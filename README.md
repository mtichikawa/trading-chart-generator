# trading-chart-generator · T2

Reads live OHLCV data from T1's PostgreSQL and generates mplfinance candlestick PNGs with JSON metadata sidecars. Output consumed by T3's signal engine. 25/25 tests pass without a database connection.

---

## Trading Arc

| Repo | Role | Status |
|------|------|--------|
| T1 · crypto-data-pipeline | Live OHLCV ingestion · market event tagging | Shipped Mar 6 |
| **T2 · trading-chart-generator** | Candlestick PNGs + JSON sidecars · 25/25 tests | Shipped Mar 10 |
| T3 · trading-signal-engine | Technical indicators + FinBERT sentiment · 51/51 tests | Shipped Mar 16 |
| T4 · trading-backtester | Backtesting + parameter sweep · 72/72 tests | Shipped Mar 26 |
| T5 · trading-dashboard | Streamlit oversight UI · 8/8 tests | Shipped Mar 31 · [Live Demo](https://mtichikawa-trading.streamlit.app) |

---

## Architecture

```
T1 PostgreSQL (ohlcv table)
      │
      ▼
  OHLCVReader (src/db_reader.py)
      │  reads latest N candles for each pair/timeframe
      ▼
  ChartGenerator (src/chart_generator.py)
      │  mplfinance candlestick render
      ├──► BTC_USD_1h_<timestamp>.png    (chart image)
      └──► BTC_USD_1h_<timestamp>.json   (OHLCV sidecar)
```

The JSON sidecar is the handoff to T3. It contains OHLCV summary stats that T3's vision demo mode reads to produce deterministic chart analysis without an LLM API call.

---

## Output Format

Each run produces two files per pair/timeframe:

**Chart PNG** — mplfinance candlestick with volume panel, `charles` dark style, gold markers on near-event candles (CPI, NFP, FOMC tagged by T1).

**JSON sidecar:**
```json
{
  "pair": "BTC/USD",
  "timeframe": "1h",
  "generated_at": "2024-03-10T12:00:00+00:00",
  "candle_count": 200,
  "date_range": { "start": "...", "end": "..." },
  "last_close": 68432.5,
  "price_change_pct": 3.14,
  "chart_path": "/path/to/BTC_USD_1h.png"
}
```

---

## Project Structure

```
trading-chart-generator/
├── src/
│   ├── config.py          # ChartConfig dataclass (output dirs, pairs, timeframes)
│   ├── db_reader.py       # OHLCVReader: reads from T1's PostgreSQL via SQLAlchemy
│   ├── chart_generator.py # ChartGenerator: renders PNG + writes JSON sidecar
│   └── run.py             # CLI entry point
├── tests/
│   └── test_chart_generator.py  # 25 tests, synthetic data, no DB required
├── examples/
│   └── quick_demo.py      # Standalone demo — no database needed
└── requirements.txt
```

---

## Setup

```bash
cd trading-chart-generator
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Standalone demo — no database required
python examples/quick_demo.py

# Live mode with T1 database
# Set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD env vars (same as T1 .env)
python src/run.py

# Options
python src/run.py --pairs BTC/USD ETH/USD --timeframes 1h 4h --limit 100
```

## Tests

```bash
pytest tests/ -v
# 25/25 — all run without DB or network access
```

---

## Contact

Mike Ichikawa · [projects.ichikawa@gmail.com](mailto:projects.ichikawa@gmail.com) · [mtichikawa.github.io](https://mtichikawa.github.io)
