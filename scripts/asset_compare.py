#!/usr/bin/env python3
"""Asset report analysis for Google App campaigns.

One report:      asset_compare.py --after report.csv --after-days 7
Before vs after: asset_compare.py --before wk1.csv --before-days 8 --after wk2.csv --after-days 7

For each asset type (Headline / Description / Image / Video) it prints per-day
totals, then per asset: share of the type's impressions and spend, cost per
in-app action, installs per 1k impressions, in-app actions per 1M impressions
and — for assets with 0 in-app actions — the Poisson chance of seeing 0 by luck
at the type's average rate (below ~5% is real evidence, ~7% is not).

Flags:
  ABSORBER   ≥40% of the type's impressions, installs/1k and CPA both worse than
             the rest of the type — the asset Google pushes into cheap inventory
  UNSERVED   <3% of the type's impressions — the replace-first slot
  WORST/1M   bottom per-impression purchasers with ≥10% of impressions

Asset-level in-app actions are NOT additive across types (each impression
carries a headline, a description and maybe an image), so never sum them into a
campaign total — use the time series for that.
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from csvio import read_asset_report  # noqa: E402

TYPES = ("Headline", "Description", "Image", "Video")


def short(name, n=44):
    return name if len(name) <= n else "…" + name[-(n - 1):]


def stats(rows):
    t = {k: sum(r[k] for r in rows) for k in ("impressions", "cost", "installs", "in_app_actions", "clicks")}
    return t


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--after", required=True)
    p.add_argument("--after-days", type=int, required=True)
    p.add_argument("--before")
    p.add_argument("--before-days", type=int)
    a = p.parse_args()

    A = read_asset_report(a.after)
    B = read_asset_report(a.before) if a.before else {}
    if a.before and not a.before_days:
        sys.exit("--before-days is required with --before")

    for t in TYPES:
        ra = [dict(r, name=k) for k, r in A.items() if r["type"] == t and r["impressions"] > 0]
        if not ra:
            continue
        ta = stats(ra)
        line = (f"\n== {t}: per day impr {ta['impressions']/a.after_days/1000:.0f}k, cost ${ta['cost']/a.after_days:.0f}, "
                f"iap {ta['in_app_actions']/a.after_days:.1f}, CPA "
                f"{'$%.1f' % (ta['cost']/ta['in_app_actions']) if ta['in_app_actions'] else '—'}, "
                f"inst/1k {ta['installs']/ta['impressions']*1000:.2f}")
        rb = [dict(r, name=k) for k, r in B.items() if r["type"] == t and r["impressions"] > 0]
        tb = stats(rb) if rb else None
        if tb:
            line += (f"  | before: impr {tb['impressions']/a.before_days/1000:.0f}k, cost ${tb['cost']/a.before_days:.0f}, "
                     f"iap {tb['in_app_actions']/a.before_days:.1f}, CPA "
                     f"{'$%.1f' % (tb['cost']/tb['in_app_actions']) if tb['in_app_actions'] else '—'}, "
                     f"inst/1k {tb['installs']/tb['impressions']*1000:.2f}")
        print(line)
        rate = ta["in_app_actions"] / ta["impressions"]  # iap per impression, type average
        per1m = sorted(((r["in_app_actions"] / r["impressions"] * 1e6), r["name"]) for r in ra
                       if r["impressions"] / ta["impressions"] >= 0.10)
        worst = {n for _, n in per1m[:2]} if len(per1m) > 2 else set()
        for r in sorted(ra, key=lambda r: -r["cost"]):
            si = r["impressions"] / ta["impressions"]
            sc = r["cost"] / ta["cost"] if ta["cost"] else 0
            cpa = r["cost"] / r["in_app_actions"] if r["in_app_actions"] else None
            ipk = r["installs"] / r["impressions"] * 1000
            flags = []
            rest = [x for x in ra if x is not r]
            if rest and si >= 0.40:
                rs = stats(rest)
                rest_ipk = rs["installs"] / rs["impressions"] * 1000 if rs["impressions"] else 0
                rest_cpa = rs["cost"] / rs["in_app_actions"] if rs["in_app_actions"] else None
                if ipk < rest_ipk and (cpa is None or (rest_cpa and cpa > rest_cpa)):
                    flags.append("ABSORBER")
            if si < 0.03:
                flags.append("UNSERVED")
            if r["name"] in worst:
                flags.append("WORST/1M")
            extra = ""
            if r["in_app_actions"] == 0 and rate > 0:
                exp = r["impressions"] * rate
                extra = f" exp {exp:.1f}, P(0)={math.exp(-exp)*100:.0f}%"
            delta = ""
            b = B.get(r["name"])
            if b and tb and b["impressions"]:
                bsi = b["impressions"] / tb["impressions"]
                bcpa = b["cost"] / b["in_app_actions"] if b["in_app_actions"] else None
                delta = (f" | before share {bsi*100:3.0f}%, impr/d {b['impressions']/a.before_days/1000:.0f}k → "
                         f"{r['impressions']/a.after_days/1000:.0f}k, CPA {'$%.0f' % bcpa if bcpa else '—'} → "
                         f"{'$%.0f' % cpa if cpa else '—'}")
            elif a.before:
                delta = " | NEW (no before data)"
            print(f"  {short(r['name']):45}{r['performance'][:5]:6}impr {si*100:3.0f}% spend {sc*100:3.0f}% "
                  f"${r['cost']:7.0f} iap {r['in_app_actions']:3.0f} CPA {'$%.1f' % cpa if cpa else '—':>7} "
                  f"inst/1k {ipk:5.2f} iap/1M {r['in_app_actions']/r['impressions']*1e6:5.0f}{extra}"
                  f"{' [' + ','.join(flags) + ']' if flags else ''}{delta}")
        if B:
            gone = [k for k, r in B.items() if r["type"] == t and r["impressions"] > 0
                    and A.get(k, {}).get("impressions", 0) == 0]
            for k in gone:
                print(f"  {short(k):45}REMOVED / stopped serving (before: {B[k]['impressions']/a.before_days/1000:.0f}k impr/d)")


if __name__ == "__main__":
    main()
