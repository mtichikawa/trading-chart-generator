"""
src/run.py — CLI entry point for T2: trading-chart-generator.

Connects to T1's PostgreSQL database via :class:`~db_reader.OHLCVReader`,
generates mplfinance candlestick PNGs and JSON sidecars for each requested
pair/timeframe combination, and prints a summary table.

Usage
-----
::

    # Default pairs (BTC/USD ETH/USD SOL/USD) and timeframes (1h 4h 1d):
    python src/run.py

    # Custom pairs and timeframes:
    python src/run.py --pairs BTC/USD ETH/USD --timeframes 1h 4h

    # Limit to 100 candles per chart:
    python src/run.py --limit 100

    # Write charts to a custom directory:
    python src/run.py --output-dir /tmp/charts
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import ChartConfig
from chart_generator import ChartGenerator
from db_reader import OHLCVReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]`` when *None*.

    Returns:
        Parsed namespace with attributes ``pairs``, ``timeframes``,
        ``limit``, and ``output_dir``.
    """
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Generate mplfinance candlestick charts from T1 OHLCV data.",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=None,
        metavar="PAIR",
        help=(
            "Trading pairs to chart (e.g. BTC/USD ETH/USD). "
            "Defaults to BTC/USD ETH/USD SOL/USD."
        ),
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=None,
        metavar="TF",
        help=(
            "Timeframes to chart (e.g. 1h 4h 1d). "
            "Defaults to 1h 4h 1d."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        metavar="N",
        help="Maximum candles per chart (default: 200).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("charts"),
        metavar="DIR",
        help="Directory for PNG and JSON output (default: charts/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, generate charts, print summary.

    Args:
        argv: Optional argument list for programmatic invocation.

    Returns:
        Exit code: 0 on success, 1 if no charts were generated.
    """
    args = parse_args(argv)

    config = ChartConfig(
        output_dir=args.output_dir,
        candle_limit=args.limit,
    )
    if args.pairs:
        config.default_pairs = args.pairs
    if args.timeframes:
        config.default_timeframes = args.timeframes

    logger.info("Connecting to T1 PostgreSQL database …")
    try:
        reader = OHLCVReader()
    except Exception as exc:
        logger.error("Failed to build DB engine: %s", exc)
        return 1

    available = {}
    try:
        available = reader.list_available()
        if available:
            logger.info(
                "Available data in DB: %s",
                {p: tfs for p, tfs in available.items()},
            )
        else:
            logger.warning("No OHLCV data found in the database.")
    except Exception as exc:
        logger.warning("Could not query available pairs: %s", exc)

    generator = ChartGenerator(output_dir=config.output_dir, config=config)

    logger.info(
        "Generating charts for pairs=%s timeframes=%s limit=%d …",
        config.default_pairs,
        config.default_timeframes,
        config.candle_limit,
    )

    results = generator.generate_all(
        reader,
        pairs=config.default_pairs,
        timeframes=config.default_timeframes,
    )

    if not results:
        logger.error("No charts were generated.  Check DB connection and data.")
        return 1

    # Print summary table.
    print("\n" + "=" * 60)
    print(f"  T2 Chart Generator — {len(results)} chart(s) generated")
    print("=" * 60)
    for png_path, json_path in results:
        print(f"  PNG : {png_path}")
        print(f"  JSON: {json_path}")
        print()
    print(f"Output directory: {config.output_dir.resolve()}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
