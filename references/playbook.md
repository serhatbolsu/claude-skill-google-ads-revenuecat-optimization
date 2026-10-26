# Playbook — decision rules and pitfalls

Learned from real reviews of target-CPA app campaigns. Numbers below are illustrative.

## Measurement

- **RevenueCat decides, Google explains.** Verdicts use RC paid subs per day for the campaign's countries. Google metrics explain *why* (which network, which asset, which hour).
- **Conversion lag.** Google back-fills in-app actions for days: a day that showed 6 actions can read 17 two days later. Never judge the latest 3–4 days on Google numbers; RC has no lag (except trials).
- **Organic baseline.** RC subs on zero-spend days (before launch, paused days). In a market with ~0 organic, RC = campaign output — the cleanest possible read. Where organic exists, it can move on its own (ASO keyword updates, featuring) — check app releases before blaming the campaign.
- **What fires the conversion.** If a free-trial start fires the bid-on event, Google counts trials as purchases on day 0 and may report the full product price as value. Google CPA then looks better than reality and diverges from RC when trial share changes (e.g. a paywall experiment).
- **Google can over-credit.** If Google's in-app actions for a window exceed *all* RC subs in that country (organic included), the bidding is optimizing toward an inflated signal.
- **Asset metrics aren't additive.** Headline, description and image metrics overlap; use the time series for totals.
- **Compare like with like.** Same-length windows, matching weekdays, cut at change dates. Mixed windows (a change mid-window) blur the effect.
- **Impressions vs installs.** Track installs per 1k impressions per asset and per period. A surge in impressions with flat installs is low-intent inventory, not growth.
- **Small samples.** For a zero-purchase asset, expected = impressions × type-average purchases-per-impression; P(0) = e^-expected. ~7% is weak evidence; <1% is conclusive. Re-check at ~2× the data.

## Diagnosing a drop (before recommending a pause or switch)

- **Decompose**: RC subs/day = new users/day × purchases per new user. Pull `customers_new` and `actives_new` from RevenueCat for the campaign's cohort (country + `attribution_source`). Volume drops point at the campaign (budget, bids, inventory); conversion drops point at user quality *or* the app.
- **Use another channel as a control.** Another attributed channel in the same market (e.g. Apple Search Ads) sees the same app but different ads. If its conversion moves with Google's on the same date, the cause is the app/paywall/config; if only Google's moves, it's the traffic.
- **Use other markets as a control.** A release that hurts one market only points at market-specific config (offering, placement, experiment, localisation).
- **Line up every timeline**: Google change history, app release adoption (`customers_new` by `first_app_version` shows the day a version goes live), RevenueCat experiments (start/stop, audiences, variant metadata) and offering mix per market (`actives_new` by `offering_identifier`).
- **Audit experiments**: audiences pinned to one app version stop enrolling once users update; a variant whose metadata equals control measures noise (useful as an A/A: on ~500 users per arm, ±30% is noise).
- **Don't switch campaigns for an app-side drop**: a fallback campaign sends users into the same paywall. Re-estimate its cost at today's conversion (its old installs/day × current purchases per new user), not its historical cost per sub.
- **Per-asset quality**: installs per 1k impressions per asset before/after a change shows which images/descriptions Google moved impressions to — often older weak images, not only the new ones.

## Budget and target

- **Find the plateau.** Plot subs/day against cost/day across periods. Beyond the point where subs stop rising, extra budget buys impressions (often Display) — marginal cost per extra sub can be 3–10× the average.
- **Budget-limited vs target-limited.** If spend ≈ budget every day, the budget binds; if spend < budget and status says "bidding strategy constrained", the target binds. Raising the target of a target-limited campaign buys volume at a higher CPA; raising the budget of a budget-limited one with a low target fills it with cheap impressions.
- **Steps.** Move tCPA ≤15–20% per step; never change budget and target on the same day; give each change ≥5–7 days (longer for small campaigns) before judging.
- **Standing decisions.** If the user fixed a budget, show the plateau data and leave the call to them; don't re-litigate.
- **Fallback campaign.** When a newer campaign degrades below an older one's historical cost per sub, set a dated threshold: still worse by date X → pause it and re-enable the old one. Never run both in the same market (they bid against each other and blur attribution).

## Assets

- **Keep serving assets.** Don't remove an asset Google is serving and learning on, even if its CPA is high; replace the **least-served** asset (lowest impression and spend share) first, with copy built on themes of assets near the CPA target.
- **Exception — undoing a regression.** When an asset added on day X becomes an ABSORBER (large share of impressions, installs/1k and CPA worse than the rest) and the campaign's real cost per sub degraded from X+1, replacing it is a rollback, not cutting a performer. Say so explicitly.
- **Absorber pattern.** Broad or curiosity headlines (new-device names, trending terms) and some new images can get rated Best by Google — many impressions, many cheap installs — while buyers per install fall. Check total impressions: if they rose and installs/1k fell, the asset added low-intent reach. If they stayed flat, it only shifted share.
- **One asset change per day**, and not on budget/target change days. Batch changes make the next read unattributable.
- **Text rules.** Don't repeat words already in the app name/title (every app ad shows it). Avoid third-party trademarks in ad text unless the user accepts the disapproval risk. Avoid claims the app can't back (e.g. "wireless" for software that isn't).
- **Images.** Judge as a group per impression when individually small. Replace weakest with variants of the best per-impression performer, not just the highest-spend one.

## Hourly

- Map the account time zone to the market's local time before reading an hourly chart.
- A budget that runs out at the same local hour every day is normal for a budget-limited campaign; check whether that pattern predates the change you're investigating before attributing it.
- App campaigns can't use ad scheduling.

## Follow-ups

Every recommendation gets a dated check with a threshold (e.g. "Oct 28: cost per RC sub over Oct 22–27 above $33 → revert"). Put the exports to bring in the reminder text so the next run starts with the right data.
