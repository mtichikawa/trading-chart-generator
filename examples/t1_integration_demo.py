"""
examples/t1_integration_demo.py — T1 → T2 integration demo.

Demonstrates the complete data flow from crypto-data-pipeline (T1) into
trading-chart-generator (T2):

    T1 (OHLCV ingest via ccxt/Kraken)  →  PostgreSQL  →  T2 (OHLCVReader)  →  Charts

This script works in two modes:

1. **Mock mode** (default) — uses MockOHLCVReader to simulate T1's database
   output without requiring PostgreSQL. Safe for CI, demos, and portfolio review.

2. **Live mode** (--live flag) — connects to T1's actual PostgreSQL database
   via OHLCVReader. Requires T1 to be running and the DB populated.

Usage
-----
::

    cd projects-hub/trading-chart-generator
    source venv/bin/activate

    # Mock mode (no database required):
    python examples/t1_integration_demo.py

    # Live mode (requires T1 PostgreSQL with data):
    python examples/t1_integration_demo.py --live

    # Specify pairs/timeframes:
    python examples/t1_integration_demo.py --pairs BTC/USD ETH/USD --timeframes 1h 4h

Output
------
Generates candlestick PNGs and JSON sidecar files in ``charts/integration/``.
Each chart shows OHLCV price action with event markers (gold triangles) on
candles flagged by T1's market-event tagger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow bare imports from src/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator  # noqa: E402
from config import ChartConfig  # noqa: E402
from mock_reader import MockOHLCVReader  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="T1 → T2 integration demo: generate charts from T1 OHLCV data."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live OHLCVReader (requires T1 PostgreSQL). Default: mock mode.",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=["BTC/USD", "ETH/USD", "SOL/USD"],
        help="Trading pairs to chart (default: BTC/USD ETH/USD SOL/USD).",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1h", "4h"],
        help="Timeframes to chart (default: 1h 4h).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of candles per chart (default: 100).",
    )
    return parser.parse_args()


def get_reader(live: bool):
    """Return either the live OHLCVReader or MockOHLCVReader.

    Args:
        live: If True, import and instantiate the real OHLCVReader
              (requires psycopg2 and a running PostgreSQL instance).

    Returns:
        A reader object with fetch_candles/fetch_with_events/list_available.
    """
    if live:
        from db_reader import OHLCVReader
        print("  Mode: LIVE (connecting to T1 PostgreSQL)")
        return OHLCVReader()
    else:
        print("  Mode: MOCK (synthetic data simulating T1 output)")
        return MockOHLCVReader(seed=2026)


def main() -> None:
    """Run the T1 → T2 integration demo."""
    args = parse_args()

    output_dir = Path(__file__).resolve().parents[1] / "charts" / "integration"
    config = ChartConfig(
        output_dir=output_dir,
        candle_limit=args.limit,
        default_pairs=args.pairs,
        default_timeframes=args.timeframes,
    )
    generator = ChartGenerator(output_dir=output_dir, config=config)

    print("=" * 65)
    print("  T1 → T2 Integration Demo")
    print("  crypto-data-pipeline → trading-chart-generator")
    print("=" * 65)

    reader = get_reader(args.live)
    print()

    # Show available data.
    available = reader.list_available()
    print("  Available data from T1:")
    for pair, timeframes in available.items():
        print(f"    {pair:<10} → {', '.join(timeframes)}")
    print()

    # Generate charts for each pair/timeframe.
    print(f"  Generating charts for {len(args.pairs)} pairs x {len(args.timeframes)} timeframes...")
    print(f"  Candle limit: {args.limit}")
    print()

    results = generator.generate_all(
        reader,
        pairs=args.pairs,
        timeframes=args.timeframes,
    )

    print(f"  Generated {len(results)} chart(s):")
    print()

    for png_path, json_path in results:
        sidecar = json.loads(json_path.read_text(encoding="utf-8"))
        print(f"  {sidecar['pair']} {sidecar['timeframe']}")
        print(f"    PNG:    {png_path.name}")
        print(f"    Candles: {sidecar['candle_count']}")
        print(f"    Range:   {sidecar['date_range']['start'][:10]} → {sidecar['date_range']['end'][:10]}")
        print(f"    Last:    ${sidecar['last_close']:,.2f} ({sidecar['price_change_pct']:+.2f}%)")
        print()

    print("  " + "-" * 50)
    print(f"  Output directory: {output_dir}")
    print()
    print("  Data flow:")
    print("    T1 ccxt/Kraken → PostgreSQL → OHLCVReader → T2 ChartGenerator → PNG + JSON")
    print()
    if not args.live:
        print("  (Run with --live to use real T1 database data)")
    print("=" * 65)


if __name__ == "__main__":
    main()
