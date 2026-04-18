"""
src/chart_generator.py — Candlestick PNG chart generation with JSON sidecars.

``ChartGenerator`` is the core class of T2.  It accepts a pandas DataFrame of
OHLCV data (as produced by :class:`db_reader.OHLCVReader`), renders a
mplfinance candlestick chart, saves it as a PNG, and writes a companion JSON
file containing chart metadata (price statistics, date range, file path).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import mplfinance as mpf
import pandas as pd

from config import ChartConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generate mplfinance candlestick charts and JSON metadata sidecars.

    Each call to :meth:`generate` produces two files in *output_dir*:

    * ``{pair}_{timeframe}_{timestamp}.png``  — candlestick chart
    * ``{pair}_{timeframe}_{timestamp}.json`` — metadata sidecar

    Near-event candles (from T1's event tagger) are highlighted with
    triangle markers on the chart when the ``near_event`` column is present
    in the DataFrame.

    Args:
        output_dir: Directory where output files are written.  Created on
            instantiation if it does not already exist.
        config: Optional :class:`~config.ChartConfig` for styling overrides.
            Defaults to :data:`~config.DEFAULT_CONFIG`.
    """

    def __init__(
        self,
        output_dir: Path | str,
        config: Optional[ChartConfig] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config if config is not None else DEFAULT_CONFIG

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        df: pd.DataFrame,
        pair: str,
        timeframe: str,
        title: Optional[str] = None,
    ) -> tuple[Path, Path]:
        """Generate a candlestick PNG chart and a JSON sidecar for *df*.

        Args:
            df: OHLCV DataFrame indexed by ``open_time`` (DatetimeIndex).
                Must have columns ``open``, ``high``, ``low``, ``close``,
                ``volume``.  An optional boolean ``near_event`` column
                triggers marker rendering on flagged candles.
            pair: Trading pair label, e.g. ``"BTC/USD"``.
            timeframe: Candle timeframe, e.g. ``"1h"``.
            title: Chart title shown in the PNG.  Defaults to
                ``"{pair} — {timeframe}"``.

        Returns:
            A ``(png_path, json_path)`` tuple of the two written files.

        Raises:
            ValueError: If *df* is empty or missing required OHLCV columns.
        """
        self._validate_df(df)

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"{pair.replace('/', '_')}_{timeframe}_{timestamp}"
        png_path = self.output_dir / f"{stem}.png"
        json_path = self.output_dir / f"{stem}.json"

        chart_title = title or f"{pair} — {timeframe}"

        # Build optional add-plots for near-event markers.
        addplots = self._build_event_markers(df)

        plot_kwargs: dict = dict(
            type="candle",
            style=self.config.style,
            title=chart_title,
            volume=self.config.volume,
            figsize=self.config.figsize,
            savefig=str(png_path),
        )
        # addplot must be omitted entirely when there are no extra plots;
        # mplfinance rejects addplot=None.
        if addplots:
            plot_kwargs["addplot"] = addplots

        mpf.plot(df[["open", "high", "low", "close", "volume"]], **plot_kwargs)

        logger.info("Chart saved: %s", png_path)

        metadata = self._build_metadata(df, pair, timeframe, png_path)
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        logger.info("Sidecar saved: %s", json_path)

        return png_path, json_path

    def generate_all(
        self,
        reader,
        pairs: Optional[list[str]] = None,
        timeframes: Optional[list[str]] = None,
    ) -> list[tuple[Path, Path]]:
        """Generate charts for every pair/timeframe combination.

        Iterates over the cartesian product of *pairs* × *timeframes*, fetches
        candles (including event annotations) via *reader*, and calls
        :meth:`generate` for each combination.  Failures for individual
        combinations are logged as warnings and skipped so that the rest of the
        batch completes.

        Args:
            reader: An :class:`~db_reader.OHLCVReader` (or any object with a
                ``fetch_with_events(pair, timeframe, limit)`` method returning
                a DataFrame).
            pairs: Trading pairs to chart.  Defaults to
                :attr:`~config.ChartConfig.default_pairs`.
            timeframes: Timeframes to chart.  Defaults to
                :attr:`~config.ChartConfig.default_timeframes`.

        Returns:
            List of ``(png_path, json_path)`` tuples for every successfully
            generated chart.
        """
        pairs = pairs or self.config.default_pairs
        timeframes = timeframes or self.config.default_timeframes
        results: list[tuple[Path, Path]] = []

        for pair in pairs:
            for tf in timeframes:
                try:
                    df = reader.fetch_with_events(
                        pair, tf, limit=self.config.candle_limit
                    )
                    if df.empty:
                        logger.warning(
                            "No data for %s %s — skipping.", pair, tf
                        )
                        continue
                    paths = self.generate(df, pair, tf)
                    results.append(paths)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to generate chart for %s %s: %s",
                        pair,
                        tf,
                        exc,
                    )

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_df(df: pd.DataFrame) -> None:
        """Raise ``ValueError`` if *df* is empty or missing required columns.

        Args:
            df: DataFrame to validate.

        Raises:
            ValueError: On empty DataFrame or missing OHLCV columns.
        """
        if df.empty:
            raise ValueError("Cannot generate chart from an empty DataFrame.")

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"DataFrame is missing required OHLCV columns: {sorted(missing)}"
            )

    def _build_event_markers(
        self, df: pd.DataFrame
    ) -> list:
        """Build mplfinance ``addplot`` objects for near-event candles.

        Candles where ``near_event`` is ``True`` receive an upward-pointing
        triangle marker (``^``) plotted just below the candle low.

        Args:
            df: OHLCV DataFrame; the ``near_event`` column is optional.

        Returns:
            A list containing one ``addplot`` object, or an empty list if the
            ``near_event`` column is absent or all values are falsy.
        """
        if "near_event" not in df.columns:
            return []

        event_mask = df["near_event"].fillna(False).astype(bool)
        if not event_mask.any():
            return []

        marker_series = pd.Series(float("nan"), index=df.index, dtype=float)
        marker_series[event_mask] = df.loc[event_mask, "low"] * 0.998

        return [
            mpf.make_addplot(
                marker_series,
                type="scatter",
                marker="^",
                markersize=80,
                color="gold",
                panel=0,
            )
        ]

    @staticmethod
    def _build_metadata(
        df: pd.DataFrame,
        pair: str,
        timeframe: str,
        png_path: Path,
    ) -> dict:
        """Assemble the JSON sidecar metadata dictionary.

        Args:
            df: OHLCV DataFrame used to generate the chart.
            pair: Trading pair label.
            timeframe: Candle timeframe label.
            png_path: Absolute path of the written PNG file.

        Returns:
            Dictionary with the following keys:

            * ``pair``              – trading pair
            * ``timeframe``         – candle timeframe
            * ``generated_at``      – ISO-8601 UTC timestamp of generation
            * ``candle_count``      – number of candles in the chart
            * ``date_range``        – ``{"start": ..., "end": ...}`` as ISO strings
            * ``last_close``        – closing price of the final candle
            * ``price_change_pct``  – percentage change from first to last close
            * ``chart_path``        – absolute path to the PNG file
        """
        first_close = float(df["close"].iloc[0])
        last_close = float(df["close"].iloc[-1])
        price_change_pct = (
            ((last_close - first_close) / first_close) * 100
            if first_close != 0
            else 0.0
        )

        # Convert index timestamps to ISO strings, handling tz-aware/naive.
        def _ts(ts: Any) -> str:
            if hasattr(ts, "isoformat"):
                return ts.isoformat()
            return str(ts)

        return {
            "pair": pair,
            "timeframe": timeframe,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "candle_count": len(df),
            "date_range": {
                "start": _ts(df.index[0]),
                "end": _ts(df.index[-1]),
            },
            "last_close": round(last_close, 8),
            "price_change_pct": round(price_change_pct, 4),
            "chart_path": str(png_path.resolve()),
        }
