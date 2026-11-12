# Store C (backup power): search & shopping brief

**Status:** amber  
**Headline:** Search visibility started this period (1,138 impressions, 18 clicks from zero), but GA4 shows 0 key events despite 2 checkouts.

## Alerts

### [medium] Key events at 0 although checkouts were recorded
- Source: ga4
- Evidence: keyEvents 0 (prev 0); checkouts 2 (prev 0); addToCarts 1 (prev 2); sessions 77 (prev 12)
- Likely cause: Purchase and checkout key events are probably not marked as key events in GA4, or the purchase event is not firing. Order volume is not in the data, so this is unconfirmed.
- Next action: Place a test order and check in GA4 DebugView that add_to_cart, begin_checkout and purchase fire and are marked as key events. (owner: developer)

### [low] Part of the traffic has no channel
- Source: ga4
- Evidence: Unassigned 17 sessions (prev 2) of 77 total; Direct 38 sessions (prev 10)
- Likely cause: Missing UTM tags or consent/redirect issues stripping the source. Unclear from this data.
- Next action: Check the landing pages and referrers of Unassigned sessions in GA4 and confirm that any paid or email links carry UTM tags. (owner: developer)

### [low] No Merchant Center data in this report
- Source: merchant_center
- Evidence: No merchant_center section in the input
- Likely cause: Source not connected to the weekly report. Account status and product disapprovals cannot be checked.
- Next action: Connect Merchant Center to the report, or confirm manually that the account is active and has no disapproved products. (owner: feed_specialist)

## Opportunities

- **Hybrid solar inverter queries sit on page 5 or 6**: гібридний інвертор для сонячних панелей [hybrid inverter for solar panels] 34 impr, pos 50.7; гібридний сонячний інвертор [hybrid solar inverter] 31 impr, pos 51.6; four more word-order variants with 20 to 26 impr each, pos 56.7 to 56.8 Next: Check which page ranks for these. Improve the hybrid inverter category page (title, H1, intro text, internal links) to target the main variant.
- **Product-code and brand queries rank in the top 8 but get 0 clicks**: ai68000 23 impr, pos 4.1; ai55430 22 impr, pos 7.7; ai25889 19 impr, pos 5.7; ai59155 19 impr, pos 7.5; ecoflow для резервного живлення будинку ціна [ecoflow for home backup power price] 21 impr, pos 6.9. All 0 clicks Next: Review titles and meta descriptions of these product pages: include the model code, price and stock status. Check the snippet in search results.
- **Organic Search is now a real channel**: Organic Search 22 sessions (prev 0); Search Console clicks 18 (prev 0); avg position 38.0 Next: Confirm why the previous period showed zero (new site, new indexing or new Search Console connection) and treat this period as the baseline.

## Note for the client

Your site started appearing in Google search this period. It had 1,138 impressions and 18 clicks, and none were recorded in the previous period. Site visits rose to 77 sessions from 12, but the numbers are still small, so we treat this as a starting baseline. We are checking that purchases and checkouts are tracked correctly, because the reports show no recorded conversions yet. Next we will improve the pages for hybrid solar inverters and for the product pages that already show in the top 8 but get no clicks.

## Rule-based alerts (before Claude)

