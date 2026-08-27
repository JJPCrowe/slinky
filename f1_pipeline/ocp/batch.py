"""
Batch OCP runner — sweeps micro-sectors × initial SoC, writes labelled parquet.

Reads the Phase 1 feature matrix (combined 2024+2025 qualifying parquet),
generates K initial-SoC scenarios per row by sweeping initial_SoC across a
user-supplied grid (default 10 values from 0.1 to 1.0), solves the OCP for
each scenario, and appends the label columns and convergence diagnostics.
Warm-starts each next solve from the previous SoC's result to accelerate
convergence.

PARALLEL EXECUTION (v4 — supervised workers):
concurrent.futures.ProcessPoolExecutor was retired after three distinct
production incidents on Windows / Python 3.14: one hard native worker
crash (MUMPS "Problem with integer stack size" → BrokenProcessPool) and
two silent spawn-stage hangs (workers at 0% CPU, no exception ever
raised — the second precisely at 6 workers × max_tasks_per_child = 192
tasks, i.e. the first worker-replacement wave). The executor cannot
express "kill a worker that stopped responding", so it is replaced by a
supervised layer on raw multiprocessing:

    * Direct assignment: one inbox Queue per worker; the parent knows
      exactly which row every worker holds, so a killed worker's row is
      requeued with no shared-queue races.
    * Handshake watchdog: workers announce readiness after imports; a
      spawn with no handshake inside STARTUP_TIMEOUT_S is killed and
      retried. Three consecutive spawn failures abandon that worker
      slot (ERROR) rather than blocking the run. Startup is staggered
      STARTUP_STAGGER_S apart to serialise native DLL loads.
    * Task watchdog: a row exceeding TASK_TIMEOUT_S has its worker
      killed and respawned and the row retried — this also covers
      native HANGS (e.g. a wedged linear solver), which no
      crash-detection scheme can see.
    * Failure ladder: worker death and worker timeout both count as
      attempts on the row in flight; MAX_ROW_ATTEMPTS failures on the
      same row → crash-marked rows (ocp_status = "worker_crashed",
      NaN labels), an ERROR log line, and the batch continues.
    * No scheduled worker recycling — the replacement-spawn trigger
      class is eliminated; degraded workers are replaced on evidence
      (death/timeout) instead of on a schedule.
    * If every worker slot is abandoned with rows still pending, the
      remainder runs serially in the parent (loud WARNING; a native
      fault then kills the run, and chunk-level resumability recovers).

Thread pinning to 1 BLAS/OpenMP thread per process is set below, BEFORE
numpy/casadi import, and inherited by spawned workers.

Progress heartbeat: a log line every 10 completed rows with cumulative
rate and ETA, so a quiet log is never ambiguous — silence beyond a few
minutes is a fault, not patience. Watchdog interventions (respawns,
timeouts, abandoned slots) are logged explicitly as they happen.

Output schema = input schema + appended columns:
    zone_eligible          (bool; only when shut_joblist is given —
                            False = solved with force_aero_shut)
    initial_SoC            (float, [0, 1] — fraction of e_batt_capacity)
    E_initial              (J)
    energy_price           (s/J; lambda, the swept co-state — problem.py
                            module docstring section D)
    d_X_optimal            (m)
    v_taper_optimal        (W per m/s; NaN where fit ill-conditioned)
    P_deploy_mean_optimal  (W; RAW accounting as of v3.1, WHEEL power;
                            NaN if no deploy — see solver.py module
                            docstring, "v3.1 CHANGE")
    E_deploy_optimal       (J; RAW accounting as of v3.1)
    E_harvest_optimal      (J; RAW accounting as of v3.1)
    P_deploy_mean_canonical (W; canonical accounting; diagnostic,
                            transition-period column — see solver.py)
    E_deploy_canonical     (J; canonical accounting; diagnostic)
    E_harvest_canonical    (J; canonical accounting; diagnostic)
    E_final                (J; RAW accounting as of v3.1 pass 2 — the OCP's
                            own solved E[N]; true store energy, NOT wheel-
                            mechanical like E_deploy/E_harvest)
    E_final_canonical      (J; canonical accounting; diagnostic — see
                            solver.py, this basis integrates with unity
                            efficiency even under v3, not comparable to
                            E_final without accounting for that)
    E_har_final            (J; terminal cumulative Recharge at the CU-K HV
                            DC bus, C5.2.10; raw — not canonically
                            reallocated)
    d_coast_optimal        (m; raw control series)
    dt_optimal             (s)
    ocp_converged          (bool)
    ocp_iterations         (int)
    ocp_status             (str; "worker_crashed" marks rows lost to
                            native solver faults or hangs)
    solve_time_s           (float; pure IPOPT wall-clock per solve)
    total_time_s           (float; build + solve + extract per scenario,
                            incl. any cold-start retry)
    E_realloc_delta_J      (float; E_harvest canonical − raw per solve)

Batch semantics:
    * energy_price (lambda, s/J) is swept over a grid (default:
      default_lambda_grid()) NESTED INSIDE the SoC loop in _solve_row, and
      threaded to every build_ocp call. lambda replaces the v2
      terminal_energy_weight keyword — same algebra (-lambda*E[N]) — but
      it is now a genuine shadow price rather than a calibrated tie-break,
      and must be strictly positive (build_ocp raises on energy_price <=
      0; the withdrawn terminal_energy_weight keyword now raises
      TypeError rather than being silently aliased). See problem.py
      module docstring section D.
    * shut_joblist marks instances to solve with force_aero_shut=True
      (zone-ineligible sectors) within a SINGLE full-batch pass; adds
      the zone_eligible column. Production mode.
    * joblist (filter) restricts the batch to listed instances — kept
      for smoke tests and targeted re-solves.

Parallelism: one micro-sector row per task (the warm-start chain runs
sequentially WITHIN a row's SoC x lambda sweep — lambda ascending inside
each SoC, SoC-to-SoC chaining as the outer level — but DIFFERENT rows
are independent). Per TR-4 mitigation in the proposal.
"""

from __future__ import annotations

import logging
import os

# Thread pinning MUST precede numpy/casadi import (workers inherit the
# environment at spawn). setdefault so a deliberate user override wins.
for _v in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_v, "1")

import multiprocessing as mp
import queue as queue_mod
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from f1_pipeline.ocp.problem import SectorInputs, build_ocp
from f1_pipeline.ocp.solver import OCPResult, solve_ocp
from f1_pipeline.ocp.vehicle import VehicleParams, default_params


logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Required input columns and how they map to SectorInputs
# ----------------------------------------------------------------------
# These names match the Phase 1 feature matrix produced by features.py.
# Speeds are km/h, length is metres — confirmed against the combined
# 2024+2025 Q parquet schema.
COL_V_EXIT = "v_exit_kph"
COL_V_ENTRY_TARGET = "v_entry_target_kph"
COL_L_STRAIGHT = "L_straight_m"
COL_SECTOR_ID = "sector_id"


REQUIRED_INPUT_COLS = [COL_V_EXIT, COL_V_ENTRY_TARGET, COL_L_STRAIGHT]

# Instance key for job-list operations. Matches rerun_joblist_v1.csv.
JOBLIST_KEYS = ["year", "gp", "driver", "sector_id"]

# Supervision parameters
STARTUP_TIMEOUT_S = 180.0     # worker must handshake within this
STARTUP_STAGGER_S = 1.0       # delay between worker launches
TASK_TIMEOUT_S = 900.0        # per-row deadline (typical row ~16 s)
MAX_ROW_ATTEMPTS = 3          # kills/deaths on a row before crash-marking
MAX_SPAWN_FAILURES = 3        # consecutive failed spawns before a slot is abandoned
HEARTBEAT_ROWS = 10           # progress log cadence (completed rows)
SUPERVISOR_POLL_S = 1.0       # result-queue poll / housekeeping interval


# ----------------------------------------------------------------------
# Default SoC sweep
# ----------------------------------------------------------------------
def default_soc_grid(k: int = 10) -> np.ndarray:
    """K evenly-spaced initial-SoC values across [0.1, 1.0]."""
    return np.linspace(0.10, 1.00, k)


# ----------------------------------------------------------------------
# Default lambda (energy_price) sweep
# ----------------------------------------------------------------------
def default_lambda_grid(k: int = 5) -> np.ndarray:
    """K log-spaced energy_price (lambda, s/J) values, strictly positive.

    PLACEHOLDER pending calibration. problem.py module docstring section D
    is explicit that lambda must be strictly positive (energy_price = 0 is
    rejected by build_ocp) and that the bottom of the grid should be set
    to the calibrated v2 tie-break epsilon, not to zero — that calibrated
    value has not been transcribed here. This default is a log-spaced
    placeholder range and MUST be overridden with the calibrated value
    before a production run.
    """
    return np.geomspace(1e-6, 1e-2, k)


# ----------------------------------------------------------------------
# Progress heartbeat
# ----------------------------------------------------------------------
def _heartbeat(done_rows: int, total_rows: int, t_start: float) -> None:
    elapsed = time.time() - t_start
    rate = done_rows / elapsed if elapsed > 0 else 0.0
    remaining = total_rows - done_rows
    eta_min = remaining / rate / 60.0 if rate > 0 else float("inf")
    logger.info("  ... %d/%d rows | %.1f rows/min | ETA %.1f min",
                done_rows, total_rows, rate * 60.0, eta_min)


# ----------------------------------------------------------------------
# Job-list handling
# ----------------------------------------------------------------------
def _read_joblist_keys(df: pd.DataFrame, joblist_path: Path) -> pd.DataFrame:
    """
    Read a job-list CSV and return its unique instance keys, dtype-cast
    to match the feature matrix. Reference columns beyond the keys are
    ignored. Raises on missing keys or uncastable dtypes — a silent
    dtype mismatch would otherwise produce an empty or partial join and
    a quietly wrong batch.
    """
    job = pd.read_csv(joblist_path)
    missing_job = [k for k in JOBLIST_KEYS if k not in job.columns]
    missing_df = [k for k in JOBLIST_KEYS if k not in df.columns]
    if missing_job or missing_df:
        raise KeyError(
            f"Job-list handling requires keys {JOBLIST_KEYS}; "
            f"missing in joblist: {missing_job}, missing in feature matrix: {missing_df}"
        )
    keys = job[JOBLIST_KEYS].drop_duplicates().copy()
    for k in JOBLIST_KEYS:
        try:
            keys[k] = keys[k].astype(df[k].dtype)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Cannot cast joblist key '{k}' ({keys[k].dtype}) to feature "
                f"matrix dtype {df[k].dtype}: {exc}"
            ) from exc
    return keys


def _filter_to_joblist(df: pd.DataFrame, joblist_path: Path) -> pd.DataFrame:
    """Restrict the feature matrix to the instances in a job-list CSV."""
    keys = _read_joblist_keys(df, joblist_path)
    filtered = df.merge(keys, on=JOBLIST_KEYS, how="inner")
    if len(filtered) != len(keys):
        raise RuntimeError(
            f"Job-list join mismatch: {len(keys)} unique instances in the "
            f"job list but {len(filtered)} matched rows in the feature "
            f"matrix. Expected exactly one row per instance. Check key "
            f"dtypes and that the SAME Phase 1 parquet used previously is "
            f"being used here."
        )
    return filtered


def _mark_shut_instances(df: pd.DataFrame, shut_joblist_path: Path) -> pd.DataFrame:
    """
    Add zone_eligible (bool) to the feature matrix: False for instances
    listed in the shut job list (solved with force_aero_shut=True),
    True otherwise. Asserts every listed instance matches exactly one
    feature-matrix row — a partial match means the wrong Phase 1 file
    or a key drift, and must stop the batch.
    """
    keys = _read_joblist_keys(df, shut_joblist_path)
    marked = df.merge(keys.assign(_force_shut=True),
                      on=JOBLIST_KEYS, how="left")
    shut_mask = marked["_force_shut"].notna()
    n_matched = int(shut_mask.sum())
    if n_matched != len(keys):
        raise RuntimeError(
            f"Shut job-list mismatch: {len(keys)} unique instances listed "
            f"but {n_matched} matched rows in the feature matrix. Every "
            f"listed instance must match exactly one row."
        )
    marked["zone_eligible"] = ~shut_mask
    return marked.drop(columns=["_force_shut"])


# ----------------------------------------------------------------------
# Per-row solve (one micro-sector × all SoC values)
# ----------------------------------------------------------------------
def _solve_row(
    row_dict: dict,
    soc_grid: np.ndarray,
    lambda_grid: np.ndarray,
    params: VehicleParams,
    N: int,
    force_aero_shut: bool,
) -> List[dict]:
    """
    Process a single micro-sector row across the SoC grid, with the
    lambda (energy_price) grid swept inside each SoC.

    Returns one output dict per (SoC, lambda) scenario, ready to be
    concatenated into the labelled parquet.

    Warm-start chain: a single `warm` handle threads through the nested
    loop in (SoC, lambda) order — lambda ascending within a SoC (each
    solve warm-starts from the previous lambda at the SAME SoC, since the
    parameter step is small and IPOPT converges in a fraction of the
    cold-start iterations), and the last-lambda result of one SoC seeds
    the first lambda of the next, preserving the existing SoC-to-SoC
    chaining as the outer level.
    """
    results: List[dict] = []
    warm: Optional[OCPResult] = None

    # Phase 1 stores speeds in km/h (confirmed by *_kph column suffix);
    # convert to m/s for the SI-unit OCP.
    v_exit_ms = float(row_dict[COL_V_EXIT]) / 3.6
    v_entry_ms = float(row_dict[COL_V_ENTRY_TARGET]) / 3.6
    L = float(row_dict[COL_L_STRAIGHT])

    # Initial SoC is the fraction of battery STORAGE CAPACITY at sector
    # start (a stock variable), NOT the fraction of the per-lap deployment
    # budget (a flow variable). These are distinct quantities — see the
    # note in vehicle_parameters.md under VP-13 vs VP-14. Conflating them
    # makes the OCP infeasible on regen-heavy sectors at high SoC because
    # E_initial would exceed the physical battery capacity.
    for soc in soc_grid:
        E_init = float(soc) * params.e_batt_capacity
        inputs = SectorInputs(
            v_exit=v_exit_ms,
            v_entry_target=v_entry_ms,
            L_straight=L,
            E_initial=E_init,
            sector_id=str(row_dict.get(COL_SECTOR_ID, "")),
        )

        for lam in lambda_grid:
            energy_price = float(lam)

            # total_time_s times the full scenario cost — build + solve +
            # label extraction, including any cold-start retry. This is
            # the per-scenario wall cost the surrogate replaces in
            # deployment. solve_time_s (from OCPResult) times pure IPOPT
            # for the kept attempt only — the conservative comparator.
            t_scenario0 = time.perf_counter()
            try:
                handle = build_ocp(
                    inputs, params, N=N, force_aero_shut=force_aero_shut,
                    energy_price=energy_price,
                )
                result = solve_ocp(handle, warm_start=warm)

                # Cold-start fallback: if the warm-started solve failed,
                # retry once with a fresh problem (no warm-start). This
                # prevents a bad result early in the chain from poisoning
                # every subsequent solve in the sweep.
                if (not result.converged) and (warm is not None):
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Warm-start failed on sector %s SoC %.2f "
                            "lambda %.3g (%s); retrying cold.",
                            inputs.sector_id, soc, energy_price,
                            result.solver_status,
                        )
                    handle_cold = build_ocp(
                        inputs, params, N=N, force_aero_shut=force_aero_shut,
                        energy_price=energy_price,
                    )
                    result_cold = solve_ocp(handle_cold, warm_start=None)
                    # Keep the better outcome
                    if result_cold.converged:
                        result = result_cold
            except Exception as exc:  # noqa: BLE001 (catch all to keep batch alive)
                logger.warning(
                    "OCP exception on sector %s SoC %.2f lambda %.3g: %s",
                    inputs.sector_id, soc, energy_price, exc,
                )
                result = None
            total_time = time.perf_counter() - t_scenario0

            # Update warm-start chain only on genuine convergence
            if result is not None and result.converged:
                warm = result
            else:
                # Reset warm chain on failure so the NEXT solve starts cold
                warm = None

            results.append(
                _result_row(row_dict, soc, E_init, energy_price, result,
                            total_time)
            )

    return results


def _result_row(
    row_dict: dict,
    soc: float,
    E_init: float,
    energy_price: float,
    result: Optional[OCPResult],
    total_time: float,
    status_if_none: str = "exception",
) -> dict:
    """Assemble one output row; NaN labels when the solve produced nothing."""
    out = dict(row_dict)  # carry through original columns
    out["initial_SoC"] = float(soc)
    out["E_initial"] = E_init
    out["energy_price"] = float(energy_price)
    if result is None:
        out["d_X_optimal"] = float("nan")
        out["v_taper_optimal"] = float("nan")
        out["P_deploy_mean_optimal"] = float("nan")
        out["E_deploy_optimal"] = float("nan")
        out["E_harvest_optimal"] = float("nan")
        out["P_deploy_mean_canonical"] = float("nan")
        out["E_deploy_canonical"] = float("nan")
        out["E_harvest_canonical"] = float("nan")
        out["E_final"] = float("nan")
        out["E_final_canonical"] = float("nan")
        out["E_har_final"] = float("nan")
        out["d_coast_optimal"] = float("nan")
        out["dt_optimal"] = float("nan")
        out["ocp_converged"] = False
        out["ocp_iterations"] = -1
        out["ocp_status"] = status_if_none
        out["solve_time_s"] = float("nan")
        out["total_time_s"] = total_time
        out["E_realloc_delta_J"] = float("nan")
    else:
        out["d_X_optimal"] = result.d_X_optimal
        out["v_taper_optimal"] = result.v_taper_optimal
        out["P_deploy_mean_optimal"] = result.P_deploy_mean_optimal
        out["E_deploy_optimal"] = result.E_deploy_optimal
        out["E_harvest_optimal"] = result.E_harvest_optimal
        out["P_deploy_mean_canonical"] = result.P_deploy_mean_canonical
        out["E_deploy_canonical"] = result.E_deploy_canonical
        out["E_harvest_canonical"] = result.E_harvest_canonical
        out["E_final"] = result.E_final
        out["E_final_canonical"] = result.E_final_canonical
        out["E_har_final"] = result.E_har_final
        out["d_coast_optimal"] = result.d_coast_optimal
        out["dt_optimal"] = result.dt_optimal
        out["ocp_converged"] = result.converged
        out["ocp_iterations"] = result.iterations
        out["ocp_status"] = result.solver_status
        out["solve_time_s"] = result.solve_time_s
        out["total_time_s"] = total_time
        out["E_realloc_delta_J"] = result.E_realloc_delta_J
    return out


def _crash_rows(row_dict: dict, soc_grid: np.ndarray, lambda_grid: np.ndarray,
                params: VehicleParams) -> List[dict]:
    """Placeholder rows for a micro-sector whose solve repeatedly kills
    or hangs the worker process (native solver fault). Keeps the output
    row-count contract intact (one row per SoC x lambda scenario) while
    marking the loss loudly."""
    return [
        _result_row(
            row_dict, float(soc), float(soc) * params.e_batt_capacity,
            float(lam), None, float("nan"), status_if_none="worker_crashed",
        )
        for soc in soc_grid
        for lam in lambda_grid
    ]


# ----------------------------------------------------------------------
# Supervised worker layer
# ----------------------------------------------------------------------
def _worker_main(
    worker_id: int,
    inbox,
    result_queue,
    soc_grid: np.ndarray,
    lambda_grid: np.ndarray,
    params: VehicleParams,
    N: int,
) -> None:
    """
    Worker process entry point. Announces readiness after imports (the
    handshake the parent's startup watchdog waits for), then serves
    row tasks from its private inbox until it receives None.

    Message protocol (worker -> parent, via result_queue):
        ("ready", worker_id)
        ("done",  worker_id, row_index, [result rows])
    Parent -> worker, via inbox:
        (row_index, row_dict, force_aero_shut)   or   None (shutdown)
    """
    result_queue.put(("ready", worker_id))
    while True:
        task = inbox.get()
        if task is None:
            return
        row_index, row_dict, force_flag = task
        rows = _solve_row(
            row_dict, soc_grid, lambda_grid, params, N, force_flag,
        )
        result_queue.put(("done", worker_id, row_index, rows))


class _WorkerSlot:
    """Parent-side bookkeeping for one worker process."""

    def __init__(self, slot_id: int):
        self.slot_id = slot_id
        self.proc: Optional[mp.process.BaseProcess] = None
        self.inbox = None
        self.ready = False
        self.spawned_at = 0.0
        self.current_task: Optional[int] = None   # row index in flight
        self.task_started_at = 0.0
        self.spawn_failures = 0
        self.abandoned = False


def _run_supervised(
    row_dicts: List[dict],
    soc_grid: np.ndarray,
    lambda_grid: np.ndarray,
    params: VehicleParams,
    N: int,
    _row_flag,
    n_workers: int,
    t_start: float,
) -> Dict[int, List[dict]]:
    """
    Supervised parallel execution (see module docstring for rationale).
    Returns {row_index: [result rows]} for every input row — by
    completion, retry, or crash-marking. Never returns partially.
    """
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    n_total = len(row_dicts)

    pending: List[int] = list(range(n_total))       # rows awaiting assignment
    attempts: Dict[int, int] = {i: 0 for i in range(n_total)}
    done: Dict[int, List[dict]] = {}

    slots = [_WorkerSlot(s) for s in range(max(1, n_workers))]

    def spawn(slot: _WorkerSlot) -> None:
        slot.inbox = ctx.Queue()
        slot.proc = ctx.Process(
            target=_worker_main,
            args=(slot.slot_id, slot.inbox, result_queue, soc_grid,
                  lambda_grid, params, N),
            daemon=True,
        )
        slot.proc.start()
        slot.ready = False
        slot.spawned_at = time.time()
        slot.current_task = None

    def kill(slot: _WorkerSlot) -> None:
        if slot.proc is not None and slot.proc.is_alive():
            slot.proc.kill()
            slot.proc.join(timeout=5.0)
        slot.proc = None
        slot.ready = False
        slot.current_task = None

    def requeue_inflight(slot: _WorkerSlot, reason: str) -> None:
        """Return a killed/dead worker's row to the queue or crash-mark it."""
        i = slot.current_task
        slot.current_task = None
        if i is None:
            return
        attempts[i] += 1
        if attempts[i] >= MAX_ROW_ATTEMPTS:
            row = row_dicts[i]
            logger.error(
                "Row %d (sector_id=%s, gp=%s) failed %d attempts (%s) — "
                "recording %d crash-marked scenarios and continuing.",
                i, row.get(COL_SECTOR_ID, "?"), row.get("gp", "?"),
                attempts[i], reason, len(soc_grid) * len(lambda_grid),
            )
            done[i] = _crash_rows(row, soc_grid, lambda_grid, params)
        else:
            logger.warning(
                "Row %d returned to queue after %s (attempt %d/%d).",
                i, reason, attempts[i], MAX_ROW_ATTEMPTS,
            )
            pending.append(i)

    def assign(slot: _WorkerSlot) -> None:
        if pending and slot.ready and slot.current_task is None:
            i = pending.pop(0)
            slot.current_task = i
            slot.task_started_at = time.time()
            slot.inbox.put((i, row_dicts[i], _row_flag(row_dicts[i])))

    # Staggered initial launch — serialises native DLL loads.
    for slot in slots:
        spawn(slot)
        logger.info("Worker slot %d launched (pid %s).",
                    slot.slot_id, slot.proc.pid)
        time.sleep(STARTUP_STAGGER_S)

    last_heartbeat_at = 0
    while len(done) < n_total:
        # Drain results
        try:
            msg = result_queue.get(timeout=SUPERVISOR_POLL_S)
        except queue_mod.Empty:
            msg = None
        if msg is not None:
            kind = msg[0]
            if kind == "ready":
                slot = slots[msg[1]]
                slot.ready = True
                slot.spawn_failures = 0
                logger.info("Worker slot %d ready.", slot.slot_id)
                assign(slot)
            elif kind == "done":
                _, wid, i, rows = msg
                slot = slots[wid]
                done[i] = rows
                slot.current_task = None
                if len(done) >= last_heartbeat_at + HEARTBEAT_ROWS:
                    _heartbeat(len(done), n_total, t_start)
                    last_heartbeat_at = len(done)
                assign(slot)
            continue  # drain queue eagerly before housekeeping

        # Housekeeping (runs when the queue is momentarily quiet)
        now = time.time()
        for slot in slots:
            if slot.abandoned:
                continue
            alive = slot.proc is not None and slot.proc.is_alive()

            if not alive:
                # Worker died (native crash or exit).
                requeue_inflight(slot, "worker death")
                slot.spawn_failures += (0 if slot.ready else 1)
                if (not slot.ready
                        and slot.spawn_failures >= MAX_SPAWN_FAILURES):
                    slot.abandoned = True
                    logger.error(
                        "Worker slot %d abandoned after %d failed "
                        "startups.", slot.slot_id, slot.spawn_failures,
                    )
                    continue
                logger.warning("Worker slot %d died — respawning.",
                               slot.slot_id)
                kill(slot)
                spawn(slot)
                continue

            if not slot.ready:
                # Spawn-stage watchdog.
                if now - slot.spawned_at > STARTUP_TIMEOUT_S:
                    slot.spawn_failures += 1
                    logger.warning(
                        "Worker slot %d failed to handshake within %.0f s "
                        "(spawn hang) — killing (failure %d/%d).",
                        slot.slot_id, STARTUP_TIMEOUT_S,
                        slot.spawn_failures, MAX_SPAWN_FAILURES,
                    )
                    kill(slot)
                    if slot.spawn_failures >= MAX_SPAWN_FAILURES:
                        slot.abandoned = True
                        logger.error("Worker slot %d abandoned after %d "
                                     "failed startups.", slot.slot_id,
                                     slot.spawn_failures)
                    else:
                        spawn(slot)
                continue

            if slot.current_task is not None:
                # Task watchdog.
                if now - slot.task_started_at > TASK_TIMEOUT_S:
                    logger.warning(
                        "Worker slot %d exceeded %.0f s on row %d "
                        "(native hang) — killing and respawning.",
                        slot.slot_id, TASK_TIMEOUT_S, slot.current_task,
                    )
                    requeue_inflight(slot, "task timeout")
                    kill(slot)
                    spawn(slot)
            else:
                assign(slot)

        # All slots gone but work remains → serial fallback in parent.
        if all(s.abandoned for s in slots) and len(done) < n_total:
            logger.error(
                "All worker slots abandoned with %d rows pending — "
                "falling back to serial execution in the parent process. "
                "A native fault now kills the run; chunk resumability "
                "recovers it.", n_total - len(done),
            )
            for i in list(pending):
                done[i] = _solve_row(
                    row_dicts[i], soc_grid, lambda_grid, params, N,
                    _row_flag(row_dicts[i]),
                )
                if len(done) >= last_heartbeat_at + HEARTBEAT_ROWS:
                    _heartbeat(len(done), n_total, t_start)
                    last_heartbeat_at = len(done)
            pending.clear()
            # Any rows that were in flight on abandoned slots were already
            # requeued or crash-marked by requeue_inflight.
            for i in range(n_total):
                if i not in done:
                    done[i] = _solve_row(
                        row_dicts[i], soc_grid, lambda_grid, params, N,
                        _row_flag(row_dicts[i]),
                    )

    # Shutdown: sentinels to live workers, then join/kill.
    for slot in slots:
        if slot.proc is not None and slot.proc.is_alive():
            try:
                slot.inbox.put(None)
            except Exception:  # noqa: BLE001
                pass
    deadline = time.time() + 10.0
    for slot in slots:
        if slot.proc is not None:
            slot.proc.join(timeout=max(0.1, deadline - time.time()))
            if slot.proc.is_alive():
                slot.proc.kill()

    return done


# ----------------------------------------------------------------------
# Top-level batch driver
# ----------------------------------------------------------------------
def run_batch(
    input_parquet: Path,
    output_parquet: Path,
    *,
    soc_grid: Optional[np.ndarray] = None,
    lambda_grid: Optional[np.ndarray] = None,
    params: Optional[VehicleParams] = None,
    N: int = 50,
    n_workers: int = 1,
    limit: Optional[int] = None,
    force_aero_shut: bool = False,
    joblist: Optional[Path] = None,
    shut_joblist: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Drive the full batch: read parquet, sweep, write parquet, return DataFrame.

    Parameters
    ----------
    input_parquet : Path
        Combined 2024+2025 Q micro-sector feature matrix from Phase 1.
    output_parquet : Path
        Destination for the labelled feature matrix.
    soc_grid : np.ndarray, optional
        SoC values to sweep per micro-sector. Defaults to 10 points
        across [0.1, 1.0] (default_soc_grid()).
    lambda_grid : np.ndarray, optional
        energy_price (lambda, s/J) values to sweep, NESTED inside the SoC
        loop, per build_ocp call. Defaults to default_lambda_grid() — a
        PLACEHOLDER pending calibration (problem.py module docstring
        section D); override with the calibrated grid before a
        production run. lambda replaces the v2 terminal_energy_weight
        keyword and must be strictly positive; passing the old keyword to
        build_ocp now raises TypeError by design.
    params : VehicleParams, optional
        Defaults to the placeholder set in vehicle.py.
    N : int
        Collocation intervals per OCP. 50 is the default.
    n_workers : int
        Worker processes for row-level parallelism. 1 = serial.
    limit : int, optional
        Truncate input to first `limit` rows for smoke-testing.
        Applied AFTER job-list handling when both are given.
    force_aero_shut : bool
        Global shut flag — every row solved with the aero variable
        pinned. Mutually exclusive with shut_joblist.
    joblist : Path, optional
        CSV of instance keys RESTRICTING the batch to listed instances
        (smoke tests, targeted re-solves).
    shut_joblist : Path, optional
        CSV of instance keys MARKING which rows are solved with
        force_aero_shut=True within a full-batch pass. Adds the
        zone_eligible column to the output. Production mode.
    """
    if force_aero_shut and shut_joblist is not None:
        raise ValueError(
            "force_aero_shut (global) and shut_joblist (per-row) are "
            "mutually exclusive — choose one regime mechanism."
        )
    if soc_grid is None:
        soc_grid = default_soc_grid()
    if lambda_grid is None:
        lambda_grid = default_lambda_grid()
    if params is None:
        params = default_params()

    df = pd.read_parquet(input_parquet)
    for col in REQUIRED_INPUT_COLS:
        if col not in df.columns:
            raise KeyError(
                f"Phase 1 parquet missing required column '{col}'. "
                f"Found columns: {list(df.columns)}"
            )
    if joblist is not None:
        n_before = len(df)
        df = _filter_to_joblist(df, joblist)
        logger.info(
            "Job-list filter: %d -> %d micro-sectors (%s)",
            n_before, len(df), joblist,
        )
    if shut_joblist is not None:
        df = _mark_shut_instances(df, shut_joblist)
        n_shut = int((~df["zone_eligible"]).sum())
        logger.info(
            "Regime marking: %d of %d micro-sectors force_aero_shut (%s)",
            n_shut, len(df), shut_joblist,
        )
    if limit is not None:
        df = df.head(limit)

    logger.info(
        "Phase 2 batch: %d micro-sectors x %d SoC x %d lambda = %d scenarios, "
        "workers=%d, lambda_grid=[%g, %g], regime=%s",
        len(df), len(soc_grid), len(lambda_grid),
        len(df) * len(soc_grid) * len(lambda_grid), n_workers,
        float(lambda_grid[0]), float(lambda_grid[-1]),
        ("per-row shut_joblist" if shut_joblist is not None
         else f"global force_aero_shut={force_aero_shut}"),
    )
    t0 = time.time()

    row_dicts = df.to_dict(orient="records")

    def _row_flag(row: dict) -> bool:
        if shut_joblist is not None:
            return not bool(row["zone_eligible"])
        return force_aero_shut

    if n_workers <= 1:
        results_by_row: Dict[int, List[dict]] = {}
        for i, row in enumerate(row_dicts):
            results_by_row[i] = _solve_row(
                row, soc_grid, lambda_grid, params, N, _row_flag(row),
            )
            if (i + 1) % HEARTBEAT_ROWS == 0:
                _heartbeat(i + 1, len(row_dicts), t0)
    else:
        results_by_row = _run_supervised(
            row_dicts, soc_grid, lambda_grid, params, N, _row_flag,
            n_workers, t0,
        )

    elapsed = time.time() - t0
    all_results = [r for i in sorted(results_by_row)
                   for r in results_by_row[i]]
    logger.info("Phase 2 batch complete: %d rows in %.1f s",
                len(all_results), elapsed)

    out_df = pd.DataFrame(all_results)
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(output_parquet, index=False)

    # Convergence + crash summary for the methods chapter
    n_conv = int(out_df["ocp_converged"].sum())
    logger.info(
        "Convergence: %d / %d (%.1f%%)",
        n_conv, len(out_df), 100.0 * n_conv / max(1, len(out_df)),
    )
    n_crash = int((out_df["ocp_status"] == "worker_crashed").sum())
    if n_crash:
        logger.error(
            "%d scenario(s) lost to native solver crashes/hangs "
            "(ocp_status == 'worker_crashed'). Investigate before "
            "training on this file.", n_crash,
        )

    return out_df
