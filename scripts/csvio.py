"""Readers for Google Ads UI exports, RevenueCat CSV exports, and the normalized
CSVs the skill writes from MCP/API results.

Google Ads exports come in two shapes:
  * time series chart — UTF-8, comma-separated, header on line 1,
    dates like "Mon, Sep 21, 2026", money like "$1,234.56"
  * report downloads (Asset details, Campaign, Change history) — UTF-16 LE,
    tab-separated, a title line and a date-range line before the header

RevenueCat "Paid Subscriptions" exports have two header rows: a group row
("Total", per-product or per-attribution groups) and a metric row.
"""

import csv
import datetime as dt
import io


def read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def num(s):
    """'$1,234.56' / '"2,519.00"' / '12.5%' / '--' / '—' → float (0 for blanks)."""
    if s is None:
        return 0.0
    s = s.strip().strip('"').replace("$", "").replace(",", "").replace("%", "")
    if s in ("", "--", "—", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date(s):
    s = s.strip().strip('"')
    for fmt in ("%Y-%m-%d", "%a, %b %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date: {s!r}")


def _rows(path):
    """Header-detecting dict reader for both Google Ads export shapes."""
    text = read_text(path)
    lines = text.splitlines()
    delim = "\t" if "\t" in "\n".join(lines[:5]) else ","
    # Skip title / date-range lines: the header is the first line with ≥3 fields.
    start = 0
    for i, line in enumerate(lines[:6]):
        if len(next(csv.reader([line], delimiter=delim))) >= 3:
            start = i
            break
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delim))


def _pick(row, *names):
    for n in names:
        for k in row:
            if k and k.strip().lower() == n.lower():
                return row[k]
    return None


def read_google_timeseries(path):
    """→ {date: {cost, impressions, installs, in_app_actions, clicks}}.
    Missing columns stay None so callers can tell 'absent' from 'zero'."""
    out = {}
    for r in _rows(path):
        d = _pick(r, "Date", "Day", "date")
        if not d:
            continue
        try:
            day = parse_date(d)
        except ValueError:
            continue  # total rows
        def col(*n):
            v = _pick(r, *n)
            return None if v is None else num(v)
        out[day] = {
            "cost": col("Cost", "cost"),
            "impressions": col("Impr.", "Impressions", "impressions"),
            "installs": col("Installs", "installs"),
            "in_app_actions": col("In-app actions", "in_app_actions"),
            "clicks": col("Clicks", "clicks"),
        }
    return out


def read_asset_report(path):
    """→ {asset_text: {type, performance, status, impressions, clicks, cost, installs, in_app_actions}}"""
    out = {}
    for r in _rows(path):
        name = _pick(r, "Asset", "asset")
        if not name:
            continue
        out[name] = {
            "type": _pick(r, "Asset type", "type") or "",
            "performance": (_pick(r, "Performance", "performance") or "").strip(),
            "status": _pick(r, "Asset status", "status") or "",
            "impressions": num(_pick(r, "Impr.", "impressions")),
            "clicks": num(_pick(r, "Clicks", "clicks")),
            "cost": num(_pick(r, "Cost", "cost")),
            "installs": num(_pick(r, "Installs", "installs")),
            "in_app_actions": num(_pick(r, "In-app actions", "in_app_actions")),
        }
    return out


def read_revenuecat_paid_subs(path, group="Total"):
    """RevenueCat Paid Subscriptions export → {date: {metric: value}} for one group.

    Also accepts a normalized CSV with a single header row:
    date,total_paid[,direct,trial_conversions,intro_offers]."""
    rows = list(csv.reader(io.StringIO(read_text(path))))
    if rows and rows[0] and rows[0][0].strip().lower() == "date":
        hdr = [h.strip() for h in rows[0]]
        out = {}
        for r in rows[1:]:
            if r:
                rec = {hdr[i]: num(v) for i, v in enumerate(r) if i}
                out[parse_date(r[0])] = rec
        return out
    groups, metrics = rows[0], rows[1]
    idx = {}
    for i, (g, m) in enumerate(zip(groups, metrics)):
        if i and g.strip() == group:
            idx[m.strip()] = i
    if not idx:
        raise SystemExit(f"group {group!r} not in export; groups: {sorted(set(groups[1:]))}")
    key = {"Total Paid Subscriptions": "total_paid", "Direct Subscriptions": "direct",
           "Trial Conversions": "trial_conversions", "Intro Offers": "intro_offers"}
    out = {}
    for r in rows[2:]:
        if not r or not r[0].strip():
            continue
        out[parse_date(r[0])] = {key.get(m, m): num(r[i]) for m, i in idx.items()}
    return out
