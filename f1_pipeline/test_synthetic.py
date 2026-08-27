"""Synthetic smoke test - verifies the offline-testable parts of the pipeline.

We can't hit the FastF1 API here, but we CAN verify that:
  * curvature is computed correctly on a known geometry
  * the hybrid apex detector finds the right apex on synthetic data
  * micro-sector segmentation behaves
  * feature extraction produces sensible numbers
"""

import numpy as np
import pandas as pd

from f1_pipeline.apex_detection import (
    Apex, compute_curvature, detect_apex_hybrid, _merge_close
)
from f1_pipeline.config import PipelineConfig
from f1_pipeline.segmentation import segment_apex_to_apex
from f1_pipeline.features import extract_features


def make_synthetic_lap():
    """A toy lap: two straights joined by two semicircular corners.

    Corner 1: radius 50m centred at (0, 50)     -> kappa = 0.02 1/m
    Corner 2: radius 100m centred at (300, 0)   -> kappa = 0.01 1/m
    Speed dips to 80 km/h at corner 1 apex, 120 km/h at corner 2 apex,
    300 km/h on straights.
    """
    # Straight 1: from x = -300 to 0 along y = 0
    s1 = np.linspace(-300, 0, 150)
    x1, y1 = s1, np.zeros_like(s1)

    # Corner 1: semicircle of radius 50 around (0, 50), entering at (0,0)
    # going through (50, 50) (apex) and exiting at (0, 100).
    theta1 = np.linspace(-np.pi / 2, np.pi / 2, 50)
    r1 = 50.0
    x_c1 = 0.0 + r1 * np.cos(theta1)
    y_c1 = 50.0 + r1 * np.sin(theta1)
    apex1_local = np.argmin(np.abs(theta1 - 0))   # index of apex (50, 50)

    # Straight 2: from (0, 100) to (300, 100)
    s2 = np.linspace(0, 300, 150)
    x2, y2 = s2, np.full_like(s2, 100.0)

    # Corner 2: semicircle of radius 100 around (300, 0), entering at (300, 100)
    # going through (400, 0) (apex) and exiting at (300, -100).
    theta2 = np.linspace(np.pi / 2, -np.pi / 2, 50)
    r2 = 100.0
    x_c2 = 300.0 + r2 * np.cos(theta2)
    y_c2 = 0.0 + r2 * np.sin(theta2)
    apex2_local = np.argmin(np.abs(theta2 - 0))   # index of apex (400, 0)

    # Final straight
    s3 = np.linspace(300, 0, 50)
    x3, y3 = s3, np.full_like(s3, -100.0)

    x = np.concatenate([x1, x_c1, x2, x_c2, x3])
    y = np.concatenate([y1, y_c1, y2, y_c2, y3])

    # Compute cumulative distance along the path
    dx = np.diff(x, prepend=x[0])
    dy = np.diff(y, prepend=y[0])
    d = np.cumsum(np.sqrt(dx * dx + dy * dy))

    # Speed profile: 300 on straights, dipping into the corners.
    speed = np.full_like(d, 300.0)
    apex1_idx = len(x1) + apex1_local
    apex2_idx = len(x1) + len(x_c1) + len(x2) + apex2_local

    # Smooth dip around each apex
    for centre, v_apex, half_width in [(apex1_idx, 80.0, 30), (apex2_idx, 120.0, 30)]:
        for j in range(max(0, centre - half_width), min(len(speed), centre + half_width)):
            t = abs(j - centre) / half_width
            speed[j] = v_apex + (300.0 - v_apex) * t

    # Resample to a uniform spatial grid (matches what the pipeline expects)
    d_uniform = np.arange(d.min(), d.max(), 2.0)
    x_u = np.interp(d_uniform, d, x)
    y_u = np.interp(d_uniform, d, y)
    speed_u = np.interp(d_uniform, d, speed)

    tel = pd.DataFrame({
        "Distance": d_uniform,
        "X": x_u,
        "Y": y_u,
        "Z": np.zeros_like(d_uniform),
        "Speed": speed_u,
        "Throttle": np.where(speed_u > 250, 100.0, 30.0),
        "Brake": np.where(speed_u < 200, 1.0, 0.0),
        "nGear": np.where(speed_u > 250, 8, 4),
    })

    # Find the apex indices in the resampled telemetry
    apex1_idx_u = int(np.argmin(np.abs(d_uniform - d[apex1_idx])))
    apex2_idx_u = int(np.argmin(np.abs(d_uniform - d[apex2_idx])))

    return tel, apex1_idx_u, apex2_idx_u


def test_curvature():
    tel, _, _ = make_synthetic_lap()
    kappa = compute_curvature(tel)
    # Curvature on straight should be near 0
    straight_kappa = np.abs(kappa[10:140])
    assert straight_kappa.max() < 0.005, f"Straight curvature too high: {straight_kappa.max()}"
    # Curvature in corner 1 (r=50) should be near 0.02
    corner_kappa = np.abs(kappa[180:200])
    assert 0.015 < corner_kappa.mean() < 0.025, f"Corner kappa off: mean={corner_kappa.mean()}"
    print(f"  curvature OK (straight max={straight_kappa.max():.5f}, "
          f"corner1 mean={corner_kappa.mean():.4f})")


def test_apex_detection():
    tel, apex1_idx, apex2_idx = make_synthetic_lap()
    config = PipelineConfig(
        resample_dx=2.0,
        curvature_threshold=0.003,
        min_corner_separation=50.0,
        curvature_smoothing_window=11,
    )
    apexes = detect_apex_hybrid(tel, config)
    assert len(apexes) == 2, f"Expected 2 apexes, got {len(apexes)}: {apexes}"
    # Apex 1 should be at the slower of the two corners (80 km/h)
    speeds = sorted(a.speed for a in apexes)
    assert speeds[0] < 100, f"Slowest apex too fast: {speeds[0]}"
    assert 110 < speeds[1] < 130, f"Faster apex off: {speeds[1]}"
    print(f"  detected 2 apexes at speeds {[round(a.speed, 1) for a in apexes]}")


def test_merge():
    a = Apex(distance=100, x=0, y=0, speed=90, method="hybrid")
    b = Apex(distance=120, x=0, y=0, speed=85, method="hybrid")   # closer to a, slower
    c = Apex(distance=400, x=0, y=0, speed=100, method="hybrid")
    merged = _merge_close([a, b, c], min_sep=50)
    assert len(merged) == 2, f"Merge failed: {merged}"
    assert merged[0].speed == 85, "Should keep slower of the merged pair"
    print(f"  merge OK ({len(merged)} apexes after merging, slowest kept)")


def test_segmentation_and_features():
    tel, _, _ = make_synthetic_lap()
    config = PipelineConfig()
    apexes = detect_apex_hybrid(tel, config)
    sectors = segment_apex_to_apex(tel, apexes, min_length=50)
    assert len(sectors) >= 1, "Should produce at least one sector"
    metadata = {"year": 2025, "gp": "Synthetic", "driver": "TST"}
    features = extract_features(sectors, metadata)
    assert not features.empty, "Features should not be empty"
    assert "L_straight_m" in features.columns
    assert features["L_straight_m"].iloc[0] > 0
    print(f"  {len(sectors)} sector(s), L_straight={features['L_straight_m'].iloc[0]:.1f}m, "
          f"v_exit={features['v_exit_kph'].iloc[0]:.1f} -> v_entry={features['v_entry_target_kph'].iloc[0]:.1f} kph")


if __name__ == "__main__":
    print("Running synthetic smoke tests...\n")
    test_curvature()
    test_apex_detection()
    test_merge()
    test_segmentation_and_features()
    print("\nAll synthetic tests passed.")
