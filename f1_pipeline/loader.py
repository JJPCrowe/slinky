"""Session loading and lap selection via the FastF1 API."""

from __future__ import annotations

import logging
from typing import Iterator

import fastf1
import pandas as pd
from fastf1.core import Session


logger = logging.getLogger(__name__)


def load_session(year: int, gp: str | int, session_type: str = "Q") -> Session:
    """Load a FastF1 session with telemetry and position data.

    Parameters
    ----------
    year : int
        Championship year (e.g. 2025).
    gp : str | int
        Grand Prix name or round number.  FastF1 fuzzy-matches names.
    session_type : str
        One of 'FP1', 'FP2', 'FP3', 'Q', 'S', 'SS', 'R'.  Default 'Q'
        (qualifying) per dissertation scope - cleanest single-lap pace.
    """
    session = fastf1.get_session(year, gp, session_type)
    # weather + messages not needed for Phase 1 features
    session.load(telemetry=True, weather=False, messages=False)
    return session


def get_fastest_lap_per_driver(
    session: Session,
    pace_filter_pct: float | None = 107.0,
) -> Iterator[tuple[str, pd.Series]]:
    """Yield (driver_abbreviation, fastest_valid_lap) for each driver.

    Filters applied (in order):
      * NaN LapTime (out-laps, in-laps, pit laps)
      * Deleted laps (track-limit violations, etc.) where FastF1 exposes
        the `Deleted` column
      * Drivers whose fastest lap exceeds `pace_filter_pct`% of the
        session's pole time - drops laps that weren't representative
        flying laps (red-flag affected attempts, single-lap Q1 exits).
        Pass `None` to disable.

    Note: this picks each driver's fastest qualifying lap, which is the
    relevant performance benchmark and what race engineers use for
    cross-team setup comparisons.
    """
    # Pass 1: collect each driver's fastest valid lap into a list so we
    # can compute the session pole time before applying the pace filter.
    candidates: list[tuple[str, pd.Series]] = []
    for drv in session.drivers:
        try:
            drv_laps = session.laps.pick_drivers(drv)
        except AttributeError:
            # Older FastF1 versions used singular pick_driver
            drv_laps = session.laps.pick_driver(drv)

        if drv_laps.empty:
            continue

        valid = drv_laps.dropna(subset=["LapTime"])

        # Drop deleted laps if the column is present.
        if "Deleted" in valid.columns:
            valid = valid[valid["Deleted"] != True]  # noqa: E712

        if valid.empty:
            continue

        fastest = valid.loc[valid["LapTime"].idxmin()]

        try:
            driver_abbr = session.get_driver(drv)["Abbreviation"]
        except Exception:
            driver_abbr = str(drv)

        candidates.append((driver_abbr, fastest))

    if not candidates:
        return

    # Pass 2: apply the pace filter, if enabled.
    if pace_filter_pct is None or pace_filter_pct >= 1000:
        # No filter requested; yield everything.
        yield from candidates
        return

    pole_time_s = min(
        c[1]["LapTime"].total_seconds() for c in candidates
    )
    threshold_s = pole_time_s * (pace_filter_pct / 100.0)

    n_kept = n_filtered = 0
    for driver_abbr, fastest in candidates:
        lap_time_s = fastest["LapTime"].total_seconds()
        if lap_time_s <= threshold_s:
            yield driver_abbr, fastest
            n_kept += 1
        else:
            pct_off = (lap_time_s / pole_time_s - 1) * 100
            logger.info(
                "Pace-filtered %s on this session: %.3fs (+%.2f%% from pole "
                "%.3fs) exceeds %.1f%% threshold",
                driver_abbr, lap_time_s, pct_off, pole_time_s, pace_filter_pct,
            )
            n_filtered += 1

    if n_filtered > 0:
        logger.info(
            "Pace filter: kept %d/%d drivers (pole=%.3fs, threshold=%.3fs)",
            n_kept, n_kept + n_filtered, pole_time_s, threshold_s,
        )


def get_season_schedule(year: int) -> pd.DataFrame:
    """Return all race events for a season, excluding pre-season testing."""
    return fastf1.get_event_schedule(year, include_testing=False)
