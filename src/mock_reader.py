"""
src/mock_reader.py — Mock T1 reader that simulates live OHLCV data from crypto-data-pipeline.

Provides the same interface as OHLCVReader (fetch_candles, fetch_with_events,
list_available) but generates realistic synthetic data using a random walk.
This enables T2 demos, CI tests, and integration examples without a live
PostgreSQL database or T1 running.

The synthetic data mimics T1's output: proper OHLCV relationships, UTC
timestamps, and optional event-tagging columns (near_event, event_type,
mins_from_event).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd


# Realistic price anchors for common crypto pairs (approximate Apr 2026 levels).
_PRICE_ANCHORS: dict[str, float] = {
    "BTC/USD": 87_000.0,
    "ETH/USD": 3_200.0,
    "SOL/USD": 165.0,
}

# Timeframe to pandas frequency mapping.
_TF_TO_FREQ: dict[str, str] = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}


class MockOHLCVReader:
    """Drop-in replacement for OHLCVReader that returns synthetic data.

    Implements the same public methods as ``db_reader.OHLCVReader``:

    * :meth:`fetch_candles` — OHLCV without event columns
    * :meth:`fetch_with_events` — OHLCV + event annotation columns
    * :meth:`list_available` — available pair/timeframe combinations

    Args:
        pairs: Trading pairs to serve. Defaults to BTC/USD, ETH/USD, SOL/USD.
        timeframes: Timeframes to serve. Defaults to T1's standard set.
        seed: NumPy random seed for reproducible output.
        event_probability: Fraction of candles marked as near_event (0.0-1.0).
    """

    def __init__(
        self,
        pairs: Optional[list[str]] = None,
        timeframes: Optional[list[str]] = None,
        seed: int = 42,
        event_probability: float = 0.05,
    ) -> None:
        self.pairs = pairs or ["BTC/USD", "ETH/USD", "SOL/USD"]
        self.timeframes = timeframes or ["5m", "15m", "1h", "4h", "1d"]
        self.seed = seed
        self.event_probability = event_probability

    def fetch_candles(
        self,
        pair: str,
        timeframe: str,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch synthetic OHLCV candles (no event columns).

        Args:
            pair: Trading pair, e.g. "BTC/USD".
            timeframe: Candle timeframe, e.g. "1h".
            limit: Number of candles to return.

        Returns:
            DataFrame indexed by open_time with columns:
            open, high, low, close, volume.
        """
        return self._generate_ohlcv(pair, timeframe, limit, include_events=False)

    def fetch_with_events(
        self,
        pair: str,
        timeframe: str,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch synthetic OHLCV candles with event annotation columns.

        Matches the interface of OHLCVReader.fetch_with_events(). Some candles
        are randomly marked as near_event to simulate T1's event tagger.

        Args:
            pair: Trading pair, e.g. "ETH/USD".
            timeframe: Candle timeframe, e.g. "4h".
            limit: Number of candles to return.

        Returns:
            DataFrame indexed by open_time with columns:
            open, high, low, close, volume, near_event, event_type, mins_from_event.
        """
        return self._generate_ohlcv(pair, timeframe, limit, include_events=True)

    def list_available(self) -> dict[str, list[str]]:
        """Return available pair/timeframe combinations.

        Returns:
            Dict mapping each pair to its sorted list of timeframes.
        """
        return {pair: sorted(self.timeframes) for pair in sorted(self.pairs)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_ohlcv(
        self,
        pair: str,
        timeframe: str,
        limit: int,
        include_events: bool,
    ) -> pd.DataFrame:
        """Generate a synthetic OHLCV DataFrame mimicking T1's output.

        Uses a geometric random walk with volatility scaled to the timeframe.
        The seed is combined with pair + timeframe so different combinations
        produce different but reproducible data.
        """
        # Deterministic seed per pair/timeframe combination.
        combo_seed = self.seed + hash(f"{pair}_{timeframe}") % 10_000
        rng = np.random.default_rng(combo_seed)

        start_price = _PRICE_ANCHORS.get(pair, 1_000.0)
        freq = _TF_TO_FREQ.get(timeframe, "1h")

        # Scale volatility by timeframe (daily candles are noisier than 5m).
        vol_scale = {"5m": 0.001, "15m": 0.0015, "1h": 0.003, "4h": 0.006, "1d": 0.012}
        sigma = vol_scale.get(timeframe, 0.003)

        # Random walk.
        returns = rng.normal(loc=0.0001, scale=sigma, size=limit)
        mid_prices = start_price * np.cumprod(1 + returns)

        # Build OHLC from mid prices with realistic spread.
        spread = mid_prices * rng.uniform(0.001, 0.005, size=limit)
        open_ = mid_prices + rng.uniform(-0.3, 0.3, size=limit) * spread
        close = mid_prices + rng.uniform(-0.3, 0.3, size=limit) * spread
        high = np.maximum(open_, close) + rng.uniform(0.2, 1.0, size=limit) * spread
        low = np.minimum(open_, close) - rng.uniform(0.2, 1.0, size=limit) * spread

        # Volume scales with price level.
        base_vol = start_price * rng.uniform(0.5, 5.0, size=limit)
        volume = base_vol

        # Build timestamp index ending at "now" (most recent candle is current).
        end_time = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
        index = pd.date_range(end=end_time, periods=limit, freq=freq, tz="UTC")

        df = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=index,
        )
        df.index.name = "open_time"

        if include_events:
            # Randomly tag some candles as near-event.
            event_mask = rng.random(limit) < self.event_probability
            df["near_event"] = event_mask

            event_types = ["FOMC", "CPI", "NFP", "GDP", "PPI"]
            df["event_type"] = None
            if event_mask.any():
                df.loc[event_mask, "event_type"] = rng.choice(
                    event_types, size=event_mask.sum()
                )

            df["mins_from_event"] = None
            if event_mask.any():
                df.loc[event_mask, "mins_from_event"] = rng.integers(
                    -120, 120, size=event_mask.sum()
                )

        return df
