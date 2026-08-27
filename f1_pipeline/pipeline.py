"""End-to-end pipeline orchestration.

Single-session: `process_session(year, gp, session_type)` -> features DataFrame.
Multi-session: `process_season(year)` -> concatenated features + diagnostics.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fastf1
import pandas as pd

from .apex_detection import (
    compare_detectors,
    detect_apex_circuit_info,
    detect_apex_hybrid,
)
from .config import CACHE_DIR, OUTPUT_DIR, PipelineConfig
from .features import extract_features
from .loader import get_fastest_lap_per_driver, get_season_schedule, load_session
from .segmentation import segment_apex_to_apex
from .telemetry import extract_telemetry, resample_uniform, smooth_telemetry


logger = logging.getLogger(__name__)


def init_cache(cache_dir: Path = CACHE_DIR) -> None:
    """Enable FastF1's on-disk cache.  Required before any session load."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))


# ---------------------------------------------------------------------------
# Single session
# ---------------------------------------------------------------------------


def process_session(
    year: int,
    gp: str | int,
    session_type: str = "Q",
    config: PipelineConfig | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Process one session -> (features DataFrame, per-driver diagnostics).

    The diagnostics list contains one entry per driver with the
    detector-agreement metrics.  These are useful for spotting circuits
    where one of the apex detectors is failing.
    """
    config = config or PipelineConfig()
    session = load_session(year, gp, session_type)

    feature_frames: list[pd.DataFrame] = []
    diagnostics: list[dict] = []

    for driver_code, lap in get_fastest_lap_per_driver(
        session, pace_filter_pct=config.pace_filter_pct
    ):
        try:
            tel_raw = extract_telemetry(lap)
            tel = resample_uniform(tel_raw, dx=config.resample_dx)
            tel = smooth_telemetry(tel, config)

            apexes_hybrid = detect_apex_hybrid(tel, config)
            apexes_circuit = detect_apex_circuit_info(session, tel, config)

            agreement = compare_detectors(
                apexes_hybrid, apexes_circuit, config.apex_agreement_tolerance
            )
            agreement.update({
                "year": year,
                "gp": str(gp),
                "session": session_type,
                "driver": driver_code,
            })
            diagnostics.append(agreement)

            # Prefer circuit_info when available (uses FIA ground truth
            # for corner existence); fall back to hybrid otherwise.
            apexes = apexes_circuit if apexes_circuit else apexes_hybrid
            detector_used = "circuit_info" if apexes_circuit else "hybrid"

            sectors = segment_apex_to_apex(
                tel, apexes, min_length=config.min_sector_length
            )

            metadata = {
                "year": year,
                "gp": str(gp),
                "session": session_type,
                "driver": driver_code,
                "lap_time_s": _to_seconds(lap.get("LapTime")),
                "detector": detector_used,
                "n_apexes": len(apexes),
            }

            features = extract_features(sectors, metadata)
            if not features.empty:
                feature_frames.append(features)

        except Exception as exc:
            logger.warning(
                "Failed driver %s on %s %s: %s", driver_code, year, gp, exc
            )
            continue

    if feature_frames:
        out = pd.concat(feature_frames, ignore_index=True)
    else:
        out = pd.DataFrame()

    return out, diagnostics


# ---------------------------------------------------------------------------
# Full season
# ---------------------------------------------------------------------------


def process_season(
    year: int,
    session_type: str = "Q",
    config: PipelineConfig | None = None,
    skip_failed: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process every event in a season -> (features, diagnostics) DataFrames.

    Returns whatever it can; failed sessions are logged but don't
    abort the run (so a single missing dataset doesn't kill the
    overnight processing).
    """
    config = config or PipelineConfig()
    schedule = get_season_schedule(year)

    all_features: list[pd.DataFrame] = []
    all_diagnostics: list[dict] = []

    for _, event in schedule.iterrows():
        gp = event["EventName"]
        logger.info("Processing %s %s (%s)...", year, gp, session_type)
        try:
            features, diags = process_session(year, gp, session_type, config)
            if not features.empty:
                all_features.append(features)
            all_diagnostics.extend(diags)
        except Exception as exc:
            logger.error("Skipping %s: %s", gp, exc)
            if not skip_failed:
                raise

    features_df = (
        pd.concat(all_features, ignore_index=True) if all_features else pd.DataFrame()
    )
    diagnostics_df = pd.DataFrame(all_diagnostics)

    return features_df, diagnostics_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_seconds(td) -> float | None:
    """Convert a pandas/numpy Timedelta lap time to float seconds."""
    if td is None or pd.isna(td):
        return None
    try:
        return td.total_seconds()
    except AttributeError:
        return None


def save_outputs(
    features: pd.DataFrame,
    diagnostics: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    tag: str = "2025",
) -> tuple[Path, Path]:
    """Persist features and diagnostics to disk.  Returns (features_path, diag_path)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    feat_path = output_dir / f"microsectors_{tag}.parquet"
    diag_path = output_dir / f"diagnostics_{tag}.parquet"
    features.to_parquet(feat_path, index=False)
    diagnostics.to_parquet(diag_path, index=False)
    return feat_path, diag_path
