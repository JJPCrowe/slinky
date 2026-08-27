"""Per-micro-sector feature extraction.

Produces the tabular feature matrix X consumed by:
  * Phase 2: as the geometric input to the OCP (CasADi)
  * Phase 3: as the input to the XGBoost surrogate

Feature design follows section 2.5 of the proposal: the OCP needs
to know the kinematic boundary conditions (v_exit, v_entry_target)
and the geometric domain (L_straight, curvature profile).

Elevation features are deliberately excluded - the broadcast Z channel
was found unreliable on tunnel circuits (see telemetry.py module
docstring).  Where Phase 2 requires altitude, FIA-published circuit
profiles should be used directly.

Energy-budget features (battery SoC, deployment caps) are NOT generated
here either - they are sweep variables for the OCP and will be appended
to this feature matrix during Phase 2 ground-truth generation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .apex_detection import compute_curvature
from .segmentation import MicroSector


def extract_features(
    sectors: list[MicroSector], metadata: dict
) -> pd.DataFrame:
    """Compute one feature row per micro-sector and return as DataFrame.

    `metadata` is a dict of session-level columns (year, gp, driver, etc.)
    that gets attached to every row.
    """
    rows: list[dict] = []
    for s in sectors:
        row = _features_for_sector(s, metadata)
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows)


def _features_for_sector(s: MicroSector, metadata: dict) -> dict | None:
    tel = s.telemetry
    if tel.empty or len(tel) < 5:
        return None

    speed = tel["Speed"].to_numpy()

    # Kinematic boundary conditions (the OCP cares most about these)
    v_exit = float(speed[0])             # speed leaving the prior corner apex
    v_entry_target = float(speed[-1])    # target speed at next corner apex
    v_max = float(speed.max())
    v_min = float(speed.min())

    # Argmax position of speed - useful for "where does the car reach
    # terminal velocity" analysis on the straight.
    arg_v_max = int(np.argmax(speed))
    dist_to_vmax = float(arg_v_max) / float(len(speed)) if len(speed) else np.nan

    # Geometric features
    L_straight = float(s.apex_end.distance - s.apex_start.distance)

    # Throttle / brake distribution proxies for current driving style.
    # The OCP will replace these with mathematically optimal traces.
    if "Throttle" in tel.columns:
        thr = tel["Throttle"].to_numpy()
        full_throttle_frac = float((thr > 95).mean())
        lift_frac = float((thr < 50).mean())
    else:
        full_throttle_frac = lift_frac = np.nan

    if "Brake" in tel.columns:
        brake_frac = float((tel["Brake"] > 0).mean())
    else:
        brake_frac = np.nan

    # Curvature features in this sector (most of the sector should be
    # near-straight; non-zero curvature here suggests a "kink" rather
    # than a true straight - important to flag for the OCP).
    if {"X", "Y"}.issubset(tel.columns) and len(tel) >= 5:
        kappa = compute_curvature(tel)
        kappa_abs = np.abs(kappa)
        kappa_max_mid = float(kappa_abs[len(kappa_abs) // 4 : 3 * len(kappa_abs) // 4].max())
        kappa_mean = float(kappa_abs.mean())
    else:
        kappa_max_mid = kappa_mean = np.nan

    return {
        **metadata,
        "sector_id": s.sector_id,
        "apex_start_m": float(s.apex_start.distance),
        "apex_end_m": float(s.apex_end.distance),
        "L_straight_m": L_straight,
        "v_exit_kph": v_exit,
        "v_entry_target_kph": v_entry_target,
        "v_max_kph": v_max,
        "v_min_kph": v_min,
        "rel_pos_vmax": dist_to_vmax,
        "full_throttle_frac": full_throttle_frac,
        "lift_frac": lift_frac,
        "brake_frac": brake_frac,
        "kappa_max_mid_1pm": kappa_max_mid,
        "kappa_mean_1pm": kappa_mean,
        "apex_start_corner": s.apex_start.corner_number,
        "apex_end_corner": s.apex_end.corner_number,
        "n_samples": len(tel),
    }
