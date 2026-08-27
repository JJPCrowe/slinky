# F1 Telemetry → Micro-Sector Feature Pipeline

Phase 1 of the dissertation methodology. Extracts apex-to-apex
micro-sectors from FastF1 telemetry and produces the tabular feature
matrix consumed by the Phase 2 OCP (CasADi) and Phase 3 surrogate
(XGBoost).

## Setup

```bash
pip install -r requirements.txt
```

FastF1 maintains its own on-disk cache. First run for a given session
downloads from the F1 live timing servers (~10–30 MB per session);
subsequent runs are instant.

## Usage

### Single session (sanity check)

```bash
python run_pipeline.py --year 2025 --gp Silverstone --session Q -v
```

Outputs `output/microsectors_2025_Silverstone_Q.parquet` and a
diagnostics parquet with detector-agreement metrics per driver.

### Full 2025 season

```bash
python run_pipeline.py --year 2025 --season -v
```

Expected runtime: 20–60 minutes depending on cache state and
connection. Produces ~20 GPs × ~17 drivers × ~15 sectors/lap ≈
**~5,000–6,000 micro-sectors**. To clear the 10,000 target from
Objective 2, either add the 2024 season or expand to all clean
qualifying flying laps per driver (a one-line change in `loader.py`).

### Parameter sweeps

All tunables live in `f1_pipeline/config.py`. CLI flags exist for
the two most-swept parameters:

```bash
python run_pipeline.py --year 2025 --season --curvature-threshold 0.004 --resample-dx 1.0
```

### Synthetic smoke test (no network needed)

```bash
python test_synthetic.py
```

Verifies curvature computation, apex detector, segmentation, and
feature extraction on a synthetic two-corner track. Useful for
regression-testing after any edit to the algorithmic code.

## Architecture

```
f1_pipeline/
├── config.py          # tunable parameters in one place
├── loader.py          # session loading + lap selection
├── telemetry.py       # extraction, resampling, median + Savitzky-Golay
├── apex_detection.py  # hybrid + circuit_info detectors, agreement
├── segmentation.py    # apex-to-apex micro-sectors
├── features.py        # per-sector feature extraction
└── pipeline.py        # orchestrator
run_pipeline.py        # CLI entry point
test_synthetic.py      # offline smoke tests
```

## Methodological findings (for the dissertation methods chapter)

### Elevation channel reliability

The broadcast Z (elevation) channel was excluded from the feature
matrix after empirical testing on the 2025 Monaco GP qualifying
session. Sustained corruption blocks were observed in tunnel sections
where satellite lock is lost — `elev_range_m` values of ~280 m
appeared in micro-sectors covering the Monaco tunnel, against a true
circuit altitude differential of ~32 m. Neither Savitzky-Golay
smoothing nor 5-sample median filtering rejected the corruption
(it spans ~195 consecutive samples, exceeding any reasonable kernel
width).

Decision: drop Z from `_CHANNELS` and the feature matrix. The
dissertation's Phase 2 OCP uses a longitudinal-only vehicle model
(per proposal section 5.2); where altitude is required (e.g., for
the `m·g·sin(θ)` gradient term on undulating circuits like Spa or
Austin), it should be sourced from FIA-published circuit altitude
profiles, which are stable and independent of broadcast GPS quality.

### Detector agreement variance

The hybrid (curvature-gated speed minima) and circuit_info detectors
showed substantially different agreement rates between circuits in
initial testing (Silverstone: 5.6%; Monaco: 31.6%). This is
track-dependent rather than a systematic offset, and consistent with
the hypothesis that the hybrid detector's curvature threshold is
calibrated for low-radius corners and underperforms on high-speed
sweepers. Since the pipeline preferentially uses `circuit_info`
(FIA ground truth) where available, this does not affect the produced
feature matrix; the agreement metric is logged per-driver in the
diagnostics parquet for transparency, and will be investigated
during the validation phase.

## Known limitations

* **One lap per driver**: pipeline currently picks each driver's
  fastest qualifying lap. If a driver's Q1 fastest was deleted for
  track limits and their remaining laps are slow, they will still
  appear with a slow lap. Add a 107%-of-fastest filter in `loader.py`
  if this becomes a problem.

* **No S/F-line wrap-around**: micro-sectors are built between
  consecutive apexes within a lap. The final corner of lap N to the
  first corner of lap N+1 is *not* a sector. This is fine because
  qualifying laps are isolated — but for race data this would need
  the next-lap apex to be threaded in.

* **`circuit_info` coverage**: confirmed available on 2024+ FastF1
  data. If a 2025 round is missing metadata, the pipeline falls back
  to hybrid automatically; check the `detector` column to see which
  was used per row.

* **Active-aero / energy features are not in this matrix**: Phase 1
  produces only the *geometric and kinematic* input space. The
  energy budget and aero-state sweeps belong to Phase 2 (the CasADi
  OCP), which augments these rows with the corresponding optimal
  control outputs as labels.

## Next steps (Phase 2 hook)

The OCP will:
1. Read this parquet file
2. For each row, sweep initial SoC ∈ [10%, 100%] in K steps
3. Solve the CasADi NLP for optimal (d_X, v_taper, d_coast)
4. Append the three labels and the resulting Δt_optimal as new columns

Result: the ~5,000–6,000 micro-sectors × K SoC samples → 10,000+
training rows for the XGBoost surrogate.
