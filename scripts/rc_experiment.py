#!/usr/bin/env python3
"""RevenueCat Experiments → what ran, when, and per-variant results.

  rc_experiment.py                      # list experiments: status, dates (UTC), enrollment,
                                        # countries, placements whose offering differs
  rc_experiment.py --id exp0123abcd     # results: every metric for A / B (and C / D),
                                        # plus per-product rows for conversions / trials / paid

Key: $RC_API_KEY, else the macOS Keychain item `RC_API_KEY` (see rc_fetch.py).
--project defaults to the only project the key can see. Read-only.

Reading results: "Initial conversions" counts trial starts + direct purchases; a variant
that pushes trials can win it while "Paid customers" / MRR lose. Trials still running
("Active trials") make paid numbers provisional.
"""

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rc_fetch import get, keychain_key  # noqa: E402


def ts(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if ms else "—"


def list_experiments(project, key):
    for e in get(f"/projects/{project}/experiments", key, {"limit": 50})["items"]:
        status = ("stopped" if e.get("stopped_at") else "paused" if e.get("paused_at") and not e.get("resumed_at")
                  else "running")
        countries = [c["value"] for g in ((e.get("pinned_audience") or {}).get("rules") or {}).get("groups", [])
                     for c in g["conditions"] if c["field"] == "country"]
        diffs = []
        for p in (e.get("placements") or {}).get("placement_offerings", []):
            ids = [p.get(f"offering_{v}") for v in "abcd"]
            names = [o["identifier"] for o in ids if o]
            if len({o["id"] for o in ids if o}) > 1:
                diffs.append(f"{p['placement_identifier']}: {' → '.join(names)}")
        print(f"{e['id']}  {e['display_name']}  [{status}]  {e['experiment_type']}  "
              f"enroll {e['enrollment_percentage']}% {e['enrollment_mode']}  countries {countries or 'all'}")
        print(f"    started {ts(e.get('started_at'))}  paused {ts(e.get('paused_at'))}  "
              f"resumed {ts(e.get('resumed_at'))}  stopped {ts(e.get('stopped_at'))}")
        print(f"    differs: {'; '.join(diffs) or 'offering only: ' + e['offering_a']['identifier'] + ' → ' + e['offering_b']['identifier']}")


def results(project, key, exp_id):
    r = get(f"/projects/{project}/experiments/{exp_id}/results", key)
    variants = sorted({v["variant"] for s in r["sections"] for v in s["values"]})
    for s in r["sections"]:
        segments = [g["display_name"] for g in s["segments"]]
        vals = {(v["metric"], v["segment"], v["variant"]): v for v in s["values"]}
        print(f"\n## {s['section']}")
        print(f"  {'metric':40}" + "".join(f"{v.upper():>12}" for v in variants) + "   change vs control")
        for i, m in enumerate(s["metrics"]):
            row = [vals.get((i, 0, v), {}) for v in variants]
            change = next((x.get("change") for x in row[1:] if x.get("change") is not None), None)
            print(f"  {m['name']:40}" + "".join(f"{x.get('value', ''):>12}" for x in row)
                  + (f"   {change:+.1f}%" if change is not None else ""))
        for i, m in enumerate(s["metrics"]):
            if m["name"] not in ("Initial conversions", "Trials started", "Paid customers"):
                continue
            for si, seg in enumerate(segments[1:], 1):
                row = [vals.get((i, si, v), {}).get("value") for v in variants]
                if any(row):
                    print(f"      {m['name']:22} {seg:44}" + "".join(f"{x or 0:>8g}" for x in row))
    for st in r.get("statistics", []):
        cells = []
        for v in st["variants"]:
            lo, hi = v.get("credible_interval_lower"), v.get("credible_interval_upper")
            ctw = v.get("chance_to_win")
            cells.append(f"{v['name'].upper()} {lo * 100:.1f}–{hi * 100:.1f}%" if lo is not None else v["name"].upper())
            if ctw is not None:
                cells[-1] += f" (P win {ctw * 100:.1f}%)"
        print(f"\n  {st['metric_name']:26} " + " | ".join(cells))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", help="experiment id; omit to list experiments")
    p.add_argument("--project")
    a = p.parse_args()
    key = os.environ.get("RC_API_KEY") or keychain_key() or sys.exit(
        "set RC_API_KEY or store the key in the Keychain as RC_API_KEY")
    project = a.project
    if not project:
        items = get("/projects", key)["items"]
        if len(items) != 1:
            sys.exit("key sees several projects; pass --project")
        project = items[0]["id"]
    if a.id:
        results(project, key, a.id)
    else:
        list_experiments(project, key)


if __name__ == "__main__":
    main()
