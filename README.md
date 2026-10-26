# google-ads-revenuecat-optimization

A Claude Code skill for reviewing and optimizing **Google Ads App campaigns** (install +
in-app-purchase, target CPA) using **RevenueCat** paid subscriptions as the purchase source
of truth.

It answers questions like:
- Did the budget/target/asset change on day X help or hurt — in real subscriptions, not Google's in-app actions?
- Why did purchases fall while cost rose?
- Which asset is Google pushing into low-quality inventory?
- What does each extra subscription cost at the current budget?
- Is a paywall / free-trial experiment distorting the read?

## Install

```bash
git clone https://github.com/serhatbolsu/claude-skill-google-ads-revenuecat-optimization.git \
  ~/.claude/skills/google-ads-revenuecat-optimization
```

Claude Code picks it up automatically (`/google-ads-revenuecat-optimization`, or just ask
about a campaign). Python 3.9+, standard library only.

## Data sources

The skill works with CSV exports out of the box. For hands-free pulls, connect both
official MCP servers.

### Google Ads MCP (read-only)

Official server: <https://github.com/googleads/google-ads-mcp> ·
docs: <https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server>

Needs a Google Cloud project with Google Ads API access (Explorer, Basic or Standard; the
access level is tied to the Cloud project) and OAuth / application-default credentials with
the Google Ads scope. Add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": ["run", "--spec", "git+https://github.com/googleads/google-ads-mcp.git", "google-ads-mcp"],
      "env": {
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/credentials.json"
      }
    }
  }
}
```

Set `GOOGLE_ADS_LOGIN_CUSTOMER_ID` too if you reach the account through a manager account.
Tools: `list_accessible_customers`, `search` (GAQL), `get_resource_metadata`.

### RevenueCat MCP

```bash
claude mcp add --transport http revenuecat https://mcp.revenuecat.ai/mcp
```

OAuth with your RevenueCat account, or a v2 secret key with read-only charts permissions.
The skill only uses read tools (`get-chart-data`, `get-chart-options-schema`,
`get-experiment-results`, …). Docs: <https://www.revenuecat.com/docs/tools/mcp>

### CSV fallback

- Google Ads → time series chart with **Cost, Impressions, Installs, In-app actions** (daily) → Download
- Google Ads → Assets → Asset details report (one per window you compare)
- Google Ads → Campaign report segmented by Network; Change history; Locations
- RevenueCat → Charts → Paid Subscriptions → filter country → daily → Export CSV

## Scripts

```bash
S=~/.claude/skills/google-ads-revenuecat-optimization/scripts

# Spend vs real subscriptions by period (repeat --google to sum campaigns in one market)
python3 -I $S/period_compare.py --google timeseries.csv --rc revenuecat.csv \
  --period "before:2026-09-30:2026-10-06" --period "after:2026-10-13:2026-10-19"

# Asset report, or before/after pair
python3 -I $S/asset_compare.py --before assets_wk1.csv --before-days 7 --after assets_wk2.csv --after-days 7
```

`rc_fetch.py` pulls RevenueCat Paid Subscriptions per day for one or more countries
(`RC_API_KEY=sk_… python3 -I $S/rc_fetch.py --country US --start 2026-09-01 --end 2026-10-20 --out us.csv`).

`period_compare.py` estimates organic subs/day from zero-spend days (override with
`--organic`) and prints the marginal cost of each extra subscription between periods.
`asset_compare.py` flags ABSORBER (high share, worse installs/1k and CPA), UNSERVED (<3%
share — replace first) and WORST/1M assets, and gives P(0) for zero-purchase assets.

## Privacy

Exports contain account data. Keep them out of this repo (`.gitignore` blocks `*.csv`),
and keep API keys in the environment or MCP config — never in files here.

## Layout

```
SKILL.md                  workflow Claude follows
references/playbook.md    decision rules and pitfalls
references/gaql-queries.md GAQL for each analysis
references/revenuecat.md  Charts API / MCP usage, experiments
scripts/                  rc_fetch.py, period_compare.py, asset_compare.py, csvio.py
```
