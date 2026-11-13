# ASX Income Radar

Mobile-first PWA for screening Australian income shares by **quality-adjusted buy value**, not headline yield alone.

## What it tracks

- 25 curated ASX income shares across banks, insurance, telecom, infrastructure, REITs, resources, LICs, utilities, and staples.
- Dated market price, 52-week range, trailing cash distributions, conservative sustainable-DPS estimate, cash yield, franking-adjusted gross yield, and a hard buy price.
- Statuses: `BUY`, `WATCH` (within 8% of the hard buy price), `WAIT`, and `STALE`.
- Search and expandable detail cards.
- Installable PWA shell with offline support.

## Refresh data

```bash
python scripts/update_market_data.py
```

Prices and dividend events come from Yahoo Finance's chart endpoint. Daily price change uses the previous **distinct exchange trading session's close**, not `chartPreviousClose` (the start of the requested chart range). Duplicate current-day bars are ignored for this baseline. The 52-week price-only change is labelled separately and excludes dividends.

`trailingCashDps` sums cash distributions by Australian ex-dividend date in the preceding **12 calendar months**, excluding the anniversary date and future events. This is not cash received by payment date. It can legitimately contain three semiannual payments when ex-dates shift.

`annualOrdinaryCashDps` excludes verified special components (`specialDividends`, keyed by Australian ex-date) and caps the rolling events to one normal annual payment cycle: two payments by default, or `paymentsPerYear` for other schedules. No missing payment is annualised. Yahoo split-adjusted historical prices and dividend amounts are not adjusted a second time. Company announcements remain the final source for franking, tax character, payout coverage, and guidance; new special distributions require a reviewed configuration update, not an amount-based guess.

## Develop and verify

```bash
npm install
npm test
python -m unittest scripts/test_update_market_data.py scripts/test_check_alerts.py
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

Sustainable DPS is either an explicit ordinary-dividend override or `annualOrdinaryCashDps` multiplied by a conservative stability factor. Both the UI and alert script use this same basis. Cash yield is sustainable DPS / price; franking credits are only added in the separately labelled gross and after-tax estimates. Banks, REITs, infrastructure, LICs, operating companies, and cyclical producers use different required yields and risk assumptions.

Verified exceptions in the universe:

- [Suncorp FY26](https://www.suncorpgroup.com.au/news/news/fy26-results): the 62c final payment includes a 10c special; ordinary annual DPS is 17c + 52c = 69c before the stability haircut.
- [TPG dividend history](https://www.tpgtelecom.com.au/investor-relations/dividends): the 14 November 2025 9c special is excluded if the upstream feed includes it; capital returns are not treated as ordinary income.
- [AFIC FY27 guidance](https://www.afi.com.au/news/dividend-guidance-for-fy27-and-move-to-quarterly-dividends): quarterly payments include specials; the model uses the **27c ordinary** annual guidance, not the 37c total. [FY26 history](https://www.afi.com.au/dividend-history) documents the 2.5c special components. Guidance remains conditional on Board approval.

Pull requests run frontend tests, Python regressions and the production build without deploying. Main-branch deployments refresh live data; daily generated market JSON is not included in bug-fix commits.

This is a screening tool, not personal financial advice.
