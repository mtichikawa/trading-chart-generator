"""
examples/quick_demo.py — Zero-dependency demo for trading-chart-generator (T2).

Generates 30 candles of synthetic BTC/USD 1h OHLCV data using a NumPy
random walk, renders a candlestick PNG with mplfinance, writes a JSON sidecar,
and prints the sidecar contents.

No T1 database, no environment variables, no API keys required.

Usage
-----
::

    cd projects-hub/trading-chart-generator
    source venv/bin/activate
    python examples/quick_demo.py
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

# Allow bare imports from src/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator  # noqa: E402
from config import ChartConfig  # noqa: E402


def build_synthetic_ohlcv(
    n: int = 30,
    start_price: float = 65_000.0,
    start: str = "2024-03-01 00:00:00",
    freq: str = "1h",
    seed: int = 7,
) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame using a geometric random walk.

    The price process starts at *start_price* and evolves via small log-normal
    returns.  Each candle's open, high, low, close are derived from the simulated
    mid-price with added noise so the OHLC relationship holds
    (high ≥ max(open, close), low ≤ min(open, close)).

    Args:
        n: Number of candles to generate.
        start_price: Starting price for the random walk.
        start: ISO timestamp for the first candle's open_time.
        freq: pandas frequency string for the DatetimeIndex (e.g. ``"1h"``).
        seed: NumPy random seed for reproducibility.

    Returns:
        DataFrame indexed by a UTC-aware DatetimeIndex with columns
        ``open``, ``high``, ``low``, ``close``, ``volume``, ``near_event``,
        ``event_type``.
    """
    rng = np.random.default_rng(seed)

    # Geometric random walk: daily-ish volatility spread over hourly candles.
    returns = rng.normal(loc=0.0001, scale=0.005, size=n)
    mid_prices = start_price * np.cumprod(1 + returns)

    # Per-candle spread as a random fraction of the mid-price.
    spread = mid_prices * rng.uniform(0.002, 0.008, size=n)

    open_ = mid_prices + rng.uniform(-0.5, 0.5, size=n) * spread
    close = mid_prices + rng.uniform(-0.5, 0.5, size=n) * spread
    high = np.maximum(open_, close) + rng.uniform(0, 1, size=n) * spread
    low = np.minimum(open_, close) - rng.uniform(0, 1, size=n) * spread
    volume = rng.uniform(5_000, 80_000, size=n)

    # Mark three candles as "near event" to demo the marker rendering.
    near_event = np.zeros(n, dtype=bool)
    event_indices = [5, 14, 22]
    for idx in event_indices:
        if idx < n:
            near_event[idx] = True

    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "near_event": near_event,
            "event_type": np.where(near_event, "FOMC", None),
        },
        index=index,
    )

    return df


def main() -> None:
    """Run the quick demo: generate a chart and print the JSON sidecar."""
    output_dir = Path(__file__).resolve().parents[1] / "charts"
    config = ChartConfig(output_dir=output_dir)
    generator = ChartGenerator(output_dir=output_dir, config=config)

    print("=" * 60)
    print("  T2 trading-chart-generator — quick demo")
    print("=" * 60)
    print(f"  Output directory : {output_dir}")
    print()

    df = build_synthetic_ohlcv(n=30)
    print(f"  Synthetic data   : {len(df)} candles of BTC/USD 1h")
    print(f"  Date range       : {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  Price range      : ${df['low'].min():,.2f} – ${df['high'].max():,.2f}")
    print()

    print("  Generating chart …")
    png_path, json_path = generator.generate(df, "BTC/USD", "1h", title="BTC/USD 1h — Quick Demo")

    print(f"  PNG  saved : {png_path}")
    print(f"  JSON saved : {json_path}")
    print()

    sidecar = json.loads(json_path.read_text(encoding="utf-8"))
    print("  JSON sidecar contents:")
    print("  " + "-" * 40)
    for key, value in sidecar.items():
        print(f"    {key:<20} {value}")
    print("  " + "-" * 40)
    print()
    print("  Demo complete.  Open the PNG to view the chart.")
    print("=" * 60)


if __name__ == "__main__":
    main()
