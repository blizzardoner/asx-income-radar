# ASX Income Radar

Mobile-first PWA for screening Australian income shares by **quality-adjusted buy value**, not headline yield alone.

## What it tracks

- 25 curated ASX income shares across banks, insurance, telecom, infrastructure, REITs, resources, LICs, utilities, and staples.
- Dated market price, 52-week range, trailing cash distributions, conservative sustainable-DPS estimate, cash yield, franking-adjusted gross yield, and a hard buy price.
- Statuses: `BUY`, `WATCH` (within 8% of the hard buy price), `WAIT`, `UNVERIFIED` (no usable annual income basis), and `STALE`.
- Side-by-side daily, one-week and one-year price-only changes, visible on desktop and mobile before expanding a card; each baseline price/date is shown in details.
- Search and expandable detail cards.
- Installable PWA shell with offline support.

## Refresh data

```bash
python scripts/update_market_data.py
```

Prices and dividend events come from Yahoo Finance's chart endpoint. Daily price change uses the previous **distinct exchange trading session's close**, not `chartPreviousClose` (the start of the requested chart range). Week/year targets are seven calendar days/the calendar anniversary before the **quote date**, not the refresh date. On a holiday/weekend use the latest available close on or before the target, at most seven days earlier. Missing/suspended history is unavailable, not zero or the first close after the target. Duplicate current-day bars are ignored. All three changes are price-only, excluding dividends; Yahoo's split-adjusted closes are not adjusted twice. Leap-day anniversaries use February 28.

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

Daily refresh updates prices/events/FX; it does **not** claim to automatically discover new financial reports or classify special dividends. Update the reviewed disclosure snapshot when an issuer publishes a new complete year, revises its ordinary guidance or announces relevant corporate actions. Use primary issuer/ASX documents; preserve actual fiscal dates (including 52-week fiscal years), currency and ordinary/special distinction. Do not simply extend expiry or copy a trailing event sum. Reported snapshots expire 400 days after announcement; guidance snapshots expire 120 days after the stated fiscal-period end. These are review cutoffs, not an assurance that nothing changes sooner. On expiry the app shows unverified income and stops buy/watch alerts until the record is reviewed. Static source snapshots are versioned; daily market outputs remain outside fix PRs.

This is a screening tool, not personal financial advice.
