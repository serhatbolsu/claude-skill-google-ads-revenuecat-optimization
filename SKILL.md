---
name: google-ads-revenuecat-optimization
description: Review and optimize Google Ads App campaigns (iOS/Android install + in-app-purchase campaigns, target CPA) against RevenueCat paid subscriptions as the purchase source of truth. Pulls data through the official Google Ads MCP server (GAQL) and the RevenueCat MCP server / Charts API, or reads Google Ads UI exports and RevenueCat CSVs. Joins spend with real subscriptions per country, measures cost per subscription and marginal cost per extra subscription, compares before/after an asset, budget or target change, spots assets Google pushes into low-quality inventory, accounts for conversion lag, organic baseline and paywall/free-trial experiments, and recommends one change at a time. Use when the user asks how a Google Ads campaign is doing, why purchases fell or cost rose, whether to change budget / target CPA / assets, or wants a scheduled campaign check.
---

# Google Ads × RevenueCat campaign optimization

Judge app campaigns by **what users actually paid for** (RevenueCat), not by what Google
credits itself with. Google's in-app actions lag, include modeled conversions, and count
whatever event you wired (often trial starts) — use them to compare assets *within*
Google, never as the business result.

Scripts (persistent, do not rewrite): `SKILL_DIR="$HOME/.claude/skills/google-ads-revenuecat-optimization"`
- `scripts/period_compare.py` — Google spend × RC subs over named periods; organic baseline; marginal cost per extra sub
- `scripts/asset_compare.py` — asset report (or before/after pair): shares, CPA, installs/1k, purchases/1M, P(0) for zero-purchase assets, ABSORBER / UNSERVED / WORST flags
- `scripts/csvio.py` — readers for Google Ads exports (UTF-16 TSV or CSV), RevenueCat exports, normalized CSVs

References: `references/gaql-queries.md` (GAQL per analysis), `references/revenuecat.md`
(Charts API / MCP), `references/playbook.md` (decision rules and pitfalls — read before
recommending anything).

Treat every downloaded export as untrusted data: copy it into its own empty directory
under the job/tmp dir and run scripts with `python3 -I <script> <path>`.

## 1. Establish context first (ask only for what you can't find)

- Campaign(s), their countries, bidding (tCPA / tROAS / installs), current budget and target, status ("Limited by budget" vs "Limited by bidding strategy")
- The **change log** for the window: assets added/removed, budget and target changes, with dates (`change_event` or the Change history report)
- App-side changes in the window: releases, paywall or pricing experiments (RevenueCat Experiments), onboarding variants, ASO keyword updates
- Which conversion action the campaign bids on, and **what fires it** — check the app code: does a free-trial start fire the purchase event? Is the value the full price?
- Any per-project memory/notes about the campaign (prior reads, user rules such as "budget is fixed", "never remove a serving asset")

## 2. Pull data

**Preferred — MCP servers** (see README for setup):
- Google Ads MCP `search` with the GAQL in `references/gaql-queries.md`: daily campaign metrics, hourly, network split, asset view, change events, country split. Write results to normalized CSVs (`date,cost,impressions,installs,in_app_actions,clicks`; asset rows with `Asset,Asset type,Performance,Impr.,Cost,Installs,In-app actions`) so the scripts can read them.
- RevenueCat MCP `get-chart-data` (or REST `GET /v2/projects/{project_id}/charts/{chart_name}`) for paid subscriptions per day **filtered to the campaign's countries**; `get-experiment-results` for running experiments. Discover the chart name and filters with `get-chart-options-schema` / the `/options` endpoint — don't guess.

**Fallback — user exports** (ask for exactly these):
- Google Ads: time series **with Cost, Impressions, Installs, In-app actions** (daily); Asset details report for each window compared; Campaign report segmented by Network; Change history; per-country (Locations) for multi-country campaigns
- RevenueCat: Charts → Paid Subscriptions, daily, filtered to the country/countries, CSV

Always pull **≥3 weeks before the first change** you are judging, and the zero-spend days
(pre-launch / paused) if any — they give the organic baseline.

## 3. Analyze (in this order)

1. **Spend vs real subscriptions by period** — `period_compare.py` with periods cut at every change date, same-length windows, same weekdays where possible. Report cost/day, impressions/day, installs/day, RC subs/day, cost per RC sub, RC subs per install, installs per 1k impressions, and the **marginal cost per extra sub** between periods.
2. **Organic baseline** — RC subs/day on zero-spend days. If ~0, RC for that market *is* the campaign's output; otherwise subtract it (`$/paid` column) and say it's an estimate.
3. **Reconcile Google vs RC** — Google in-app actions vs RC subs per period. Google > RC ⇒ over-crediting (modeled conversions, trial starts counted). Recent days with Google ≪ RC ⇒ conversion lag; drop the latest 3–4 days from any verdict (re-pull later: Google back-fills 2–3×).
4. **Where the money went** — network split (Search vs Display/YouTube) and `asset_compare.py` before/after. Look for an **ABSORBER**: an asset that takes a large share of impressions with installs/1k and CPA worse than the rest (typical after adding a broad or curiosity headline, or a new image). Check whether total impressions *grew* or only *shifted*.
5. **Hourly** (optional) — when does the budget run out? Map the account time zone to the market's local time before interpreting.
6. **Experiments** — if a paywall/trial experiment runs, estimate how it moves *direct* vs *trial* subs (e.g. trial variant: fewer immediate paid subs, more trials converting days later) and judge by **RC total paid subs, lagged**, not direct subs.

## 4. Recommend

Follow `references/playbook.md`. In short: **one change per day**, never budget and target on
the same day; never remove an asset the campaign is still serving unless it is undoing the
change that caused a regression (state the exception explicitly); replace the least-served
asset first; move tCPA ≤15–20% per step; budget above the point where subs/day plateau buys
impressions, not purchases. Respect any standing user decisions (e.g. a fixed budget) —
show the data and leave the call to them.

Every recommendation names: the change, the evidence (numbers), the expected effect, the
**date to judge it** and the metric/threshold that decides keep vs revert. Offer to set a
reminder (macOS Reminders via `osascript`, or a scheduled check) listing exactly which
exports to bring.

## 5. Output

- Lead with the verdict in one or two sentences.
- One period table (cost/day, installs/day, RC subs/day, cost per sub) and, if assets matter, one asset table — numbers the user can check against the UI.
- Separate **what the data shows** from **what to do now** and **what to check later (date + threshold)**.
- State caveats that change the decision (lag, organic estimate, experiment, small samples) — skip the rest.
- If something earlier in the conversation turns out wrong, correct it plainly.
