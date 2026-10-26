#!/usr/bin/env python3
"""Where do purchases actually start? RevenueCat funnel by entry point, per period.

  RC_API_KEY=sk_... rc_funnel.py --country BR --attribution "No Attribution" \
      --period "before:2026-10-06:2026-10-16" --period "after:2026-10-17:2026-10-25" \
      [--source-attr paywall_source] [--json out.json]

Per period: new users (`customers_new`), share that saw a paywall within a day
(`paywall_encounter`), paid subs (`actives_new`) split by the custom subscriber
attribute the app sets at purchase time (default `paywall_source`), and each
source's paid subs per paywall viewer. Answers "did fewer users reach the paywall,
or did the paywall that sells convert worse?" — and points at the screen to fix.

Notes
- Custom attributes segment as `external_subscriber_attributes:<name>`; purchases
  made before the app started setting the attribute show as blank "(none)", so
  compare only periods after it was introduced.
- `paywall_conversion` is only populated for RevenueCat-built paywalls; apps with
  custom paywalls get zeros there, so this script uses encounters + attributes.
- A purchase's attribute is the user's latest value (RevenueCat attributes are
  per customer), which is the entry point for first purchases.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.revenuecat.com/v2"


def chart(key, project, name, filters, start, end, segment=None):
    p = {"start_date": start, "end_date": end, "resolution": "0", "filters": json.dumps(filters)}
    if segment:
        p["segment"] = segment
    req = urllib.request.Request(f"{API}/projects/{project}/charts/{name}?" + urllib.parse.urlencode(p),
                                 headers={"Authorization": f"Bearer {key}"})
    time.sleep(2.5)  # Charts & Metrics: 25 requests/minute
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"RevenueCat {e.code} on {name}: {e.read().decode(errors='replace')[:400]}")


def by_day(c, measure_name=None, measure_index=None):
    """→ {segment_name: {date: value}} for one measure (realtime format)."""
    meas = [m["display_name"] for m in c.get("measures") or []]
    mi = measure_index if measure_index is not None else meas.index(measure_name)
    segs = [s["display_name"] or "(none)" for s in (c.get("segments") or [{"display_name": "Total"}])]
    out = {}
    for v in c.get("values") or []:
        if v["measure"] != mi:
            continue
        day = dt.datetime.fromtimestamp(v["cohort"], dt.timezone.utc).date().isoformat()
        out.setdefault(segs[v.get("segment", 0)], {})[day] = v["value"] or 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True, help="ISO codes, comma-separated")
    ap.add_argument("--attribution", help='attribution_source to keep, e.g. "No Attribution"')
    ap.add_argument("--period", action="append", required=True, help="label:YYYY-MM-DD:YYYY-MM-DD")
    ap.add_argument("--source-attr", default="paywall_source")
    ap.add_argument("--project")
    ap.add_argument("--json")
    a = ap.parse_args()

    key = os.environ.get("RC_API_KEY") or sys.exit("set RC_API_KEY (RevenueCat v2 secret key, charts read)")
    project = a.project
    if not project:
        req = urllib.request.Request(f"{API}/projects", headers={"Authorization": f"Bearer {key}"})
        items = json.load(urllib.request.urlopen(req, timeout=60))["items"]
        if len(items) != 1:
            sys.exit("pass --project: " + ", ".join(i["id"] for i in items))
        project = items[0]["id"]

    periods = [p.rsplit(":", 2) for p in a.period]
    start, end = min(p[1] for p in periods), max(p[2] for p in periods)
    flt = [{"name": "country", "values": a.country.split(",")}]
    if a.attribution:
        flt.append({"name": "attribution_source", "values": [a.attribution]})

    enc = chart(key, project, "paywall_encounter", flt, start, end)
    installs = by_day(enc, measure_index=0).get("Total", {})
    encounters = by_day(enc, measure_index=1).get("Total", {})
    subs = by_day(chart(key, project, "actives_new", flt, start, end,
                        f"external_subscriber_attributes:{a.source_attr}"), "Total Paid Subscriptions")

    res = []
    for label, s, e in periods:
        win = lambda series: sum(v for d, v in series.items() if s <= d <= e)
        n, seen, total = win(installs), win(encounters), win(subs.get("Total", {}))
        days = (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days + 1
        sources = {k: win(v) for k, v in subs.items() if k != "Total"}
        res.append({"label": label, "days": days, "new_users": n, "paywall_viewers": seen, "paid": total,
                    "reach": seen / n if n else None, "paid_per_viewer": total / seen if seen else None,
                    "by_source": sources})

    print(f"{'period':14}{'new/d':>7}{'reach':>7}{'paid/d':>8}{'paid/viewer':>12}")
    for r in res:
        d = r["days"]
        print(f"{r['label'][:13]:14}{r['new_users']/d:>7.0f}{(r['reach'] or 0)*100:>6.1f}%{r['paid']/d:>8.1f}"
              f"{(r['paid_per_viewer'] or 0)*100:>11.2f}%")
    names = sorted({k for r in res for k in r["by_source"]}, key=lambda k: -sum(r["by_source"].get(k, 0) for r in res))
    print(f"\npaid subs by {a.source_attr} (per day | per 100 paywall viewers | share)")
    for k in names:
        if sum(r["by_source"].get(k, 0) for r in res) < 3:
            continue
        cells = []
        for r in res:
            x = r["by_source"].get(k, 0)
            cells.append(f"{r['label'][:10]} {x / r['days']:5.1f}/d {x / r['paywall_viewers'] * 100 if r['paywall_viewers'] else 0:5.2f} "
                         f"{x / r['paid'] * 100 if r['paid'] else 0:3.0f}%")
        print(f"  {k[:28]:29}" + " | ".join(cells))
    if a.json:
        json.dump({"country": a.country, "attribution": a.attribution, "periods": res}, open(a.json, "w"), indent=2)


if __name__ == "__main__":
    main()
