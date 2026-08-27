"""Telemetry extraction, uniform spatial resampling, and Savitzky-Golay smoothing.

Mitigates TR-2 (low-fidelity FastF1 telemetry noise) from the proposal.

Note on elevation (Z): the broadcast Z channel was excluded after empirical
testing showed it is unreliable on circuits with tunnels or extensive
GPS-occluded sections (Monaco tunnel produced sustained corruption blocks
that survived Savitzky-Golay and short-window median filtering).  Since
the dissertation's Phase 2 OCP uses a longitudinal-only vehicle model
(per proposal section 5.2), elevation-dependent terms — if needed — will
be sourced from FIA-published circuit altitude profiles rather than
broadcast telemetry.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import medfilt, savgol_filter

from .config import PipelineConfig


# Channels we carry through the pipeline.
# Z (elevation) is deliberately excluded - see module docstring.
_CHANNELS = ["Speed", "Throttle", "Brake", "nGear", "X", "Y", "RPM"]


def extract_telemetry(lap) -> pd.DataFrame:
    """Pull merged car + position telemetry for a single lap.

    `lap.get_telemetry()` returns a FastF1 Telemetry object with car
    data and position data merged and a 'Distance' column already
    computed via integration of speed over time.
    """
    tel = lap.get_telemetry()

    # Keep only the channels we use; tolerate missing columns gracefully.
    cols = ["Distance"] + [c for c in _CHANNELS if c in tel.columns]
    return tel[cols].copy().reset_index(drop=True)


def resample_uniform(tel: pd.DataFrame, dx: float = 2.0) -> pd.DataFrame:
    """Resample telemetry onto a uniform spatial grid via linear interpolation.

    Uniform spacing is required for:
      * Savitzky-Golay (assumes constant sample spacing)
      * curvature via finite differences on X, Y
      * apex distance comparisons across drivers/laps
    """
    d = tel["Distance"].to_numpy()
    d_uniform = np.arange(d.min(), d.max(), dx)

    out = {"Distance": d_uniform}
    for col in tel.columns:
        if col == "Distance":
            continue
        out[col] = np.interp(d_uniform, d, tel[col].to_numpy())
    return pd.DataFrame(out)


def smooth_telemetry(tel: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Apply Savitzky-Golay smoothing with separate windows for speed and position.

    Speed is well-calibrated and only needs light smoothing.  Position
    (X, Y) is noisy GPS and gets a wider window because we differentiate
    it twice when computing curvature.

    A median filter is applied to position channels BEFORE Savitzky-Golay
    to reject isolated GPS spikes (extending the proposal's stated TR-2
    mitigation; standard robust signal processing).  The 5-sample kernel
    preserves real motion (~10 m of track at dx=2 m) while killing
    point-outliers in the GPS-derived X,Y coordinates.
    """
    out = tel.copy()

    speed_w = _odd_window(config.savgol_speed_window, len(out))
    pos_w = _odd_window(config.savgol_pos_window, len(out))

    if speed_w and "Speed" in out.columns:
        out["Speed"] = savgol_filter(
            out["Speed"].to_numpy(), speed_w, config.savgol_speed_polyorder
        )

    if pos_w:
        for col in ("X", "Y"):
            if col in out.columns:
                arr = out[col].to_numpy()
                arr = medfilt(arr, kernel_size=5)
                out[col] = savgol_filter(
                    arr, pos_w, config.savgol_pos_polyorder
                )

    return out


def _odd_window(requested: int, n_samples: int) -> int | None:
    """Coerce window length to be odd, >= polyorder+2, and <= n_samples."""
    w = min(requested, n_samples)
    if w < 5:
        return None
    if w % 2 == 0:
        w -= 1
    return w
