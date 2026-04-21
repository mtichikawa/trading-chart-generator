"""
tests/test_t1_integration.py — Integration tests for T1 → T2 data flow.

Verifies that MockOHLCVReader produces data compatible with ChartGenerator,
and that the full pipeline (reader → generator → PNG + JSON) works end-to-end.
No database or network access required.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator  # noqa: E402
from config import ChartConfig  # noqa: E402
from mock_reader import MockOHLCVReader  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reader() -> MockOHLCVReader:
    """MockOHLCVReader with deterministic seed."""
    return MockOHLCVReader(seed=99)


@pytest.fixture()
def generator(tmp_path: Path) -> ChartGenerator:
    """ChartGenerator writing to a temp directory."""
    config = ChartConfig(output_dir=tmp_path)
    return ChartGenerator(output_dir=tmp_path, config=config)


# ---------------------------------------------------------------------------
# MockOHLCVReader unit tests
# ---------------------------------------------------------------------------


class TestMockReader:
    """Tests for MockOHLCVReader interface compliance."""

    def test_fetch_candles_returns_dataframe(self, reader: MockOHLCVReader) -> None:
        """fetch_candles must return a non-empty DataFrame."""
        df = reader.fetch_candles("BTC/USD", "1h", limit=50)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 50

    def test_fetch_candles_has_ohlcv_columns(self, reader: MockOHLCVReader) -> None:
        """fetch_candles output must have open, high, low, close, volume."""
        df = reader.fetch_candles("ETH/USD", "4h", limit=30)
        required = {"open", "high", "low", "close", "volume"}
        assert required.issubset(set(df.columns))

    def test_fetch_candles_no_event_columns(self, reader: MockOHLCVReader) -> None:
        """fetch_candles must NOT include event annotation columns."""
        df = reader.fetch_candles("BTC/USD", "1h", limit=50)
        assert "near_event" not in df.columns
        assert "event_type" not in df.columns

    def test_fetch_with_events_has_event_columns(self, reader: MockOHLCVReader) -> None:
        """fetch_with_events must include near_event, event_type, mins_from_event."""
        df = reader.fetch_with_events("BTC/USD", "1h", limit=100)
        assert "near_event" in df.columns
        assert "event_type" in df.columns
        assert "mins_from_event" in df.columns

    def test_ohlc_relationships_hold(self, reader: MockOHLCVReader) -> None:
        """High must be >= max(open, close); low must be <= min(open, close)."""
        df = reader.fetch_candles("BTC/USD", "1h", limit=200)
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()

    def test_index_is_datetime_utc(self, reader: MockOHLCVReader) -> None:
        """Index must be a timezone-aware DatetimeIndex in UTC."""
        df = reader.fetch_candles("SOL/USD", "1d", limit=30)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tz is not None
        assert str(df.index.tz) == "UTC"

    def test_index_is_sorted_ascending(self, reader: MockOHLCVReader) -> None:
        """Index must be sorted in ascending chronological order."""
        df = reader.fetch_candles("BTC/USD", "1h", limit=100)
        assert df.index.is_monotonic_increasing

    def test_list_available_returns_dict(self, reader: MockOHLCVReader) -> None:
        """list_available must return a dict of pair -> timeframes."""
        available = reader.list_available()
        assert isinstance(available, dict)
        assert "BTC/USD" in available
        assert isinstance(available["BTC/USD"], list)

    def test_different_pairs_produce_different_data(self, reader: MockOHLCVReader) -> None:
        """Different pairs should produce different price levels."""
        btc = reader.fetch_candles("BTC/USD", "1h", limit=10)
        eth = reader.fetch_candles("ETH/USD", "1h", limit=10)
        # BTC should be much higher than ETH
        assert btc["close"].mean() > eth["close"].mean() * 10

    def test_reproducible_with_same_seed(self) -> None:
        """Same seed must produce identical output."""
        r1 = MockOHLCVReader(seed=123)
        r2 = MockOHLCVReader(seed=123)
        df1 = r1.fetch_candles("BTC/USD", "1h", limit=50)
        df2 = r2.fetch_candles("BTC/USD", "1h", limit=50)
        pd.testing.assert_frame_equal(df1, df2)


# ---------------------------------------------------------------------------
# End-to-end integration tests
# ---------------------------------------------------------------------------


class TestT1T2Integration:
    """End-to-end tests: MockReader (T1 interface) → ChartGenerator (T2)."""

    def test_single_chart_generation(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """Can generate a single chart from mock T1 data."""
        df = reader.fetch_with_events("BTC/USD", "1h", limit=100)
        png_path, json_path = generator.generate(df, "BTC/USD", "1h")
        assert png_path.exists()
        assert json_path.exists()

    def test_generate_all_with_mock_reader(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """generate_all works with MockOHLCVReader (same interface as OHLCVReader)."""
        results = generator.generate_all(
            reader,
            pairs=["BTC/USD", "ETH/USD"],
            timeframes=["1h"],
        )
        assert len(results) == 2
        for png_path, json_path in results:
            assert png_path.exists()
            assert json_path.exists()

    def test_json_sidecar_has_correct_metadata(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """JSON sidecar from mock data contains valid metadata."""
        df = reader.fetch_with_events("ETH/USD", "4h", limit=50)
        _, json_path = generator.generate(df, "ETH/USD", "4h")
        data = json.loads(json_path.read_text(encoding="utf-8"))

        assert data["pair"] == "ETH/USD"
        assert data["timeframe"] == "4h"
        assert data["candle_count"] == 50
        assert isinstance(data["last_close"], (int, float))
        assert data["last_close"] > 0

    def test_event_markers_rendered(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """Charts with event-tagged data generate without errors."""
        # Use higher event probability to guarantee some events.
        event_reader = MockOHLCVReader(seed=99, event_probability=0.2)
        df = event_reader.fetch_with_events("BTC/USD", "1h", limit=100)
        assert df["near_event"].any(), "Test setup: need at least one event"
        png_path, _ = generator.generate(df, "BTC/USD", "1h")
        assert png_path.exists()
        assert png_path.stat().st_size > 0

    def test_all_three_pairs_chartable(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """All T1 pairs (BTC, ETH, SOL) produce valid charts."""
        for pair in ["BTC/USD", "ETH/USD", "SOL/USD"]:
            df = reader.fetch_candles(pair, "1h", limit=30)
            png_path, json_path = generator.generate(df, pair, "1h")
            assert png_path.exists()
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["pair"] == pair

    def test_multiple_timeframes(
        self, reader: MockOHLCVReader, generator: ChartGenerator
    ) -> None:
        """Different timeframes produce different date ranges."""
        df_1h = reader.fetch_candles("BTC/USD", "1h", limit=50)
        df_1d = reader.fetch_candles("BTC/USD", "1d", limit=50)

        _, json_1h = generator.generate(df_1h, "BTC/USD", "1h")
        _, json_1d = generator.generate(df_1d, "BTC/USD", "1d")

        meta_1h = json.loads(json_1h.read_text(encoding="utf-8"))
        meta_1d = json.loads(json_1d.read_text(encoding="utf-8"))

        # 50 daily candles span ~50 days; 50 hourly candles span ~2 days.
        # The daily range should be much wider.
        assert meta_1d["date_range"]["start"] < meta_1h["date_range"]["start"]

    def test_volume_data_is_positive(self, reader: MockOHLCVReader) -> None:
        """Volume from mock reader must be strictly positive (like real exchange data)."""
        df = reader.fetch_candles("BTC/USD", "1h", limit=200)
        assert (df["volume"] > 0).all()

    def test_prices_are_positive(self, reader: MockOHLCVReader) -> None:
        """All price columns must be strictly positive."""
        df = reader.fetch_candles("SOL/USD", "4h", limit=200)
        for col in ["open", "high", "low", "close"]:
            assert (df[col] > 0).all()
