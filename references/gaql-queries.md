# GAQL for app-campaign reviews

Run through the Google Ads MCP `search` tool (or any Google Ads API client). Before relying
on a field, confirm it with `get_resource_metadata` for that resource — field names and
selectability change between API versions. Money is in **micros** (÷ 1,000,000).

App campaigns are `campaign.advertising_channel_type = 'MULTI_CHANNEL'`
(`advertising_channel_sub_type` `APP_CAMPAIGN` / `APP_CAMPAIGN_FOR_ENGAGEMENT`).
UI "Installs" ≈ `metrics.biddable_app_install_conversions`, UI "In-app actions" ≈
`metrics.biddable_app_post_install_conversions` — verify against the UI for one day.

## Account basics

```sql
SELECT customer.id, customer.descriptive_name, customer.time_zone, customer.currency_code
FROM customer
```
The time zone matters: hourly data and "today" are in account time, not the market's.

## Campaign settings and status

```sql
SELECT campaign.id, campaign.name, campaign.status, campaign.primary_status,
       campaign.primary_status_reasons, campaign.bidding_strategy_type,
       campaign.target_cpa.target_cpa_micros, campaign_budget.amount_micros,
       campaign.app_campaign_setting.app_id, campaign.app_campaign_setting.bidding_strategy_goal_type
FROM campaign
WHERE campaign.advertising_channel_type = 'MULTI_CHANNEL'
```
`primary_status_reasons` distinguishes budget-limited from bid-strategy-limited.

## Daily time series (the backbone)

```sql
SELECT segments.date, campaign.name, metrics.cost_micros, metrics.impressions, metrics.clicks,
       metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions,
       metrics.conversions, metrics.all_conversions
FROM campaign
WHERE campaign.id = <ID> AND segments.date BETWEEN '<YYYY-MM-DD>' AND '<YYYY-MM-DD>'
ORDER BY segments.date
```
Write as `date,cost,impressions,installs,in_app_actions,clicks` for `period_compare.py`.

## Conversions by action (what is Google counting?)

```sql
SELECT segments.date, segments.conversion_action_name, metrics.conversions, metrics.all_conversions,
       metrics.conversions_value
FROM campaign
WHERE campaign.id = <ID> AND segments.date BETWEEN '<start>' AND '<end>'
```
Shows whether the bid-on action is e.g. Firebase `in_app_purchase` or a custom event, and
whether its value looks like full prices on trial starts.

## Network split

```sql
SELECT segments.ad_network_type, metrics.cost_micros, metrics.impressions,
       metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions
FROM campaign
WHERE campaign.id = <ID> AND segments.date BETWEEN '<start>' AND '<end>'
```
`SEARCH`, `SEARCH_PARTNERS`, `CONTENT` (Display), `YOUTUBE*`, `MIXED` (cross-network).

## Hourly (when does the budget run out?)

```sql
SELECT segments.date, segments.hour, metrics.cost_micros, metrics.impressions, metrics.clicks
FROM campaign
WHERE campaign.id = <ID> AND segments.date BETWEEN '<start>' AND '<end>'
```
Compare a day before and after a suspected change. App campaigns have no ad schedule;
the levers are budget and target.

## Asset performance (per window)

```sql
SELECT asset.id, asset.type, asset.name, asset.text_asset.text, asset.image_asset.full_size.url,
       ad_group_ad_asset_view.field_type, ad_group_ad_asset_view.performance_label,
       ad_group_ad_asset_view.enabled,
       metrics.impressions, metrics.clicks, metrics.cost_micros,
       metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions
FROM ad_group_ad_asset_view
WHERE campaign.id = <ID> AND segments.date BETWEEN '<start>' AND '<end>'
```
Run once per window (e.g. the 7 days before a change and the 7 days after) and write each
as an asset CSV for `asset_compare.py`. Asset metrics overlap across field types — never
add them up into a campaign total.

## Change history (last 30 days only)

```sql
SELECT change_event.change_date_time, change_event.user_email, change_event.change_resource_type,
       change_event.resource_change_operation, change_event.changed_fields,
       change_event.old_resource, change_event.new_resource, change_event.campaign
FROM change_event
WHERE change_event.change_date_time >= '<YYYY-MM-DD>' AND change_event.change_date_time <= '<YYYY-MM-DD>'
ORDER BY change_event.change_date_time DESC
LIMIT 1000
```
`LIMIT` is required. Older history: ask for the UI Change history export.

## Country split (multi-country campaigns)

```sql
SELECT geographic_view.country_criterion_id, geographic_view.location_type,
       metrics.cost_micros, metrics.impressions,
       metrics.biddable_app_install_conversions, metrics.biddable_app_post_install_conversions
FROM geographic_view
WHERE campaign.id = <ID> AND segments.date BETWEEN '<start>' AND '<end>'
```
Common country criterion IDs: US 2840, CA 2124, GB 2826, AU 2036, DE 2276, BR 2076,
MX 2484, FR 2250, JP 2392. Join each country with RevenueCat filtered to the same ISO code.

## Search terms (Search network insight)

App campaigns expose search-term *categories*, not raw terms, via
`campaign_search_term_insight` (verify availability with `get_resource_metadata`); fall
back to the UI "Search terms insights" export.
