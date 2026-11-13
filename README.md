# recession_forecast

Four-prong recession signal tracker with an NBER backtest. A nightly GitHub Action pulls FRED and Federal Reserve data,
computes the signals, commits `docs/data/signals.json`, and deploys the static page in `docs/` to GitHub Pages.

Prongs: yield curve (T10Y3M), Sahm rule (SAHMREALTIME), regional Fed manufacturing (Philly/NY/Dallas), credit
(excess bond premium or SLOOS DRTSCILM). Watch: building permits YoY. Every threshold, window and source lives in
`config/signals.json`. No ISM or Moody's data (license).

## Run
```
export FRED_API_KEY=...            # free key from FRED
python -m pipeline.smoke           # step 0: every source present, non-empty, schema unchanged, fresh
python -m pipeline.build           # writes docs/data/signals.json
python -m http.server -d docs      # open http://localhost:8000
```
Offline: `RF_RAW_DIR=tests/fixtures python -m pipeline.build` (FRED-format CSVs named `<SERIES>.csv`, plus `EBP.csv`).

## Test
```
pip install pytest && pytest -q && node --test tests/*.mjs
```

## Deployed
- Live: https://leftbrain847.github.io/recession_forecast/ (after the first nightly run)
- Day snapshot: `2026-11-12 - recession_forecast` (frozen; never edited)

## Ship a sprint day
Set `project` in `sprint.config.json`, then freeze the day's page:
```
node scripts/snapshot.mjs <page.html>            # private
node scripts/snapshot.mjs <page.html> --public   # opts in to the public sprint site
```
Commit `snapshots/` to `main` (via PR). The index's nightly refresh logs the day automatically; public pages still have to pass its UAT and secret scan.
