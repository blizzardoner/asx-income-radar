# ASX Income Radar

Mobile-first PWA for broad Australian income-share screening, with source-backed annual income kept separate from historical cash distributions.

## What it tracks

- An explicitly labelled **ASX 300 proxy from Vanguard VAS official physical holdings**, refreshed from the official download endpoint. This is not the S&P official constituent list and its count is not forced to 300. Show the effective holdings date separately from retrieval time, source URL/hash, raw rows, exclusions and priced coverage.
- The first verified source snapshot has 302 positive-weight securities dated 30 September 2026. Preserve raw tickers, including `SGLLV`; `.AX` is the Yahoo market suffix, not an inferred alias. Zero-weight and unnamed non-positive rows are excluded transparently. VAS holdings older than 120 days or ambiguous/incomplete sources stop regeneration rather than manufacture membership.
- The previous 25 curated securities remain a separate watchlist. AFI and ARG are outside this dated VAS proxy and are labelled watch-only, not counted as index members.
- Five completed calendar years of historical cash distributions, a 12-calendar-month cash distribution yield (including specials), and recent average daily traded value. These are observed screening statistics, not audited sustainable dividends or guarantees. Calendar-year coverage requires at least 180 price sessions and observations near both year boundaries; missing years remain incomplete. Liquidity uses up to 60 sessions within the latest 90 calendar days and needs at least 20 observations; it is close-price × volume, not exact exchange turnover.
- Search, sector, minimum historical yield, distribution-year count, liquidity, verified annual basis and scope filters. Ranking is explicit and reproducible: distribution years, cash yield and liquidity, with separate sort options; no invented quality scores for newcomers.
- **Franking rate is known or unknown, never silently zero or 100%.** Reviewed annual fractions and component evidence live in `data/franking-disclosures.json`, linked to the identical annual ordinary period. Partial rates are cash-weighted across the ordinary annual components, not copied from the latest payment. Legacy universe assumptions are ignored. Unknown franking suppresses grossed-up and after-tax estimates; verified 0% remains distinct. Trust/stapled tax components require separate treatment, so simple after-tax estimates are unavailable for those structures.
- Dated prices, 52-week ranges and separately reviewed ordinary annual income. Only the curated watchlist has manually configured yield/stability thresholds; those assumptions are not whole-market ratings or investment recommendations.
- Statuses: `BUY`, `WATCH` (within 8% of the hard buy price), `WAIT`, `UNVERIFIED` (no usable annual income basis), and `STALE`.
- Side-by-side daily, one-week and one-year price-only changes, visible on desktop and mobile before expanding a card; each baseline price/date is shown in details.
- Search and expandable detail cards.
- Installable PWA shell with offline support.

## Refresh data

```bash
python scripts/update_market_data.py
```

Prices and dividend events come from Yahoo Finance's ten-year chart endpoint. Daily price change uses the previous **distinct exchange trading session's close**, not `chartPreviousClose` (the start of the requested chart range). Week/year targets are seven calendar days/the calendar anniversary before the **quote date**, not the refresh date. On a holiday/weekend use the latest available close on or before the target, at most seven days earlier. Missing/suspended history is unavailable, not zero or the first close after the target. Duplicate current-day bars are ignored. All three changes are price-only, excluding dividends; Yahoo's split-adjusted closes are not adjusted twice. Leap-day anniversaries use February 28.

`trailingCashDps` sums cash distributions by Australian ex-dividend date in the preceding **12 calendar months**, excluding the anniversary date and future events. This is not cash received by payment date. It can legitimately contain three semiannual payments when ex-dates shift.

`annualOrdinaryCashDps` comes **only** from `data/dividend-disclosures.json`, a reviewed snapshot of issuer/ASX disclosures for all 25 securities. Each record has an explicit fiscal period, reported versus guidance classification, ordinary annual amount, currency, announcement date, review-expiry date, source URLs, evidence and reconciled components. There is no default two/four-payment rule, no inferred frequency and no legacy DPS override or rolling-cash fallback. Quarterly, monthly, annual and semiannual payments all use the same source-backed annual-period contract. Specials and exceptional capital returns are excluded; ordinary trust tax-deferred/AMIT and LIC capital-gain tax components are not automatically treated as specials.

Most records use actual AUD distributions. BHP uses its disclosed USD annual ordinary amount, converted with a separately dated live `AUD=X` USD/AUD quote; this is a model currency conversion, not historical AUD cash received. FX older than seven days, missing/future/invalid/expired disclosures suppress the model yield and buy point. The client and alert script also recheck expiry and quote age, so a formerly fresh offline snapshot cannot keep its buy signal indefinitely.

## Develop and verify

```bash
npm install
npm test
python -m unittest discover -s scripts -p 'test_*.py'
npm run build
npm run preview -- --port 4321
```

Open `http://127.0.0.1:4321`.

## Monitoring

`scripts/check_alerts.py` refreshes prices and stays silent unless a share newly crosses into `BUY` or `WATCH`. Hermes runs the wrapper `asx_income_radar_watch.py` at 5:00 pm on weekdays and delivers non-empty alerts to the configured Discord channel.

## Model

```text
hard buy price = sustainable ordinary DPS / required cash yield
```

Sustainable DPS is the verified disclosed ordinary annual amount (or explicitly labelled ordinary guidance) multiplied by the security's conservative stability factor. Both the UI and alert script use `dividendBasis.annualDpsAud`; neither reconstructs an annual amount from event count. A historical fiscal-year amount is a screening reference, not a forecast or guaranteed sustainable payout. Cash yield is sustainable DPS / price; franking credits are only added in the separately labelled gross and after-tax estimates. Banks, REITs, infrastructure, LICs, operating companies, and cyclical producers use different required yields and risk assumptions.

Verified examples in the disclosure snapshot:

- [Suncorp FY26](https://www.suncorpgroup.com.au/news/news/fy26-results): the 62c final payment includes a 10c special; ordinary annual DPS is 17c + 52c = 69c before the stability haircut.
- [TPG FY25 results](https://announcements.asx.com.au/asxpdf/20260227/pdf/06wv74pm9z2zb1.pdf): FY25 ordinary annual DPS is 18c, excluding the 9c special and A$1.52 exceptional capital return; FY26 interim is not added to FY25.
- [Macquarie FY26](https://www.macquarie.com/au/en/about/news/2026/macquarie-group-fy26-result-announcement.html): the complete year ended March 2026 has A$7.00 ordinary DPS. The later FY27 interim must not be mixed with FY26 final.
- [AFIC FY27 guidance](https://www.afi.com.au/news/dividend-guidance-for-fy27-and-move-to-quarterly-dividends): quarterly payments include specials; the model uses the **27c ordinary** annual guidance, not the 37c total. [FY26 history](https://www.afi.com.au/dividend-history) documents the 2.5c special components. Guidance remains conditional on Board approval.

Pull requests run frontend tests, Python regressions and the production build without deploying. Main-branch deployments refresh live data; daily generated market JSON is not included in bug-fix commits.

## Maintaining annual disclosures

Daily refresh discovers ASX announcement headlines through the exchange website's anonymous backend. Exact-symbol entity lookup and paginated bulk date windows reconcile unique document IDs against the declared total. Sydney-local inclusive date boundaries are distinct from source UTC publication timestamps. New potentially relevant results/guidance/dividend/amendment/cancellation announcements after review make the old ordinary basis and franking rate **pending review**; missing/incomplete discovery also suppresses the old model. Discovery is not automatic PDF interpretation or automatic ordinary/special classification. Only announcement metadata and source links are delivered, not copied PDF bodies. ASX public access does not confer commercial republication rights; this app is for personal research.

Update the reviewed annual and franking snapshots using primary documents when a new full year, guidance or corporate action needs review. Preserve fiscal dates (including 52-week years), currencies and ordinary/special distinctions; never simply extend expiry or copy a trailing event sum. Reported snapshots expire 400 days after announcement; guidance expires 120 days after fiscal-period end. The UI and alerts independently recheck cached quote, FX, annual and discovery freshness. Static source snapshots are versioned; daily outputs remain outside fix PRs.

Market data embeds the generated universe and membership metadata in one versioned JSON snapshot so the client cannot combine different-date membership and prices. Regeneration is atomic and refuses proxy price coverage below 95%; individual failures stay visible rather than disappearing from the denominator. `.cache/asx-income-radar` retains source identities and short-lived charts locally and in scheduled Actions. Neither cache nor generated daily market JSON belongs in feature commits.

This is a screening tool, not personal financial advice.
