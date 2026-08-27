"""Centralised configuration for the telemetry pipeline.

All tunables in one place so they can be swept during validation
without touching the processing code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Default cache location for FastF1 (writes ~hundreds of MB per season)
CACHE_DIR = Path("./fastf1_cache")
OUTPUT_DIR = Path("./output")


@dataclass(frozen=True)
class PipelineConfig:
    """Pipeline parameters.

    Defaults chosen for FastF1 broadcast telemetry (~10 Hz, ~5-15 m
    sample spacing depending on speed).  All distances in metres,
    speeds in km/h (FastF1's native unit).
    """

    # ---- Resampling ----------------------------------------------------
    # Uniform spatial grid spacing after resampling.  2 m oversamples at
    # high speed but matches native at low speed (where it matters for
    # apex location precision).
    resample_dx: float = 2.0

    # ---- Savitzky-Golay smoothing -------------------------------------
    # Speed channel is relatively clean - light smoothing only.
    savgol_speed_window: int = 11      # samples (~22 m at dx=2)
    savgol_speed_polyorder: int = 3

    # Position channels (X, Y) have GPS drift - need heavier smoothing
    # because we differentiate twice for curvature.  Median pre-filter
    # in telemetry.py handles isolated spikes.
    savgol_pos_window: int = 31        # samples (~62 m at dx=2)
    savgol_pos_polyorder: int = 3

    # ---- Hybrid apex detector (curvature-gated speed minima) ----------
    # Curvature threshold (1/m).  A 100 m radius corner has kappa = 0.01.
    # 0.003 ~= 330 m radius - threshold for "this is a corner zone".
    curvature_threshold: float = 0.003

    # Minimum distance between adjacent apexes; closer pairs are merged
    # (keeping the slower of the two as the true apex).  Important for
    # chicanes which we DO want to keep separate, but not for the same
    # apex picked up twice by noise.
    min_corner_separation: float = 60.0

    # Smoothing applied to |kappa| before thresholding (helps avoid
    # threshold flicker on noisy curvature signal).
    curvature_smoothing_window: int = 41

    # ---- Circuit-info detector ----------------------------------------
    # Search radius around each FIA corner coordinate for local speed
    # minimum refinement.
    seed_refinement_radius: float = 50.0

    # ---- Detector agreement metric ------------------------------------
    # Two apexes from different detectors are "matched" if within this
    # distance along the lap.
    apex_agreement_tolerance: float = 25.0

    # ---- Sector filtering ---------------------------------------------
    # Discard micro-sectors shorter than this (likely double-apex
    # complex picked up as two sectors).
    min_sector_length: float = 80.0

    # ---- Pace filter --------------------------------------------------
    # Drop drivers whose fastest lap exceeds this percentage of the
    # session's pole time.  107 % is the FIA's traditional qualification
    # threshold; empirically validated against 2025 season data as
    # appropriate for removing non-representative laps (red-flag affected
    # attempts, drivers who completed only one slow Q1 lap, etc.).
    # Set to None or a very large value to disable.
    pace_filter_pct: float = 107.0
