"""Apex-to-apex micro-sector segmentation.

A micro-sector spans from one corner apex to the next, capturing the
intervening straight (or short link between corners).  This is the
unit of optimisation in the Phase 2 OCP and the unit of prediction
for the Phase 3 XGBoost surrogate.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .apex_detection import Apex


@dataclass
class MicroSector:
    """One apex-to-apex segment of a lap."""

    sector_id: int
    apex_start: Apex
    apex_end: Apex
    telemetry: pd.DataFrame   # slice of the lap's telemetry covering this sector

    @property
    def length(self) -> float:
        return self.apex_end.distance - self.apex_start.distance


def segment_apex_to_apex(
    tel: pd.DataFrame, apexes: list[Apex], min_length: float = 80.0
) -> list[MicroSector]:
    """Build micro-sectors from a sorted apex sequence.

    Sectors shorter than `min_length` are discarded (likely the two
    sides of a chicane being picked up as both an exit and an entry
    rather than a single straight).

    Note: this implementation does NOT wrap from the last apex back to
    the first apex across the start-finish line.  That would require
    handling the lap discontinuity and isn't necessary for the initial
    feature matrix - we capture N-1 sectors from N apexes.  Easy to
    extend later if the OCP wants full-lap coverage.
    """
    if len(apexes) < 2:
        return []

    sorted_ax = sorted(apexes, key=lambda a: a.distance)
    sectors: list[MicroSector] = []

    for i in range(len(sorted_ax) - 1):
        a_start = sorted_ax[i]
        a_end = sorted_ax[i + 1]
        length = a_end.distance - a_start.distance
        if length < min_length:
            continue

        mask = (tel["Distance"] >= a_start.distance) & (
            tel["Distance"] <= a_end.distance
        )
        slice_ = tel.loc[mask].copy()
        if len(slice_) < 5:
            continue

        sectors.append(
            MicroSector(
                sector_id=i,
                apex_start=a_start,
                apex_end=a_end,
                telemetry=slice_,
            )
        )

    return sectors
