#!/usr/bin/env python3
"""Pull RevenueCat "Paid Subscriptions" (chart `actives_new`) per day → normalized CSV.

  RC_API_KEY=sk_... rc_fetch.py --country US --start 2026-09-01 --end 2026-10-20 --out us.csv
  RC_API_KEY=sk_... rc_fetch.py --country CA,GB,DE,AU ...      # several countries summed
  RC_API_KEY=sk_... rc_fetch.py --list-charts                   # valid chart names
  RC_API_KEY=sk_... rc_fetch.py --country BR --attribution "No Attribution" ...
      # only subs RevenueCat did NOT attribute to another source (e.g. drop "Apple Search Ads");
      # with no organic traffic this is the Google Ads cohort. --attribution list → print sources.

Output columns: date,total_paid,direct,trial_conversions,intro_offers,product_changes,resubscriptions
— readable by period_compare.py --rc.

The key is a RevenueCat v2 secret key with `charts_metrics:charts:read`. It is read from
$RC_API_KEY, else (macOS) from the login Keychain item with service `RC_API_KEY`
(`security add-generic-password -a "$USER" -s RC_API_KEY -w <key>`), and never written
anywhere by this script. --project defaults to the only project the key can see.

Note: if API totals run above a dashboard CSV export, check attribution first — exports
filtered to "No Attribution" leave out e.g. Apple Search Ads subs. Never mix sources (or
attribution scopes) inside one comparison.
"""

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.revenuecat.com/v2"
MEASURES = {
    "Trial Conversions": "trial_conversions",
    "Intro Offers": "intro_offers",
    "Direct Subscriptions": "direct",
    "Product Changes": "product_changes",
    "Resubscriptions": "resubscriptions",
    "Total Paid Subscriptions": "total_paid",
}


def get(path, key, params=None):
    url = f"{API}{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"RevenueCat {e.code} on {path}: {body[:500]}")


def keychain_key():
    if sys.platform != "darwin":
        return None
    try:
        return subprocess.check_output(["security", "find-generic-password", "-s", "RC_API_KEY", "-w"],
                                       text=True, stderr=subprocess.DEVNULL).strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--country", help="ISO codes, comma-separated (e.g. US or CA,GB,DE,AU)")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--out")
    p.add_argument("--project")
    p.add_argument("--chart", default="actives_new")
    p.add_argument("--list-charts", action="store_true")
    p.add_argument("--attribution", help='attribution_source segment to keep, e.g. "No Attribution"; "list" prints them')
    a = p.parse_args()

    key = os.environ.get("RC_API_KEY") or keychain_key()
    if not key:
        sys.exit("set RC_API_KEY to a RevenueCat v2 secret key (read-only charts permission), "
                 "or store it in the macOS Keychain under service RC_API_KEY")

    project = a.project
    if not project:
        items = get("/projects", key)["items"]
        if len(items) != 1:
            sys.exit("key sees several projects; pass --project: " + ", ".join(f"{i['id']} ({i['name']})" for i in items))
        project = items[0]["id"]

    if a.list_charts:
        res = urllib.request.Request(f"{API}/projects/{project}/charts/_/options",
                                     headers={"Authorization": f"Bearer {key}"})
        try:
            urllib.request.urlopen(res, timeout=60)
        except urllib.error.HTTPError as e:
            print(json.loads(e.read()).get("message", ""))
        return

    if not (a.country and a.start and a.end and a.out):
        sys.exit("--country, --start, --end and --out are required")
    params = {"start_date": a.start, "end_date": a.end, "resolution": "0", "realtime": "true",
              "filters": json.dumps([{"name": "country", "values": a.country.split(",")}])}
    if a.attribution:
        params["segment"] = "attribution_source"
    d = get(f"/projects/{project}/charts/{a.chart}", key, params)

    want = 0
    if a.attribution:
        segs = [s["display_name"] for s in d.get("segments") or []]
        if a.attribution == "list" or a.attribution not in segs:
            totals = (d.get("summary") or {}).get("total") or {}
            for s_ in segs:
                print(f"{s_}: {totals.get(s_, {}).get('Total Paid Subscriptions', '?')} paid subs")
            if a.attribution != "list":
                sys.exit(f"attribution source {a.attribution!r} not found")
            return
        want = segs.index(a.attribution)

    names = [m["display_name"] for m in d.get("measures") or []]
    rows = {}
    for v in d.get("values") or []:
        if not isinstance(v, dict) or v.get("segment", 0) != want:
            continue
        day = dt.datetime.fromtimestamp(v["cohort"], dt.timezone.utc).date()
        col = MEASURES.get(names[v["measure"]])
        if col:
            rows.setdefault(day, {})[col] = v["value"]
            if v.get("incomplete"):
                rows[day]["_incomplete"] = True

    cols = ["total_paid", "direct", "trial_conversions", "intro_offers", "product_changes", "resubscriptions"]
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + cols)
        for day in sorted(rows):
            w.writerow([day.isoformat()] + [int(rows[day].get(c, 0)) for c in cols])
    inc = [d.isoformat() for d, r in rows.items() if r.get("_incomplete")]
    print(f"{a.out}: {len(rows)} days, project {project}, countries {a.country}"
          + (f", attribution {a.attribution!r}" if a.attribution else "")
          + (f"; incomplete (still filling): {', '.join(sorted(inc))}" if inc else ""))


if __name__ == "__main__":
    main()
