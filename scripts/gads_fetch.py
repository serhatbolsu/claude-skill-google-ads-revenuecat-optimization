#!/usr/bin/env python3
"""Pull Google Ads app-campaign data over the REST API → normalized CSVs / tables.

Use when the Google Ads MCP server is not connected (or fails). Auth is gcloud
application-default credentials with the adwords scope; no developer token is needed
since Sept 2026 — the Cloud project's API access level (Explorer/Basic/Standard) is
the access unit. Read-only: this script only runs `googleAds:search`.

  export GOOGLE_ADS_CUSTOMER_ID=1234567890      # account to read (no dashes)
  export GOOGLE_CLOUD_PROJECT=my-cloud-project  # project with Google Ads API access
  gads_fetch.py status                                   # app campaigns: status, budget, target
  gads_fetch.py daily  --campaign ID --start 2026-10-01 --end 2026-10-28 --out g.csv
  gads_fetch.py assets --campaign ID --start 2026-10-22 --end 2026-10-28 --out a.csv
  gads_fetch.py network --campaign ID --period pre:2026-10-07:2026-10-13 --period post:2026-10-22:2026-10-28
  gads_fetch.py geo     --campaign ID --period ...      # per country
  gads_fetch.py hourly  --campaign ID --start D --end D
  gads_fetch.py changes --campaign ID --start 2026-10-01 --end 2026-10-29   # last 30 days only
  gads_fetch.py query "SELECT campaign.id, campaign.name FROM campaign"     # raw GAQL → JSON lines

`daily` writes date,cost,impressions,installs,in_app_actions,clicks (period_compare.py
--google); several --campaign IDs are summed per day. `assets` writes
Asset,Asset type,Performance,Impr.,Cost,Installs,In-app actions (asset_compare.py), one row
per asset text (or image/video asset ID) and field type. API asset IDs differ from the IDs
the UI shows for images — match images by their preview, not by a UI ID.

Flags: --customer / --project override the env vars; --login-customer when the account is
reached through a manager (env GOOGLE_ADS_LOGIN_CUSTOMER_ID). --api-version (default v24).
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

FIELD_TYPES = {
    "HEADLINE": "Headline",
    "DESCRIPTION": "Description",
    "MARKETING_IMAGE": "Image",
    "SQUARE_MARKETING_IMAGE": "Image",
    "PORTRAIT_MARKETING_IMAGE": "Image",
    "LANDSCAPE_LOGO": "Image",
    "LOGO": "Image",
    "MEDIA_BUNDLE": "Image",
    "YOUTUBE_VIDEO": "Video",
}
COUNTRIES = {"2840": "US", "2124": "CA", "2826": "GB", "2036": "AU", "2276": "DE", "2076": "BR",
             "2484": "MX", "2250": "FR", "2392": "JP", "2756": "CH", "2380": "IT", "2724": "ES",
             "2528": "NL", "2752": "SE", "2554": "NZ", "2372": "IE", "2040": "AT", "2056": "BE"}


class Ads:
    def __init__(self, customer, project, login_customer, version):
        if not customer or not project:
            sys.exit("set GOOGLE_ADS_CUSTOMER_ID and GOOGLE_CLOUD_PROJECT (or pass --customer / --project)")
        self.url = f"https://googleads.googleapis.com/{version}/customers/{customer.replace('-', '')}/googleAds:search"
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"], text=True,
                stderr=subprocess.PIPE).strip()
        except (OSError, subprocess.CalledProcessError) as e:
            sys.exit("no application-default token — log in with a Desktop OAuth client:\n"
                     "  gcloud auth application-default login --client-id-file=client_secret.json "
                     "--scopes=https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform\n"
                     f"({getattr(e, 'stderr', e)})")
        self.headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": project,
                        "Content-Type": "application/json"}
        if login_customer:
            self.headers["login-customer-id"] = login_customer.replace("-", "")

    def search(self, query):
        rows, page = [], None
        while True:
            body = {"query": query}
            if page:
                body["pageToken"] = page
            req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    res = json.load(r)
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                hint = ""
                if "test accounts" in text:
                    hint = "\n→ the Cloud project needs Google Ads API access (Explorer/Basic) for real accounts."
                sys.exit(f"Google Ads {e.code}: {text[:1500]}{hint}")
            rows += res.get("results", [])
            page = res.get("nextPageToken")
            if not page:
                return rows


def metric(row, name):
    return float(row.get("metrics", {}).get(name, 0) or 0)


def ids_clause(campaigns):
    ids = ",".join(c.strip() for c in campaigns.split(","))
    return f"campaign.id IN ({ids})"


def periods(args):
    if args.period:
        out = []
        for p in args.period:
            label, start, end = p.split(":")
            out.append((label, start, end))
        return out
    if not (args.start and args.end):
        sys.exit("pass --start/--end or one or more --period label:YYYY-MM-DD:YYYY-MM-DD")
    return [(f"{args.start}..{args.end}", args.start, args.end)]


def write_csv(path, header, rows):
    out = open(path, "w", newline="") if path else sys.stdout
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    if path:
        out.close()
        print(f"{path}: {len(rows)} rows", file=sys.stderr)


def cmd_status(ads, a):
    where = "campaign.advertising_channel_type = 'MULTI_CHANNEL'"
    if a.campaign:
        where = ids_clause(a.campaign)
    rows = ads.search(
        "SELECT campaign.id, campaign.name, campaign.status, campaign.primary_status, "
        "campaign.primary_status_reasons, campaign.bidding_strategy_type, "
        "campaign.target_cpa.target_cpa_micros, campaign.target_roas.target_roas, "
        f"campaign_budget.amount_micros FROM campaign WHERE {where}")
    for r in rows:
        c, b = r["campaign"], r.get("campaignBudget", {})
        target = c.get("targetCpa", {}).get("targetCpaMicros")
        target = f"tCPA ${int(target) / 1e6:g}" if target else (
            f"tROAS {c['targetRoas']['targetRoas']}" if c.get("targetRoas") else c.get("biddingStrategyType", ""))
        print(f"{c['id']}  {c['name']:32} {c['status']:8} {c.get('primaryStatus', ''):10} "
              f"{','.join(c.get('primaryStatusReasons', [])):40} budget ${int(b.get('amountMicros', 0)) / 1e6:g}  {target}")


def cmd_daily(ads, a):
    rows = ads.search(
        "SELECT segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks, "
        "metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions "
        f"FROM campaign WHERE {ids_clause(a.campaign)} AND segments.date BETWEEN '{a.start}' AND '{a.end}'")
    days = {}
    for r in rows:
        d = days.setdefault(r["segments"]["date"], [0.0, 0, 0.0, 0.0, 0])
        d[0] += metric(r, "costMicros") / 1e6
        d[1] += metric(r, "impressions")
        d[2] += metric(r, "biddableAppInstallConversions")
        d[3] += metric(r, "biddableAppPostInstallConversions")
        d[4] += metric(r, "clicks")
    write_csv(a.out, ["date", "cost", "impressions", "installs", "in_app_actions", "clicks"],
              [[day, round(v[0], 2), int(v[1]), round(v[2], 1), round(v[3], 1), int(v[4])]
               for day, v in sorted(days.items())])


def cmd_assets(ads, a):
    rows = ads.search(
        "SELECT asset.id, asset.type, asset.name, asset.text_asset.text, "
        "ad_group_ad_asset_view.field_type, ad_group_ad_asset_view.performance_label, "
        "metrics.impressions, metrics.cost_micros, metrics.biddable_app_install_conversions, "
        "metrics.biddable_app_post_install_conversions FROM ad_group_ad_asset_view "
        f"WHERE {ids_clause(a.campaign)} AND segments.date BETWEEN '{a.start}' AND '{a.end}'")
    agg = {}
    for r in rows:
        asset, view = r["asset"], r["adGroupAdAssetView"]
        name = asset.get("textAsset", {}).get("text") or asset["id"]
        kind = FIELD_TYPES.get(view["fieldType"], view["fieldType"].title())
        g = agg.setdefault((name, kind), [view.get("performanceLabel", "").title(), 0.0, 0.0, 0.0, 0.0])
        g[1] += metric(r, "impressions")
        g[2] += metric(r, "costMicros") / 1e6
        g[3] += metric(r, "biddableAppInstallConversions")
        g[4] += metric(r, "biddableAppPostInstallConversions")
    write_csv(a.out, ["Asset", "Asset type", "Performance", "Impr.", "Cost", "Installs", "In-app actions"],
              [[name, kind, g[0], int(g[1]), round(g[2], 2), round(g[3], 1), round(g[4], 1)]
               for (name, kind), g in sorted(agg.items(), key=lambda kv: (kv[0][1], -kv[1][1]))])


def cmd_network(ads, a):
    print(f"{'period':22}{'network':18}{'cost':>9}{'impr':>11}{'clicks':>8}{'inst':>7}{'iap':>7}{'$/iap':>8}")
    for label, start, end in periods(a):
        rows = ads.search(
            "SELECT segments.ad_network_type, metrics.cost_micros, metrics.impressions, metrics.clicks, "
            "metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions "
            f"FROM campaign WHERE {ids_clause(a.campaign)} AND segments.date BETWEEN '{start}' AND '{end}'")
        for r in rows:
            cost, iap = metric(r, "costMicros") / 1e6, metric(r, "biddableAppPostInstallConversions")
            print(f"{label:22}{r['segments']['adNetworkType']:18}{cost:9.0f}{metric(r, 'impressions'):11.0f}"
                  f"{metric(r, 'clicks'):8.0f}{metric(r, 'biddableAppInstallConversions'):7.0f}{iap:7.1f}"
                  f"{(cost / iap if iap else 0):8.1f}")


def cmd_geo(ads, a):
    # geographic_view rejects the biddable_app_* metrics and needs campaign.id selected.
    # `conversions` counts every biddable conversion, installs included — compare countries
    # by cost and share, not $/conv against the target CPA.
    print(f"{'period':22}{'country':9}{'cost':>9}{'impr':>11}{'clicks':>8}{'conv':>8}{'$/conv':>8}")
    for label, start, end in periods(a):
        rows = ads.search(
            "SELECT campaign.id, geographic_view.country_criterion_id, metrics.cost_micros, "
            "metrics.impressions, metrics.clicks, metrics.conversions FROM geographic_view "
            f"WHERE {ids_clause(a.campaign)} AND segments.date BETWEEN '{start}' AND '{end}'")
        agg = {}
        for r in rows:
            c = r["geographicView"]["countryCriterionId"]
            g = agg.setdefault(c, [0.0, 0.0, 0.0, 0.0])
            g[0] += metric(r, "costMicros") / 1e6
            g[1] += metric(r, "impressions")
            g[2] += metric(r, "clicks")
            g[3] += metric(r, "conversions")
        for c, g in sorted(agg.items(), key=lambda kv: -kv[1][0]):
            print(f"{label:22}{COUNTRIES.get(c, c):9}{g[0]:9.0f}{g[1]:11.0f}{g[2]:8.0f}{g[3]:8.1f}"
                  f"{(g[0] / g[3] if g[3] else 0):8.1f}")


def cmd_hourly(ads, a):
    # segments.hour also rejects the biddable_app_* metrics; `conversions` includes installs.
    # Hours are in the ACCOUNT time zone, which also sets when the daily budget resets.
    rows = ads.search(
        "SELECT segments.date, segments.hour, metrics.cost_micros, metrics.impressions, metrics.clicks, "
        f"metrics.conversions FROM campaign WHERE {ids_clause(a.campaign)} "
        f"AND segments.date BETWEEN '{a.start}' AND '{a.end}'")
    write_csv(a.out, ["date", "hour", "cost", "impressions", "clicks", "conversions"],
              sorted([r["segments"]["date"], int(r["segments"]["hour"]), round(metric(r, "costMicros") / 1e6, 2),
                      int(metric(r, "impressions")), int(metric(r, "clicks")), round(metric(r, "conversions"), 1)]
                     for r in rows))


def cmd_changes(ads, a):
    rows = ads.search(
        "SELECT change_event.change_date_time, change_event.change_resource_type, "
        "change_event.resource_change_operation, change_event.changed_fields, change_event.campaign, "
        "change_event.new_resource FROM change_event "
        f"WHERE change_event.change_date_time >= '{a.start}' AND change_event.change_date_time <= '{a.end}' "
        "ORDER BY change_event.change_date_time DESC LIMIT 1000")
    wanted = {c.strip() for c in a.campaign.split(",")} if a.campaign else None
    for r in rows:
        c = r["changeEvent"]
        camp = c.get("campaign", "").rsplit("/", 1)[-1]
        if wanted and camp not in wanted:
            continue
        new = json.dumps(c.get("newResource", {}), ensure_ascii=False)
        print(f"{c['changeDateTime'][:19]}  {camp:12} {c['changeResourceType']:18} "
              f"{c['resourceChangeOperation']:7} {c.get('changedFields', '')[:60]:60} {new[:a.width]}")


def cmd_query(ads, a):
    for r in ads.search(a.gaql):
        print(json.dumps(r, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--customer", default=os.environ.get("GOOGLE_ADS_CUSTOMER_ID"))
    p.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_PROJECT_ID"))
    p.add_argument("--login-customer", default=os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    p.add_argument("--api-version", default="v24")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, campaign=True, required=True, dates=True, out=False, period=False):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        if campaign:
            s.add_argument("--campaign", required=required, help="campaign ID(s), comma-separated")
        if dates:
            s.add_argument("--start", required=not period)
            s.add_argument("--end", required=not period)
        if period:
            s.add_argument("--period", action="append", help="label:YYYY-MM-DD:YYYY-MM-DD (repeatable)")
        if out:
            s.add_argument("--out", help="CSV path (default stdout)")
        return s

    add("status", cmd_status, required=False, dates=False)
    add("daily", cmd_daily, out=True)
    add("assets", cmd_assets, out=True)
    add("network", cmd_network, period=True)
    add("geo", cmd_geo, period=True)
    add("hourly", cmd_hourly, out=True)
    add("changes", cmd_changes, required=False).add_argument("--width", type=int, default=220)
    q = sub.add_parser("query")
    q.set_defaults(fn=cmd_query)
    q.add_argument("gaql")

    a = p.parse_args()
    a.fn(Ads(a.customer, a.project, a.login_customer, a.api_version), a)


if __name__ == "__main__":
    main()
