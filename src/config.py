"""
src/config.py — Configuration dataclass for chart output and generation settings.

Central place for all tuneable parameters: output directories, chart styling,
default pairs/timeframes, and candle window size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChartConfig:
    """Configuration for the chart generator.

    Attributes:
        output_dir: Directory where PNG charts and JSON sidecars are written.
        default_pairs: Trading pairs to chart when no explicit list is given.
        default_timeframes: Timeframes to chart when no explicit list is given.
        candle_limit: Number of most-recent candles to fetch per pair/timeframe.
        style: mplfinance style name (e.g. 'charles', 'nightclouds', 'yahoo').
        figsize: Figure dimensions in inches (width, height).
        volume: Whether to render the volume panel below the candlestick chart.
    """

    output_dir: Path = field(default_factory=lambda: Path("charts"))
    default_pairs: list[str] = field(
        default_factory=lambda: ["BTC/USD", "ETH/USD", "SOL/USD"]
    )
    default_timeframes: list[str] = field(
        default_factory=lambda: ["1h", "4h", "1d"]
    )
    candle_limit: int = 200
    style: str = "charles"
    figsize: tuple[int, int] = (14, 8)
    volume: bool = True

    def __post_init__(self) -> None:
        """Coerce output_dir to Path and create it if it does not exist."""
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


# Module-level default instance — importable directly as ``from config import DEFAULT_CONFIG``.
DEFAULT_CONFIG = ChartConfig()
