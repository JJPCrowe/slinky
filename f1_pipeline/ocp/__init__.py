"""
Phase 2 — Optimal Control Problem (OCP) submodule.

Generates the mathematical ground-truth labels (d_X, v_taper, d_coast)
for each micro-sector × initial-SoC scenario in the Phase 1 feature matrix.
The CasADi-transcribed NLP is solved via IPOPT for every row, producing
the dataset that the Phase 3 XGBoost surrogate learns to approximate.

Module map:
    vehicle.py   — 2026 F1 vehicle parameters (placeholder + worksheet)
    dynamics.py  — longitudinal point-mass state derivatives
    problem.py   — CasADi Opti transcription (direct collocation)
    solver.py    — IPOPT interface, warm-start, result extraction
    batch.py     — sweep across micro-sectors × SoC values
"""

from f1_pipeline.ocp.vehicle import VehicleParams, default_params
from f1_pipeline.ocp.problem import build_ocp
from f1_pipeline.ocp.solver import solve_ocp, OCPResult
from f1_pipeline.ocp.batch import run_batch

__all__ = [
    "VehicleParams",
    "default_params",
    "build_ocp",
    "solve_ocp",
    "OCPResult",
    "run_batch",
]
