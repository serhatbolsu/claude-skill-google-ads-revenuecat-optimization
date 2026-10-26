# RevenueCat data

RevenueCat is the purchase source of truth: it records each paid subscription on the day
the store charges, with no attribution model and no back-fill. It is app-wide per country —
it can never be split by campaign, which is why the organic baseline matters.

## MCP server (official)

- URL: `https://mcp.revenuecat.ai/mcp` — Claude Code: `claude mcp add --transport http revenuecat https://mcp.revenuecat.ai/mcp` (OAuth), or the AI Toolkit plugin (`claude plugins marketplace add RevenueCat/ai-toolkit` → `claude plugins install revenuecat`).
- Tools used by this skill: `get-chart-options-schema` (valid chart names, resolutions, filters, segments for a chart), `get-chart-data` (time series), `get-overview-metrics`, `list-experiments`, `get-experiment`, `get-experiment-results` (filters: platform, country, paywall view status).
- Write tools exist (`create-experiment`, `stop-experiment`, …). This skill is read-only — never call them.

## REST (Charts API v2)

- `GET https://api.revenuecat.com/v2/projects/{project_id}/charts/{chart_name}` — permission `charts_metrics:charts:read`
  - `start_date`, `end_date` (`YYYY-MM-DD`), `resolution` (chart-specific id from `/options`), `filters` (JSON array, e.g. `[{"name":"country","values":["US"]}]`), `segment`, `selectors` (JSON object), `currency`, `realtime` (default true)
- `GET …/charts/{chart_name}/options` — lists resolutions, segments, filters for that chart
- `GET …/metrics/overview`, `GET …/metrics/revenue?start_date&end_date` — permission `charts_metrics:overview:read`
- Rate limit: 25 requests/minute across Charts & Metrics. Key: a **v2 secret key** with read-only charts permissions; keep it in the environment or the MCP config, never in files or the repo.

The dashboard "Paid Subscriptions" chart is **`actives_new`** (measures: Trial Conversions,
Intro Offers, Direct Subscriptions, Product Changes, Resubscriptions, Total Paid
Subscriptions). An invalid chart name returns the full list in the error message
(`rc_fetch.py --list-charts`). `realtime=true` (default) returns `values` as
`{cohort, measure, segment, value, incomplete}` objects; `realtime=false` returns rows of
`[timestamp, m0, m1, …]` with `measures: null`. Segments include `attribution_campaign` /
`attribution_source` — populated only when an attribution integration feeds RevenueCat.

API vs dashboard export: the same chart can differ by a few percent (country/time-zone
definitions). Keep one source per comparison and restate thresholds when switching. Pull **daily**, **filtered to the campaign's countries**, and ask for the breakdown
into direct subscriptions / trial conversions / intro offers where the chart offers it.

Write the result as a normalized CSV for `period_compare.py`:
```
date,total_paid,direct,trial_conversions,intro_offers
2026-10-01,42,37,3,2
```

## UI export fallback

Charts → Paid Subscriptions → filter Country → daily → Export CSV. The file has two header
rows (group, metric); `csvio.read_revenuecat_paid_subs` reads the `Total` group by default
(`--rc-group` picks another, e.g. an attribution group like `No Attribution`).

## Experiments change what "a purchase" means

A free-trial variant converts later: fewer *direct* subs today, more *trial conversions*
3–7 days later. While one runs:
- judge by **total paid subs**, lagged by the trial length + 1 day;
- estimate the shift from the experiment's results (per variant: direct purchases, trials started, customers) and state it;
- check the app's purchase logging — if a trial start fires the ad-network conversion event, Google counts trials as purchases on day 0 (often with the full price as value) and its CPA looks better than reality.
