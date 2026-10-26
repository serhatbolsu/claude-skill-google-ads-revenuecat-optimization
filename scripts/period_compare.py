#!/usr/bin/env python3
"""Join Google Ads daily spend with RevenueCat paid subscriptions over named periods.

  period_compare.py --google ts.csv --rc rc.csv \
      --period "before:2026-09-30:2026-10-06" --period "after:2026-10-13:2026-10-18" \
      [--rc-group Total] [--organic 3.5] [--json out.json]

Per period (all per day): cost, impressions, installs, Google in-app actions
(if the export has them), RC paid subs (total / direct / trial conversions),
Google cost per RC sub, cost per *paid-media* sub (RC minus organic), RC subs
per Google install, installs per 1k impressions. Between consecutive periods
it prints the marginal cost of each extra RC sub.

Organic baseline: unless --organic is given, it is the mean RC subs/day on
days where Google cost was 0 (campaign paused / before launch). Say so in the
write-up — it is an estimate, and organic grows after ASO changes.
"""

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from csvio import read_google_timeseries, read_revenuecat_paid_subs  # noqa: E402


def days(a, b):
    return [a + dt.timedelta(i) for i in range((b - a).days + 1)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--google", required=True, action="append",
                   help="Google Ads time series CSV; repeat to sum several campaigns")
    p.add_argument("--rc", required=True, help="RevenueCat Paid Subscriptions CSV (one country/market)")
    p.add_argument("--rc-group", default="Total")
    p.add_argument("--period", action="append", required=True, help="label:YYYY-MM-DD:YYYY-MM-DD")
    p.add_argument("--organic", type=float, help="organic RC subs/day; default = mean on zero-spend days")
    p.add_argument("--json")
    a = p.parse_args()

    g = {}
    for path in a.google:
        for d, v in read_google_timeseries(path).items():
            acc = g.setdefault(d, {})
            for k, x in v.items():
                if x is not None:
                    acc[k] = acc.get(k, 0.0) + x
    # API pulls omit zero-spend days; inside the pulled range a missing day means $0.
    if g:
        for d in days(min(g), max(g)):
            g.setdefault(d, {"cost": 0.0, "impressions": 0.0, "installs": 0.0, "clicks": 0.0})
    rc = read_revenuecat_paid_subs(a.rc, a.rc_group)

    organic = a.organic
    zero_days = [d for d in rc if d in g and not g[d].get("cost")]
    if organic is None:
        organic = sum(rc[d].get("total_paid", 0) for d in zero_days) / len(zero_days) if zero_days else 0.0
    print(f"organic baseline: {organic:.1f} RC subs/day "
          f"({'given' if a.organic is not None else f'{len(zero_days)} zero-spend days'})")

    has_iap = any("in_app_actions" in v for v in g.values())
    res = []
    for spec in a.period:
        label, s, e = spec.rsplit(":", 2)
        ds = days(dt.date.fromisoformat(s), dt.date.fromisoformat(e))
        k = len(ds)
        gs = lambda f: sum(g.get(d, {}).get(f, 0.0) for d in ds)
        rs = lambda f: sum(rc.get(d, {}).get(f, 0.0) for d in ds)
        cost, impr, inst, iap = gs("cost"), gs("impressions"), gs("installs"), gs("in_app_actions")
        tot, direct, trialc = rs("total_paid"), rs("direct"), rs("trial_conversions")
        paid_media = max(tot - organic * k, 0.0)
        missing = [d.isoformat() for d in ds if d not in rc or d not in g]
        res.append({
            "label": label, "start": s, "end": e, "days": k,
            "cost_per_day": cost / k, "impressions_per_day": impr / k, "installs_per_day": inst / k,
            "google_iap_per_day": iap / k if has_iap else None,
            "rc_total_per_day": tot / k, "rc_direct_per_day": direct / k,
            "rc_trial_conversions_per_day": trialc / k,
            "cost_per_rc_sub": cost / tot if tot else None,
            "cost_per_paid_media_sub": cost / paid_media if paid_media else None,
            "rc_per_install": tot / inst if inst else None,
            "installs_per_1k_impr": inst / impr * 1000 if impr else None,
            "google_cpa": cost / iap if has_iap and iap else None,
            "missing_days": missing,
        })

    f = lambda v, fmt: "—" if v is None else format(v, fmt)
    hdr = f"{'period':22}{'cost/d':>8}{'impr/d':>9}{'inst/d':>7}{'G-iap/d':>8}{'RC/d':>6}{'direct':>7}{'trialC':>7}{'$/RC':>7}{'$/paid':>7}{'RC/inst':>8}{'inst/1k':>8}{'G-CPA':>7}"
    print(hdr)
    for r in res:
        print(f"{r['label'][:21]:22}{r['cost_per_day']:>8.0f}{r['impressions_per_day']/1000:>8.0f}k"
              f"{r['installs_per_day']:>7.0f}{f(r['google_iap_per_day'], '.1f'):>8}{r['rc_total_per_day']:>6.1f}"
              f"{r['rc_direct_per_day']:>7.1f}{r['rc_trial_conversions_per_day']:>7.1f}"
              f"{f(r['cost_per_rc_sub'], '.1f'):>7}{f(r['cost_per_paid_media_sub'], '.1f'):>7}"
              f"{f(r['rc_per_install'] and r['rc_per_install'] * 100, '.1f') + '%':>8}"
              f"{f(r['installs_per_1k_impr'], '.2f'):>8}{f(r['google_cpa'], '.1f'):>7}")
        if r["missing_days"]:
            print(f"  ! {len(r['missing_days'])} day(s) missing from an export: {', '.join(r['missing_days'][:5])}")
    for prev, cur in zip(res, res[1:]):
        dc = cur["cost_per_day"] - prev["cost_per_day"]
        dr = cur["rc_total_per_day"] - prev["rc_total_per_day"]
        m = f"${dc / dr:.0f} per extra sub" if dr > 0 and dc > 0 else ("subs fell" if dr <= 0 < dc else "n/a")
        print(f"marginal {prev['label']} → {cur['label']}: Δcost/day {dc:+.0f}, ΔRC/day {dr:+.1f} → {m}")

    if a.json:
        json.dump({"organic_per_day": organic, "periods": res}, open(a.json, "w"), indent=2)


if __name__ == "__main__":
    main()
