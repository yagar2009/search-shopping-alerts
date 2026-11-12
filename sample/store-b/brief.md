# Store B (doors & windows): search & shopping brief

**Status:** amber  
**Headline:** Organic search is growing fast (40 clicks vs 5), but GA4 shows no key events and Direct traffic halved, so tracking needs checking first.

## Alerts

### [high] No key events recorded and cart steps falling
- Source: ga4
- Evidence: keyEvents 0 vs 0. addToCarts 3 vs 11 (-72.7%). checkouts 0 vs 4 (-100%). engagedSessions 74 vs 95 (-22.1%).
- Likely cause: Key events look not configured, since the count is 0 in both periods. The fall in carts and checkouts is on small numbers, so it may be noise or a broken purchase funnel. The data cannot tell which.
- Next action: Developer tests the full path on the live site (product, add to cart, checkout) and confirms in GA4 DebugView that add_to_cart, begin_checkout and purchase fire. Then mark the right events as key events. (owner: developer)

### [high] Direct sessions down 52.7% while Organic Search jumped
- Source: ga4
- Evidence: Direct 86 vs 182 (-52.7%). Organic Search 86 vs 8. Total sessions 184 vs 194 (-5.2%). Landing page /dveri/mizhkimnatni-dveri 1 vs 33 sessions, /dveri 1 vs 14.
- Likely cause: Total traffic is flat, so this is a shift between channels, not a loss. Direct was probably inflated before by untagged traffic, bots or a past campaign aimed at the interior door pages. Some of it may also be a change in how GA4 attributes visits. Unclear which.
- Next action: Analyst checks GA4 Direct sessions by day, device and country for 17 Sep to 11 Nov to find when the 33-session door page traffic stopped. Ask the client about any ads, emails or campaigns in September and early October. (owner: account_manager)

### [medium] Impressions up 8x but average position fell to 31.6 and new queries get no clicks
- Source: search_console
- Evidence: Clicks 40 vs 5. Impressions 3758 vs 405. Avg position 31.6 vs 18.2. Top new queries have 0 clicks at positions 35.5 to 73.2, for example 'столы компьютерные белые' (white computer desks) 39 impressions, 'мебель для офиса цена' (office furniture price) 14 impressions at 63.6.
- Likely cause: The site is now indexed for many new long tail queries on page 3 or lower. This pulls the average position down. The growth is real but still shallow.
- Next action: SEO lists the pages that rank for the new furniture and blind queries and checks they have matching titles, headings and category copy. (owner: seo)

### [low] Four pages that had clicks last period now have none
- Source: search_console
- Evidence: Each of 4 pages went from 1 click to 0. They include /ru/dveri/vkhidni-dveri/portala-trio-lait-adel-spyl-koniachnyi-chkf/ (pos 2 before) and /en/kontakty/ (4.3 before).
- Likely cause: Single clicks, so most likely noise. No evidence of a real loss.
- Next action: SEO checks that these 4 URLs return 200 and are indexed. No other action unless they stay at 0 next week. (owner: seo)

### [low] Merchant Center data missing from this report
- Source: cross_source
- Evidence: No merchant_center block in the signals. GA4 shows Organic Shopping 3 sessions vs 0.
- Likely cause: Merchant Center is not connected to the weekly report. Feed health cannot be judged.
- Next action: Feed specialist connects the Merchant Center account to the report, or confirms the store does not use it. (owner: feed_specialist)

## Opportunities

- **Push 'furniture for kids' onto page 1 clicks**: 21 impressions vs 3, position 8 (same as before), 0 clicks. Next: Improve the title and intro of the kids furniture category and add internal links to it from the home page.
- **Build a page set for white computer desks**: Four spelling variants appear as new queries: 'столы компьютерные белые' 39 impressions, 'компьютерный стол белый' 15, 'белый стол для компьютера' 15, all at positions 35.5 to 47. Next: Make one strong category page for white computer desks that covers all variants, and check the products are in the right category.
- **Target office furniture and blinds queries**: 'купить мебель для офиса украина' (buy office furniture Ukraine) 17 impressions, 'жалюзи день ночь днепр' (day-night blinds Dnipro) 12 impressions at position 40, 'жалюзи на кухню' (kitchen blinds) 13. Next: Check whether category pages exist for these topics and add them to the content plan if not.
- **Brand query is gaining**: Store name query: position 4.6 vs 9.5, 17 impressions vs 2. Next: Make sure the home page title and snippet show the main product lines.

## Note for the client

Your site is showing up in Google much more than last month. Clicks from search went from 5 to 40, and organic visits in our analytics went from 8 to 86. Most of the new visibility is on searches where the site still ranks low, so we will work on those pages next. We also found that the analytics does not record purchases or other key actions, and we are checking this with the developer this week. Until it is fixed we cannot measure orders from this traffic.

## Rule-based alerts (before Claude)

- high: ga4 / sessions:Direct: 86 vs 182 (-53%)
