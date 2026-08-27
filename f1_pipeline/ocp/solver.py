"""
IPOPT solver wrapper and result extraction — v3.1 (raw energy accounting).

Wraps a built OCPHandle (problem.py) with the IPOPT plugin, solves, and
extracts the Phase 3 label variables from the optimal trajectory.

LABEL SEMANTICS (v3.1 — RAW is now the primary basis for everything,
including E_final as of the second v3.1 pass, Aug 2026):
    All trajectory AND energy-accounting labels are extracted from the RAW
    solved controls/states:
        d_X_optimal, d_coast_optimal, dt_optimal, v_taper_optimal,
        P_deploy_mean_optimal, E_deploy_optimal, E_harvest_optimal,
        E_final
    E_final is now the OCP's own solved E[N] (handle.E's terminal value) —
    a decision variable, raw by construction, not recomputed from anything.
    P_deploy_mean_optimal, E_deploy_optimal, E_harvest_optimal and E_final
    ALL get a parallel *_canonical sibling (P_deploy_mean_canonical,
    E_deploy_canonical, E_harvest_canonical, E_final_canonical) for one
    transition period, so the raw/canonical difference is measurable in the
    production labels rather than inferred after the fact.

v3.1 CHANGE — why the primary basis moved off canonical (Aug 2026, two
passes):
    Pass 1 (P_deploy/E_deploy/E_harvest): _canonical_energy_reallocation
    (still defined below, still called, see its own docstring) was built
    for v2's UNITY-EFFICIENCY world, where reassigning retard force from
    friction brake to regen was a pure win — regen and brake were
    physically interchangeable at fixed motion, so a "regen-first" greedy
    pass could only ever help or be neutral. Under v3, regen carries a
    genuine eta_regen < 1 cost and the raw solve is already price- and
    efficiency-aware: it trades regen against brake optimally given the
    true cost and the true (global, not just forward-local) capacity
    headroom. The canonical pass has no such foresight — it is a greedy,
    forward-only, locally-headroom-capped heuristic — and measured against
    the raw solve on the 10,000-solve v3 re-validation pool (2026-08-23/24),
    it UNDERSHOOTS raw harvest in 99.15% of solves (median −36 kJ per solve
    on a common DC-bus basis), the opposite of what "regen-first" promises.
    That is a defect in the reallocation relative to its own stated intent,
    not a legitimate design choice, and P_deploy_mean/E_deploy/E_harvest —
    P_deploy_mean being the primary Phase 3 surrogate target — were being
    measured against it.

    Pass 2 (E_final): E_final was left canonical in pass 1 as out of scope,
    which created a bookkeeping inconsistency (E_final wasn't reconcilable
    against the now-raw E_deploy/E_harvest) and, more importantly, a basis
    mismatch with the Phase 4 forward simulator, which propagates SoC using
    raw physics — training a surrogate on canonical E_final while the
    simulator runs on raw state describes two different vehicles, exactly
    the failure pass 1 was meant to remove. Diagnosed before changing
    anything, per instruction: E_final was NOT merely "the canonical
    F-split's terminal value" in the sense of reusing an otherwise-correct
    v3 integration — _canonical_energy_reallocation's own forward walk
    integrates `E = E - Fk*h`, i.e. dE/ds = -F' with UNITY efficiency,
    never applying eta_motor/eta_regen at all, even under v3. So the old
    E_final was doubly divorced from v3's actual dynamics: wrong force
    split (pass-1 defect) AND wrong (unity) efficiency in its own separate
    integration, while the OCP's own E[N] decision variable was sitting
    right there the whole time, solved via the ACTUAL v3 dynamics
    (dynamics.py: dE/ds = -F_dep/eta_motor + F_reg*eta_regen) via proper
    trapezoidal collocation. The original v2-era motivation was real (the
    module's historical rationale below explicitly names E_final's
    nondeterminism, up to the same ~11.3 kJ margin as E_harvest, as part of
    what canonical reallocation was built to fix) — but it rested on the
    same v2 unity-efficiency degeneracy pass 1 already retired, so it
    retires the same way, not by patching the old mechanism.

    Phase 3 results measured against the canonical basis (any of the four
    fields) should be re-run against raw.
    _canonical_energy_reallocation is NOT deleted: it is left in place,
    unused by the primary extraction path, so the labels it produced remain
    reproducible and auditable. Its own docstring and the v2-era rationale
    below still explain why it exists and what it was built to solve; they
    describe the v2/early-v3 problem it no longer needs to solve for the
    primary labels, not a currently-active code path.

d_coast_optimal was ALREADY raw in v3 (called with the raw F_mguk series,
never F_canon) — it required no change here. Confirm this from the call
site below rather than assuming; a prior task description characterized it
as canonical-derived, which the code does not support.

WHEEL vs DC-BUS POWER (state this so it cannot be misread again):
P_deploy_mean_optimal (and E_deploy_optimal) are WHEEL-equivalent
quantities — force integrated at the wheel, no efficiency applied — in
both the raw and canonical bases, in both v2 and v3. The regulatory 350 kW
cap (C5.2.7) is enforced at the DC bus (problem.py: P_dep_dc = F_dep·v /
eta_motor ≤ 350 kW); the WHEEL-equivalent ceiling implied by that DC-bus
cap is 350,000 × eta_motor = 332,500 W, not 350,000 W. Any "% of cap"
comparison against P_deploy_mean_optimal must use 332.5 kW, not 350 kW.

Historical rationale (v2/early-v3 calibration pre-flight, Aug 2026), for
why _canonical_energy_reallocation exists and is retained rather than
deleted: under the pure time objective (ε = 0) the trajectory v(s) is
deterministic (cold vs warm-chain solves agree to ≤ 28 µs in dt and 0.00 m
in d_coast), but the regen-vs-friction-brake SPLIT inside braking zones was
degenerate under v2's unity efficiency — the two retarders were
interchangeable at fixed motion, so IPOPT's landing point was
solver-path-dependent (raw E_harvest nondeterminism up to 11.3 kJ, with
ΔE_final ≈ ΔE_harvest and ΔE_deploy ≈ 0: the pure-split signature).
Objective-side tie-breaks were measured and rejected: the v1 friction-brake
penalty acted as a second objective (median 2.1%, max 7.27× of sector
time), and a terminal-energy value term −ε·E[N] re-created a SoC-keyed
d_coast artefact through the battery cap at every tested ε. The tie was
therefore resolved AFTER solving, in extraction — see
_canonical_energy_reallocation's own docstring for the mechanism. Under
v3's priced, efficiency-aware raw solve this degeneracy is far less
significant and the reallocation's own greedy-heuristic cost now exceeds
its benefit for P_deploy/E_deploy/E_harvest — hence the v3.1 change above.

    E_realloc_delta_J records E_harvest_canonical − E_harvest_raw per
    solve — the size of the (now-diagnostic-only) accounting correction —
    for batch QA and the methods chapter.

Labels:
    d_X_optimal          — distance along sector where aero variable a(s)
                           first crosses 0.5 (Z→X switch). NaN if no switch.
    v_taper_optimal      — best-fit linear slope dP_mguk/dv over the
                           deployment segment (W per m/s). GUARDED: NaN
                           unless the deployment phase spans enough
                           intervals and velocity range for the fit to be
                           well-conditioned (placeholder batch produced
                           |slope| up to 5e6 on degenerate fits).
    P_deploy_mean_optimal — mean MGU-K power over the deployment phase
                           (W), RAW accounting, WHEEL power (see above).
                           NaN if the sector never deploys.
    P_deploy_mean_canonical — same, canonical accounting. Diagnostic only;
                           transition-period column.
    E_deploy_optimal     — total electrical energy deployed (J, ≥ 0),
                           RAW accounting, WHEEL-equivalent.
    E_deploy_canonical   — same, canonical accounting. Diagnostic only.
    E_harvest_optimal    — total mechanical energy absorbed in regen
                           (J, ≥ 0; unity-efficiency model), RAW
                           accounting.
    E_harvest_canonical  — same, canonical accounting. Diagnostic only.
    E_final              — terminal battery energy (J), RAW accounting —
                           the OCP's own solved E[N], true v3 efficiency-
                           weighted dynamics. NOT wheel-mechanical like
                           E_deploy/E_harvest; this is actual store energy.
    E_final_canonical    — same, from _canonical_energy_reallocation's
                           own (unity-efficiency) forward walk. Diagnostic
                           only; NOT directly comparable to E_deploy/
                           E_harvest_canonical without accounting for that
                           walk's missing efficiencies.
    d_coast_optimal      — distance over which raw F_mguk(s) is negative
                           contiguously before the sector end. Always raw.
    dt_optimal           — converged sector traversal time (s).

Warm-start hooks: pass a previous OCPResult as `warm_start` and its
primal solution will be set as the initial guess for the new problem.
Warm-starting uses the RAW trajectories (the actual NLP primal), never
the canonical reallocation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from f1_pipeline.ocp.problem import OCPHandle


# ----------------------------------------------------------------------
# Result container
# ----------------------------------------------------------------------
@dataclass
class OCPResult:
    """Solution payload for a single OCP solve."""
    converged: bool
    iterations: int
    solver_status: str

    # Phase 3 labels
    d_X_optimal: float
    v_taper_optimal: float
    P_deploy_mean_optimal: float    # v3.1: RAW basis (was canonical)
    E_deploy_optimal: float         # v3.1: RAW basis (was canonical)
    E_harvest_optimal: float        # v3.1: RAW basis (was canonical)
    P_deploy_mean_canonical: float  # diagnostic, transition period only
    E_deploy_canonical: float       # diagnostic, transition period only
    E_harvest_canonical: float      # diagnostic, transition period only
    E_final: float                  # v3.1 pass 2: RAW basis (was canonical)
    E_final_canonical: float        # diagnostic, transition period only
    E_har_final: float
    d_coast_optimal: float
    dt_optimal: float

    # Full primal trajectory (for warm-starting and validation plots)
    s_grid: np.ndarray
    v_traj: np.ndarray
    E_traj: np.ndarray
    E_har_traj: np.ndarray
    F_ice_traj: np.ndarray
    F_dep_traj: np.ndarray
    F_reg_traj: np.ndarray
    F_mguk_traj: np.ndarray
    F_brake_traj: np.ndarray
    a_traj: np.ndarray

    # Diagnostic
    nlp_residual: float = math.nan
    solve_time_s: float = math.nan
    E_realloc_delta_J: float = math.nan


# ----------------------------------------------------------------------
# Solver entry point
# ----------------------------------------------------------------------
def solve_ocp(
    handle: OCPHandle,
    warm_start: Optional[OCPResult] = None,
    verbose: bool = False,
    max_iter: int = 500,
    tol: float = 1e-4,
) -> OCPResult:
    """
    Solve the OCP using IPOPT.

    Parameters
    ----------
    handle : OCPHandle
        Output of build_ocp.
    warm_start : OCPResult, optional
        Previous result whose primal trajectory will be reused as initial
        guess. The number of intervals N must match.
    verbose : bool
        If True, print IPOPT progress. Off by default for batch use.
    max_iter : int
        IPOPT iteration cap. 500 is generous for these problem sizes.
    tol : float
        IPOPT convergence tolerance (matches proposal Table 1 target of
        1e-4 for the local NLP).
    """
    opti = handle.opti

    # Apply warm-start if provided
    if warm_start is not None and len(warm_start.v_traj) == handle.N + 1:
        for k in range(handle.N + 1):
            opti.set_initial(handle.v[k], float(warm_start.v_traj[k]))
            opti.set_initial(handle.E[k], float(warm_start.E_traj[k]))
            opti.set_initial(handle.E_har[k], float(warm_start.E_har_traj[k]))
        for k in range(handle.N):
            opti.set_initial(handle.F_ice[k],   float(warm_start.F_ice_traj[k]))
            # handle.F_mguk_expr is a derived CasADi expression (F_dep -
            # F_reg), not a decision variable — opti.set_initial() on it
            # would fail. Warm-start the two non-negative controls it is
            # built from instead, using the RAW primal from the previous
            # solve (never the canonical reallocation).
            opti.set_initial(handle.F_dep[k],   float(warm_start.F_dep_traj[k]))
            opti.set_initial(handle.F_reg[k],   float(warm_start.F_reg_traj[k]))
            opti.set_initial(handle.F_brake[k], float(warm_start.F_brake_traj[k]))
            opti.set_initial(handle.a[k],       float(warm_start.a_traj[k]))

    # Configure IPOPT
    p_opts = {"expand": True}
    s_opts = {
        "max_iter": max_iter,
        "tol": tol,
        "print_level": 5 if verbose else 0,
        "sb": "yes",  # suppress banner
    }
    opti.solver("ipopt", p_opts, s_opts)

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------
    # Pure-IPOPT wall clock. Bracket only the solve call — build and
    # extraction are timed separately by the batch layer (total_time_s).
    t0 = time.perf_counter()
    try:
        sol = opti.solve()
        converged = True
        status = "solved"
    except RuntimeError as exc:
        # IPOPT signalled failure. Recover the actual termination reason
        # from opti.stats() — the bare exception class is uninformative.
        sol = None
        converged = False
        try:
            ipopt_status = opti.stats().get("return_status", "unknown")
        except Exception:  # noqa: BLE001
            ipopt_status = "stats_unavailable"
        status = f"failed: {ipopt_status}"
        # Surface the underlying exception text too if logging is on
        if verbose:
            print(f"  [solver] {ipopt_status}: {exc}")
    solve_time = time.perf_counter() - t0

    # Iteration count is available from opti.stats() in both success and
    # failure cases (the previous try/except branch lost it on failure).
    try:
        iterations = int(opti.stats().get("iter_count", -1))
    except Exception:  # noqa: BLE001
        iterations = -1

    # Extract trajectories (works for both solved and unsolved via debug)
    def _val(sym):
        return np.asarray(opti.debug.value(sym) if sol is None else sol.value(sym)).flatten()

    v_traj      = _val(handle.v)
    E_traj      = _val(handle.E)
    E_har_traj  = _val(handle.E_har)
    F_ice_traj  = _val(handle.F_ice)
    F_dep_traj  = _val(handle.F_dep)
    F_reg_traj  = _val(handle.F_reg)
    F_mguk_traj = F_dep_traj - F_reg_traj
    F_brake_traj = _val(handle.F_brake)
    a_traj      = _val(handle.a)

    s_grid = np.linspace(0.0, handle.L, handle.N + 1)
    s_mid  = 0.5 * (s_grid[:-1] + s_grid[1:])

    # ------------------------------------------------------------------
    # Extract Phase 3 labels
    # ------------------------------------------------------------------
    # Trajectory labels — raw controls (d_coast was always raw; unchanged)
    d_X = _extract_aero_switch(s_mid, a_traj)
    v_taper = _extract_velocity_taper(v_traj, F_mguk_traj)
    d_coast = _extract_coast_distance(s_mid, F_mguk_traj, handle.L)

    # Energy-accounting labels — v3.1: RAW is now primary for all four
    # (see module docstring, "v3.1 CHANGE", pass 1 and pass 2). Canonical
    # is still computed and kept as a parallel *_canonical diagnostic for
    # the transition period.
    E_deploy_raw, E_harvest_raw, P_deploy_mean_raw = _extract_deployment_aggregates(
        v_traj, F_mguk_traj, handle.L
    )
    F_canon, E_final_canon = _canonical_energy_reallocation(
        v_traj, F_mguk_traj, F_brake_traj,
        handle.inputs.E_initial, handle.L, handle.params,
    )
    E_deploy_canon, E_harvest_canon, P_deploy_mean_canon = _extract_deployment_aggregates(
        v_traj, F_canon, handle.L
    )
    E_realloc_delta = E_harvest_canon - E_harvest_raw
    # E_final: the OCP's own solved terminal state, raw by construction —
    # no recomputation, no reallocation. This is genuinely different from
    # E_final_canon above: real v3 efficiency-weighted dynamics vs that
    # function's own unity-efficiency forward walk on a different force
    # split. See module docstring, v3.1 pass 2.
    E_final_raw = float(E_traj[-1])

    # Sector time from trapezoidal cost evaluation
    h = handle.L / handle.N
    dt_optimal = float(np.sum(0.5 * h * (1.0 / v_traj[:-1] + 1.0 / v_traj[1:])))

    return OCPResult(
        converged=converged,
        iterations=iterations,
        solver_status=status,
        d_X_optimal=d_X,
        v_taper_optimal=v_taper,
        P_deploy_mean_optimal=P_deploy_mean_raw,
        E_deploy_optimal=E_deploy_raw,
        E_harvest_optimal=E_harvest_raw,
        P_deploy_mean_canonical=P_deploy_mean_canon,
        E_deploy_canonical=E_deploy_canon,
        E_harvest_canonical=E_harvest_canon,
        E_final=E_final_raw,
        E_final_canonical=E_final_canon,
        E_har_final=float(E_har_traj[-1]),
        d_coast_optimal=d_coast,
        dt_optimal=dt_optimal,
        s_grid=s_grid,
        v_traj=v_traj,
        E_traj=E_traj,
        E_har_traj=E_har_traj,
        F_ice_traj=F_ice_traj,
        F_dep_traj=F_dep_traj,
        F_reg_traj=F_reg_traj,
        F_mguk_traj=F_mguk_traj,
        F_brake_traj=F_brake_traj,
        a_traj=a_traj,
        solve_time_s=solve_time,
        E_realloc_delta_J=E_realloc_delta,
    )


# ----------------------------------------------------------------------
# Canonical energy reallocation
# ----------------------------------------------------------------------
def _canonical_energy_reallocation(
    v_traj: np.ndarray,
    F_mguk_traj: np.ndarray,
    F_brake_traj: np.ndarray,
    E_initial: float,
    L: float,
    params,
) -> Tuple[np.ndarray, float]:
    """
    RETIRED from the primary extraction path as of v3.1 (Aug 2026) — kept,
    not deleted, for audit-trail purposes (E_final still uses it; the
    *_canonical diagnostic columns still call it; historical labels
    remain reproducible). Do not route P_deploy_mean/E_deploy/E_harvest
    through this by default again without re-reading the v3.1 note in the
    module docstring: it was built for v2's unity-efficiency world, where
    reassigning retard force from friction brake to regen was a pure win
    (regen and brake were physically interchangeable at fixed motion). Under
    v3, regen carries a genuine eta_regen < 1 cost and the raw solve is
    already price- and efficiency-aware; this function is a greedy,
    forward-only, locally-headroom-capped heuristic with no such foresight,
    and it measurably UNDERSHOOTS the raw solve's own harvest in 99.15% of
    v3 solves (median −36 kJ per solve, DC-bus basis) — the opposite of what
    "regen-first" promises. That made it a defect relative to its own
    stated intent when used as the primary basis, not a legitimate
    modelling choice.

    Resolve the regen-vs-friction-brake split deterministically without
    touching the trajectory.

    Holds F_ice and the net non-ICE force net_k = F_mguk_k − F_brake_k
    fixed per interval (so F_long and v(s) are exactly preserved) and
    reassigns:
        net_k ≥ 0 : F'_k = net_k        (any simultaneous brake is
                                         cancelled against deploy —
                                         removes within-interval
                                         deploy+brake overlap)
        net_k < 0 : retard demand R = −net_k is met regen-first:
                    F'_k = −min(R,
                               p_regen_max / v_mid_k,      (power limit)
                               (capacity − E'_k) / h)      (cap headroom)
                    with the friction brake implicitly carrying the
                    remainder R + F'_k ≥ 0.
    The battery path E'(s) is walked forward under dE/ds = −F' (the
    exact discrete form of the trapezoidal E-dynamics with ZOH
    controls). Since F'_k ≤ F_mguk_k on deploy intervals and regen is
    only ever increased up to the cap, E'(s) ≥ E_raw(s) ≥ 0 pointwise
    and E'(s) ≤ capacity by construction.

    Returns (F_canonical, E_final_canonical).
    """
    n = len(F_mguk_traj)
    h = L / n
    v_mid = 0.5 * (v_traj[:-1] + v_traj[1:])
    F_canon = np.empty(n)
    E = float(E_initial)
    for k in range(n):
        net = float(F_mguk_traj[k]) - float(F_brake_traj[k])
        if net >= 0.0:
            Fk = net
        else:
            R = -net
            f_power = params.p_regen_max / max(float(v_mid[k]), 1e-6)
            f_headroom = max((params.e_batt_capacity - E) / h, 0.0)
            Fk = -min(R, f_power, f_headroom)
        F_canon[k] = Fk
        E = E - Fk * h
        # Numerical-dust guard only; the induction argument keeps E in
        # bounds wherever the raw solution was feasible.
        E = min(max(E, 0.0), params.e_batt_capacity)
    return F_canon, float(E)


# ----------------------------------------------------------------------
# Label extraction helpers
# ----------------------------------------------------------------------
def _extract_aero_switch(s_mid: np.ndarray, a_traj: np.ndarray) -> float:
    """
    Return the distance s at which the aero variable first crosses 0.5
    (Z-mode to X-mode transition). Returns NaN if the trajectory never
    crosses the threshold.
    """
    above = a_traj > 0.5
    if not np.any(above):
        return float("nan")
    first_idx = int(np.argmax(above))
    if first_idx == 0:
        return float(s_mid[0])
    # Linear interpolation across the crossing
    a_lo, a_hi = a_traj[first_idx - 1], a_traj[first_idx]
    if a_hi == a_lo:
        return float(s_mid[first_idx])
    frac = (0.5 - a_lo) / (a_hi - a_lo)
    s_lo, s_hi = s_mid[first_idx - 1], s_mid[first_idx]
    return float(s_lo + frac * (s_hi - s_lo))


def _extract_velocity_taper(
    v_traj: np.ndarray,
    F_mguk_traj: np.ndarray,
    min_intervals: int = 5,
    min_v_span: float = 5.0,
) -> float:
    """
    Fit a linear taper P_mguk = m·v + c over the deployment segment
    (intervals where P_mguk > 0) and return the slope m in W per m/s.

    Guards: returns NaN unless the deployment phase spans at least
    `min_intervals` intervals AND at least `min_v_span` m/s of velocity
    range. Below these thresholds the linear fit is ill-conditioned: the
    placeholder full batch produced pathological slopes (|slope| up to
    ~5e6 W·s/m) precisely on short/narrow-range deployment phases. Such
    scenarios are represented instead by P_deploy_mean_optimal.
    """
    v_mid = 0.5 * (v_traj[:-1] + v_traj[1:])
    P_mguk = F_mguk_traj * v_mid
    mask = P_mguk > 0
    if int(mask.sum()) < min_intervals:
        return float("nan")
    v_dep = v_mid[mask]
    if float(v_dep.max() - v_dep.min()) < min_v_span:
        return float("nan")
    slope, _ = np.polyfit(v_dep, P_mguk[mask], 1)
    return float(slope)


def _extract_deployment_aggregates(
    v_traj: np.ndarray, F_mguk_traj: np.ndarray, L: float
):
    """
    Deployment/harvest aggregates over the sector for a given MGU-K
    force series (raw or canonical — the caller picks which by which
    force series it passes in; see solve_ocp's v3.1 call site, which now
    calls this with the RAW series for the primary labels and again with
    the canonical F_canon for the *_canonical diagnostic siblings).

    WHEEL power, not DC-bus power: F_mguk_traj is a wheel-equivalent force
    (N) in both bases, so E_deploy and P_deploy_mean are wheel-equivalent
    quantities with NO efficiency applied, regardless of which series is
    passed in. The regulatory 350 kW cap (C5.2.7) is enforced elsewhere
    (problem.py) at the DC bus; the wheel-equivalent ceiling implied by
    that cap is 350,000 * eta_motor = 332,500 W, not 350,000 W. Compare
    P_deploy_mean against 332.5 kW, not 350 kW.

    Returns (E_deploy, E_harvest, P_deploy_mean):
        E_deploy      — ∫ F_mguk⁺ ds = Σ F_mguk·h over deploying intervals
                        (J, ≥ 0). In the spatial domain dE/ds = −F_mguk,
                        so this is exactly the battery energy spent driving
                        UNDER UNITY EFFICIENCY — a v2-era description this
                        module's dynamics no longer satisfy exactly (v3
                        applies eta_motor/eta_regen); still an accurate
                        WHEEL-mechanical-energy statement in both bases.
        E_harvest     — Σ |F_mguk|·h over regen intervals (J, ≥ 0).
                        Mechanical energy absorbed; battery gain equals
                        this only under unity efficiency (v2), not v3's
                        DC-bus state E_har_final (see dynamics.py).
        P_deploy_mean — E_deploy / t_deploy with t_deploy = Σ h/v_mid over
                        deploying intervals (W). NaN if no deployment.
                        This is the robust scalar replacement for the
                        slope-based taper label.
    """
    n = len(F_mguk_traj)
    h = L / n
    v_mid = 0.5 * (v_traj[:-1] + v_traj[1:])
    dep = F_mguk_traj > 0
    reg = F_mguk_traj < 0
    E_deploy = float(np.sum(F_mguk_traj[dep]) * h) if np.any(dep) else 0.0
    E_harvest = float(-np.sum(F_mguk_traj[reg]) * h) if np.any(reg) else 0.0
    if not np.any(dep):
        return E_deploy, E_harvest, float("nan")
    t_deploy = float(np.sum(h / v_mid[dep]))
    P_mean = E_deploy / t_deploy if t_deploy > 0 else float("nan")
    return E_deploy, E_harvest, P_mean


def _extract_coast_distance(
    s_mid: np.ndarray, F_mguk_traj: np.ndarray, L: float
) -> float:
    """
    Distance of the trailing contiguous regen segment (raw F_mguk < 0)
    ending at sector exit. Captures the lift-and-coast distance d_coast.

    Deliberately computed from the RAW control series — see the module
    docstring on label semantics.

    Returns 0.0 if no regen occurs at sector end.
    """
    if F_mguk_traj[-1] >= 0:
        return 0.0
    # Walk backwards while still negative
    idx = len(F_mguk_traj) - 1
    while idx >= 0 and F_mguk_traj[idx] < 0:
        idx -= 1
    coast_start_idx = idx + 1
    return float(L - s_mid[coast_start_idx])
