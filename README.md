# trading-chart-generator (T2)

Part of the trading system arc. T2 reads live OHLCV candle data from T1's
PostgreSQL database and produces mplfinance candlestick PNG charts with JSON
metadata sidecars for every configured pair/timeframe combination.

## Trading Arc Position

```
T1 crypto-data-pipeline  →  T2 trading-chart-generator  →  T3 trading-signal-engine  →  …
(live OHLCV ingest)          (chart PNGs + JSON sidecars)   (technical indicators + FinBERT)
```

T2 sits between T1's data ingest and T3's signal engine. T3 uses technical
indicators (EMA/RSI/MACD/Bollinger Bands) fused with local FinBERT sentiment
analysis for signal scoring — no paid API calls. A mock vision demo mode
showcases chart-reading capability using deterministic sidecar data.

## Project Layout

```
trading-chart-generator/
  src/
    config.py           — ChartConfig dataclass (output dirs, pairs, timeframes)
    db_reader.py        — OHLCVReader: reads from T1's PostgreSQL via SQLAlchemy
    chart_generator.py  — ChartGenerator: renders PNG + writes JSON sidecar
    run.py              — CLI entry point
  tests/
    test_chart_generator.py  — pytest tests (synthetic data, no DB)
  examples/
    quick_demo.py       — standalone demo (no DB required)
  charts/               — default output directory for PNGs and JSON sidecars
  requirements.txt
```

## Setup

```bash
cd projects-hub/trading-chart-generator
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Quick Demo (no database required)

Generates 30 candles of synthetic BTC/USD 1h data, renders a chart, and prints
the JSON sidecar. Runs completely offline.

```bash
python examples/quick_demo.py
```

The PNG and JSON are saved to `charts/`.

## Running Tests

```bash
pytest tests/ -v
```

All tests use synthetic DataFrames and pytest's `tmp_path` fixture. No
database connection is required.

## Live Usage with T1

Ensure T1's PostgreSQL database is running and the following environment
variables are set (matching T1's `.env`):

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=crypto_pipeline
DB_USER=postgres
DB_PASSWORD=your_password
```

Then generate charts for all default pairs and timeframes:

```bash
python src/run.py
```

### CLI Options

```
python src/run.py --help

  --pairs BTC/USD ETH/USD     Trading pairs to chart (default: BTC/USD ETH/USD SOL/USD)
  --timeframes 1h 4h 1d       Timeframes to chart (default: 1h 4h 1d)
  --limit 200                 Max candles per chart (default: 200)
  --output-dir charts/        Output directory (default: charts/)
```

### Examples

```bash
# Chart only BTC/USD on the 1-hour and 4-hour timeframes:
python src/run.py --pairs BTC/USD --timeframes 1h 4h

# Chart all default pairs with 100-candle windows, custom output dir:
python src/run.py --limit 100 --output-dir /tmp/charts
```

## Output Format

Each generation run produces two files per pair/timeframe:

| File | Description |
|------|-------------|
| `BTC_USD_1h_20240310T120000Z.png` | mplfinance candlestick chart (14×8 inches) |
| `BTC_USD_1h_20240310T120000Z.json` | Metadata sidecar (see below) |

### JSON Sidecar Fields

```json
{
  "pair": "BTC/USD",
  "timeframe": "1h",
  "generated_at": "2024-03-10T12:00:00+00:00",
  "candle_count": 200,
  "date_range": {
    "start": "2024-02-25T16:00:00+00:00",
    "end":   "2024-03-10T11:00:00+00:00"
  },
  "last_close": 68432.5,
  "price_change_pct": 3.14,
  "chart_path": "/absolute/path/to/BTC_USD_1h_20240310T120000Z.png"
}
```

## Chart Features

- **Style**: `charles` (dark background, coloured candles)
- **Volume panel**: rendered below the candlestick chart
- **Near-event markers**: candles flagged by T1's event tagger (`near_event=True`)
  receive gold triangle markers, making macro events (CPI, NFP, FOMC) visible
  directly on the chart
