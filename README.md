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

Prices and dividend events come from Yahoo Finance's chart endpoint. The app deliberately applies security-type stability haircuts and explicit overrides for known special-dividend cases. Company announcements remain the final source for franking, tax character, payout coverage, and guidance.

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

Sustainable DPS is either an explicit ordinary-dividend override or trailing cash DPS multiplied by a conservative stability factor. Banks, REITs, infrastructure, LICs, operating companies, and cyclical producers use different required yields and risk assumptions.

This is a screening tool, not personal financial advice.
