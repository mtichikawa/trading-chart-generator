"""
src/db_reader.py — SQLAlchemy-based reader for T1's OHLCV PostgreSQL table.

This module connects to the same database that crypto-data-pipeline (T1) writes
to, selects the most-recent N candles for a given pair/timeframe, and returns
them as a pandas DataFrame ready for mplfinance.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()


class OHLCVReader:
    """Read OHLCV candles from T1's PostgreSQL database.

    Connection parameters are resolved from environment variables with
    sensible defaults that match T1's ``crypto-data-pipeline`` setup.

    Environment variables
    ---------------------
    DB_HOST     PostgreSQL host        (default: localhost)
    DB_PORT     PostgreSQL port        (default: 5432)
    DB_NAME     Database name          (default: crypto_pipeline)
    DB_USER     Database user          (default: postgres)
    DB_PASSWORD Database password      (default: empty string)
    """

    def __init__(self, engine: Optional[Engine] = None) -> None:
        """Initialise the reader with an optional pre-built SQLAlchemy engine.

        Args:
            engine: An existing SQLAlchemy engine.  If *None* (default) an
                engine is constructed from environment variables via
                :meth:`get_engine`.
        """
        self._engine: Engine = engine if engine is not None else self.get_engine()

    # ------------------------------------------------------------------
    # Engine construction
    # ------------------------------------------------------------------

    @staticmethod
    def get_engine() -> Engine:
        """Build a SQLAlchemy engine from environment variables.

        Returns:
            A ``postgresql+psycopg2`` engine using connection parameters
            read from the process environment.
        """
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        dbname = os.getenv("DB_NAME", "crypto_pipeline")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
        return create_engine(url, pool_pre_ping=True)

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def fetch_candles(
        self,
        pair: str,
        timeframe: str,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch the most-recent OHLCV candles for *pair* and *timeframe*.

        Returns a DataFrame with columns::

            open_time (DatetimeTZDtype, index) | open | high | low | close | volume

        The DataFrame is sorted ascending by ``open_time`` so that it can be
        passed directly to mplfinance.

        Args:
            pair:      Trading pair, e.g. ``"BTC/USD"``.
            timeframe: Candle timeframe, e.g. ``"1h"``.
            limit:     Maximum number of candles to return.

        Returns:
            DataFrame indexed by ``open_time`` with OHLCV columns cast to
            ``float64``.
        """
        query = text(
            """
            SELECT open_time, open, high, low, close, volume
            FROM ohlcv
            WHERE pair = :pair
              AND timeframe = :tf
            ORDER BY open_time DESC
            LIMIT :lim
            """
        )
        with self._engine.connect() as conn:
            df = pd.read_sql(
                query,
                conn,
                params={"pair": pair, "tf": timeframe, "lim": limit},
                parse_dates=["open_time"],
            )

        return self._prepare_ohlcv(df)

    def fetch_with_events(
        self,
        pair: str,
        timeframe: str,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch candles including market-event annotation columns.

        Extends :meth:`fetch_candles` with three extra columns:

        * ``near_event``     – boolean flag set by T1's event tagger
        * ``event_type``     – string label (e.g. ``"CPI"``, ``"NFP"``)
        * ``mins_from_event``– signed integer: negative = before event

        Args:
            pair:      Trading pair, e.g. ``"ETH/USD"``.
            timeframe: Candle timeframe, e.g. ``"4h"``.
            limit:     Maximum number of candles to return.

        Returns:
            DataFrame indexed by ``open_time`` with OHLCV + event columns.
        """
        query = text(
            """
            SELECT open_time, open, high, low, close, volume,
                   near_event, event_type, mins_from_event
            FROM ohlcv
            WHERE pair = :pair
              AND timeframe = :tf
            ORDER BY open_time DESC
            LIMIT :lim
            """
        )
        with self._engine.connect() as conn:
            df = pd.read_sql(
                query,
                conn,
                params={"pair": pair, "tf": timeframe, "lim": limit},
                parse_dates=["open_time"],
            )

        return self._prepare_ohlcv(df)

    def list_available(self) -> dict[str, list[str]]:
        """Return all (pair, timeframe) combinations present in the database.

        Returns:
            A mapping of ``{pair: [timeframe, ...]}`` where each list is
            sorted in ascending lexicographic order.

        Example::

            {
                "BTC/USD": ["15m", "1d", "1h", "4h", "5m"],
                "ETH/USD": ["1h", "4h"],
            }
        """
        query = text(
            """
            SELECT DISTINCT pair, timeframe
            FROM ohlcv
            ORDER BY pair, timeframe
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(query).fetchall()

        result: dict[str, list[str]] = {}
        for pair, timeframe in rows:
            result.setdefault(pair, []).append(timeframe)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Normalise a raw OHLCV DataFrame from the database.

        * Sets ``open_time`` as a timezone-aware DatetimeIndex.
        * Sorts ascending by time (the SQL query returns DESC for the LIMIT).
        * Casts OHLCV columns to ``float64``.

        Args:
            df: Raw DataFrame as returned by ``pd.read_sql``.

        Returns:
            Cleaned DataFrame ready for mplfinance.
        """
        if df.empty:
            return df

        df = df.sort_values("open_time").reset_index(drop=True)
        df = df.set_index("open_time")

        # Ensure the index is timezone-aware (psycopg2 may strip tz info).
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        # Cast price/volume columns to float.
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = df[col].astype(float)

        return df
