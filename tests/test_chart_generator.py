"""
tests/test_chart_generator.py — Unit tests for ChartGenerator.

All tests use synthetic OHLCV DataFrames and pytest's tmp_path fixture.
No database connection or live API is required.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup — allow bare imports from src/
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator  # noqa: E402
from config import ChartConfig  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv(
    n: int = 50,
    start: str = "2024-01-01",
    freq: str = "1h",
    seed: int = 42,
    include_events: bool = False,
) -> pd.DataFrame:
    """Return a synthetic OHLCV DataFrame with a DatetimeIndex.

    Args:
        n: Number of candles.
        start: ISO start date string.
        freq: pandas frequency string (e.g. ``"1h"``, ``"4h"``, ``"1D"``).
        seed: NumPy random seed for reproducibility.
        include_events: When *True*, add ``near_event``, ``event_type``, and
            ``mins_from_event`` columns to simulate T1's event-tagging output.

    Returns:
        DataFrame indexed by a UTC-aware DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    prices = 30_000.0 + np.cumsum(rng.normal(0, 200, n))
    prices = np.abs(prices)

    noise = rng.uniform(0, 300, n)
    open_ = prices
    close = prices + rng.normal(0, 150, n)
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    volume = rng.uniform(1_000, 50_000, n)

    index = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )

    if include_events:
        event_flags = np.zeros(n, dtype=bool)
        event_flags[[5, 15, 30]] = True
        df["near_event"] = event_flags
        df["event_type"] = None
        df.loc[df["near_event"], "event_type"] = "CPI"
        df["mins_from_event"] = None
        df.loc[df["near_event"], "mins_from_event"] = -30

    return df


@pytest.fixture()
def ohlcv_df() -> pd.DataFrame:
    """50-candle synthetic BTC/USD OHLCV DataFrame."""
    return _make_ohlcv(n=50)


@pytest.fixture()
def ohlcv_df_with_events() -> pd.DataFrame:
    """50-candle synthetic DataFrame including near_event markers."""
    return _make_ohlcv(n=50, include_events=True)


@pytest.fixture()
def generator(tmp_path: Path) -> ChartGenerator:
    """ChartGenerator writing to pytest's tmp_path directory."""
    config = ChartConfig(output_dir=tmp_path)
    return ChartGenerator(output_dir=tmp_path, config=config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for ChartGenerator.generate()."""

    def test_generate_returns_two_paths(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """generate() must return a (png_path, json_path) tuple."""
        result = generator.generate(ohlcv_df, "BTC/USD", "1h")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_png_file_is_written(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """The PNG file must exist on disk after generate()."""
        png_path, _ = generator.generate(ohlcv_df, "BTC/USD", "1h")
        assert png_path.exists()
        assert png_path.suffix == ".png"

    def test_json_file_is_written(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """The JSON sidecar must exist on disk after generate()."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        assert json_path.exists()
        assert json_path.suffix == ".json"

    def test_png_file_is_non_empty(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """The PNG file must have a non-zero byte size."""
        png_path, _ = generator.generate(ohlcv_df, "ETH/USD", "4h")
        assert png_path.stat().st_size > 0

    def test_raises_on_empty_dataframe(
        self, generator: ChartGenerator
    ) -> None:
        """generate() must raise ValueError for an empty DataFrame."""
        empty_df = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        )
        with pytest.raises(ValueError, match="empty"):
            generator.generate(empty_df, "BTC/USD", "1h")

    def test_raises_on_missing_columns(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """generate() must raise ValueError when OHLCV columns are missing."""
        bad_df = ohlcv_df.drop(columns=["close", "volume"])
        with pytest.raises(ValueError, match="missing required"):
            generator.generate(bad_df, "BTC/USD", "1h")


class TestFilenameFormat:
    """Tests for the generated file naming convention."""

    def test_png_filename_contains_pair(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """PNG filename must embed the pair with '/' replaced by '_'."""
        png_path, _ = generator.generate(ohlcv_df, "BTC/USD", "1h")
        assert "BTC_USD" in png_path.name

    def test_png_filename_contains_timeframe(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """PNG filename must embed the timeframe."""
        png_path, _ = generator.generate(ohlcv_df, "ETH/USD", "4h")
        assert "4h" in png_path.name

    def test_png_and_json_share_stem(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """PNG and JSON sidecar must share the same filename stem."""
        png_path, json_path = generator.generate(ohlcv_df, "SOL/USD", "1d")
        assert png_path.stem == json_path.stem

    def test_filename_format_pattern(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """Filename must match ``{pair}_{timeframe}_{timestamp}`` format."""
        png_path, _ = generator.generate(ohlcv_df, "BTC/USD", "1h")
        # Expected pattern: BTC_USD_1h_<YYYYMMDDTHHMMSSz>.png
        parts = png_path.stem.split("_")
        # "BTC", "USD", "1h", "<timestamp>"
        assert parts[0] == "BTC"
        assert parts[1] == "USD"
        assert parts[2] == "1h"
        assert len(parts) >= 4, "Timestamp segment is missing from filename."


class TestJSONSidecar:
    """Tests for the content of the JSON metadata sidecar."""

    def _read_json(self, json_path: Path) -> dict:
        return json.loads(json_path.read_text(encoding="utf-8"))

    def test_all_required_fields_present(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """JSON sidecar must contain all seven required metadata fields."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        required_fields = {
            "pair",
            "timeframe",
            "generated_at",
            "candle_count",
            "date_range",
            "last_close",
            "price_change_pct",
            "chart_path",
        }
        assert required_fields.issubset(data.keys())

    def test_pair_field_matches(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``pair`` field in JSON must match the pair passed to generate()."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert data["pair"] == "BTC/USD"

    def test_timeframe_field_matches(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``timeframe`` field in JSON must match the timeframe passed to generate()."""
        _, json_path = generator.generate(ohlcv_df, "ETH/USD", "4h")
        data = self._read_json(json_path)
        assert data["timeframe"] == "4h"

    def test_candle_count_matches_dataframe(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``candle_count`` must equal the number of rows in the input DataFrame."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert data["candle_count"] == len(ohlcv_df)

    def test_date_range_has_start_and_end(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``date_range`` must be a dict with both ``start`` and ``end`` keys."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert "start" in data["date_range"]
        assert "end" in data["date_range"]

    def test_last_close_is_numeric(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``last_close`` must be a float or int."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert isinstance(data["last_close"], (int, float))

    def test_price_change_pct_is_numeric(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``price_change_pct`` must be a float or int."""
        _, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert isinstance(data["price_change_pct"], (int, float))

    def test_chart_path_points_to_png(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """``chart_path`` in JSON must be an absolute path ending in ``.png``."""
        png_path, json_path = generator.generate(ohlcv_df, "BTC/USD", "1h")
        data = self._read_json(json_path)
        assert data["chart_path"].endswith(".png")
        assert Path(data["chart_path"]).is_absolute()


class TestEventMarkers:
    """Tests for near-event marker rendering."""

    def test_generate_with_events_does_not_raise(
        self,
        generator: ChartGenerator,
        ohlcv_df_with_events: pd.DataFrame,
    ) -> None:
        """generate() must succeed when the DataFrame has a near_event column."""
        png_path, json_path = generator.generate(
            ohlcv_df_with_events, "BTC/USD", "1h"
        )
        assert png_path.exists()
        assert json_path.exists()

    def test_generate_without_near_event_column(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """generate() must succeed when the near_event column is absent."""
        assert "near_event" not in ohlcv_df.columns
        png_path, _ = generator.generate(ohlcv_df, "BTC/USD", "1h")
        assert png_path.exists()

    def test_event_markers_built_only_when_column_present(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame,
        ohlcv_df_with_events: pd.DataFrame
    ) -> None:
        """_build_event_markers returns [] without column, non-empty with it."""
        assert generator._build_event_markers(ohlcv_df) == []
        markers = generator._build_event_markers(ohlcv_df_with_events)
        assert len(markers) == 1

    def test_all_false_near_event_yields_no_markers(
        self, generator: ChartGenerator, ohlcv_df: pd.DataFrame
    ) -> None:
        """When near_event is all False, _build_event_markers returns []."""
        df = ohlcv_df.copy()
        df["near_event"] = False
        assert generator._build_event_markers(df) == []


class TestGenerateAll:
    """Tests for ChartGenerator.generate_all() using a mock reader."""

    class _MockReader:
        """Minimal reader stub that returns synthetic data."""

        def fetch_with_events(
            self, pair: str, timeframe: str, limit: int = 200
        ) -> pd.DataFrame:
            return _make_ohlcv(n=min(limit, 30))

    def test_generate_all_returns_list(self, generator: ChartGenerator) -> None:
        """generate_all() must return a list of (png, json) tuples."""
        reader = self._MockReader()
        results = generator.generate_all(
            reader,
            pairs=["BTC/USD"],
            timeframes=["1h"],
        )
        assert isinstance(results, list)
        assert len(results) == 1
        assert len(results[0]) == 2

    def test_generate_all_creates_all_combinations(
        self, generator: ChartGenerator
    ) -> None:
        """generate_all() must produce one chart per pair × timeframe."""
        reader = self._MockReader()
        results = generator.generate_all(
            reader,
            pairs=["BTC/USD", "ETH/USD"],
            timeframes=["1h", "4h"],
        )
        assert len(results) == 4

    def test_generate_all_skips_empty_results(
        self, generator: ChartGenerator
    ) -> None:
        """generate_all() must skip pairs that return empty DataFrames."""

        class _EmptyReader:
            def fetch_with_events(self, pair, timeframe, limit=200):
                return pd.DataFrame(
                    columns=["open", "high", "low", "close", "volume"]
                )

        results = generator.generate_all(
            _EmptyReader(),
            pairs=["BTC/USD"],
            timeframes=["1h"],
        )
        assert results == []
