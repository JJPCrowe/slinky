# Phase 4 — Forward Simulator and Control Reconstruction

Scope: build `reconstruct_controls()` and `simulate_sector()` (`phase4/reconstruct.py`,
`phase4/simulate.py`), and measure the accuracy floor that reconstructing a full
control trajectory from three surrogate scalars (P_deploy_mean, d_X, d_coast)
imposes on Phase 4 lap assembly. `problem.py`, `dynamics.py`, `solver.py` and
`vehicle.py` were not modified; trajectory retention for Step 0 needed no
change to the OCP files because `solve_ocp()`'s `OCPResult` already carries
the full primal trajectory (`v_traj`, `E_traj`, `E_har_traj`, `F_*_traj`,
`a_traj`) — a new driver script simply persists what the solver already
returns instead of discarding it after scalar extraction, the way
`batch.py` / `run_production_v4.py` do.

**Headline answer, upfront:** three scalars are not sufficient at the stated
target. Reconstruction alone costs a **median 0.049 s per sector**, which
compounds to **≈0.60 s over a 12.27-sector lap** even under the (favourable)
assumption that per-sector errors add linearly — twelve times the +0.05 s
lap budget. See §4–5.

---

## Method and sample

A stratified sample of 2,000 scenarios (of 799,939 converged production
rows) was drawn across circuit (24), λ (7 values), zone_eligible (True/False)
and sector-length tertile — proportional allocation per non-empty cell
(714 of 1,008 possible cells populated), seed 20260826. Each was re-solved
cold (no warm start, N=50, otherwise identical to production) with full
trajectory retention: **2,000/2,000 converged**.

**Disclosed limitation of the re-solve itself:** comparing the cold re-solve's
own `dt`/`E_final` against the ORIGINAL warm-started production solve for the
same scenario, the two agree to a median 36 μs / 576 J, but **2.75% of
scenarios (55/2,000) differ by >10 kJ**, up to 941 kJ in the worst case —
genuinely different local optima, not a numerical tolerance issue. This
concentrates almost entirely in `zone_eligible=False` (aero-pinned) solves
(52/55), consistent with the regen-vs-friction-brake degeneracy already
documented in `solver.py`'s historical rationale for `_canonical_energy_reallocation`.
**Consequence for this report:** Step 3a (simulator fidelity) compares
against the re-solve's OWN reported scalars (same trajectory, no ambiguity);
Step 3b (reconstruction loss) compares against the STORED PRODUCTION labels
(the actual surrogate targets), never the re-solve's — mixing the two would
attribute local-optimum multiplicity to reconstruction error.

---

## 1. What is the true control structure, and are three scalars sufficient?

### Q1 — Phase structure: accelerate → coast → brake?

Classifying each interval as ACCEL (F_dep > 10 N), BRAKE (F_brake > 10 N,
checked first) or COAST (neither) and requiring the phase-code sequence to
be non-decreasing along the sector:

- **79.0% (1,580/2,000)** of solves fit a clean, single-transition
  ACCEL→COAST→BRAKE ordering.
- **21.0% (420/2,000)** show exactly one localised reversal (419/420 have
  *exactly one*, never more) — this is not oscillatory noise, it is a
  single structural anomaly per case. **46% (193/420)** of these sit within
  the first 3 intervals (a boundary-settling artefact right after the
  v(0)=v_exit condition); **0%** occur in the last 4 intervals (the tail
  brake block is always clean); the remaining **54% (227/420)** are a
  genuine one-off mid-sector reordering. Messy solves skew toward low λ
  (207/420 at the three lowest grid points) and toward `zone_eligible=False`
  (322/420 True, but disproportionately represented given eligible sectors
  are 68.6% of the sample).

**Bigger structural finding, not anticipated by the "accelerate, coast,
brake" framing:** whether v_entry_target exceeds v_exit or not is
**not** informative about whether braking occurs. **52.4% of the sample is
"net accelerating"** (v_entry_target ≥ v_exit), and a materially-sized
fraction of these still brake hard in the last few intervals — the
time-minimising solve routinely accelerates *past* both boundary speeds to
spend more of the sector at high speed, then sheds the excess in a short,
hard braking burst right before the exit boundary. A concrete example from
the pool: v_exit = 74.7 m/s, v_entry_target = 78.4 m/s, yet the solve peaks
at **87.5 m/s** (interval 45/50) before braking down to exactly 78.4 m/s in
the last four intervals. None of the three surrogate scalars expose this
peak or its location — see §5.

### What d_coast actually measures (important correction to the framing)

Despite the name, **d_coast_optimal is usually not a force-free glide.**
Within the segment it labels (the trailing run of negative net F_mguk),
a **median 100% (mean 83.5%)** of intervals have the **friction brake
actively engaged**, and only a **mean 3.6% (median 0%)** are genuinely
force-free. Correlation between `d_coast_optimal` and "distance from the
end of the ACCEL block to sector end" is only 0.29–0.49 depending on how the
latter is defined — d_coast is best read as *"where sustained deployment
stops,"* not *"how far the car coasts before braking."* This directly
explains the earlier Q3 finding (below): almost all harvest happens
"during braking," because "during braking" and "inside the labelled
d_coast window" are nearly the same interval for most solves.

### Q2 — Is F_dep constant or tapering within ACCEL?

Real, moderate tapering: second-half/first-half mean F_dep ratio has
**median 0.76** (IQR 0.31–0.88; i.e., a wide spread including some solves
that taper hard). `v_taper_optimal` (96.5% non-NaN in the sample) correlates
with this ratio at **r = 0.50** — a real but partial signal, not a
sufficient statistic for the taper shape. A constant-power reconstruction
(§2) reproduces P_deploy_mean exactly by construction but misses this
taper entirely; the resulting error is part of what §4 quantifies. **v_taper
was deliberately NOT used as a fourth reconstruction input** (only assessed):
using it would mean fitting the reconstruction to a scalar defined via a
guarded linear fit with its own failure modes (3.5% NaN, historically
pathological slopes on short/narrow-range phases), and the task's own
instruction against tuning the reconstruction to make the round-trip look
good extends naturally to not quietly upgrading from 3 inputs to 4 inside
the "3-scalar" analysis.

### Q3 — Regen split: COAST vs BRAKE phase

**Essentially all harvest happens during braking.** Fraction of a solve's
total harvest occurring in the COAST phase: **median 0%**, mean 2.4%; in
BRAKE: **median 99%**, mean 92%. This is a direct consequence of the
d_coast finding above, not an independent result. The split correlates with
geometric coast-fraction at r=0.62 and essentially not at all with the
speed differential dv_kph (r=0.005) — it is a length/geometry effect, not a
"how much do you need to slow down" effect.

### Q4 — F_reg vs F_brake split during BRAKE: is regen at cap?

**42.7%** of BRAKE-phase intervals run regen at ≥97% of the 350 kW cap; the
friction brake is engaged (by construction, since BRAKE was defined by
F_brake>10N) throughout. This supports **"regen-first up to its
instantaneous power-limited cap, friction brake for the remainder up to the
friction-circle limit"** as the operative policy far more often than a
smoothly modulated partial brake — exactly the greedy mechanism
`_canonical_energy_reallocation` already implements (retired from label
extraction in v3.1, but its *policy*, not its use as a label basis, is a
reasonable non-fitted assumption for *reconstruction*, which is a different
use case: synthesising a plausible profile from scratch, not overriding an
already-optimal raw solve).

### Q5 — Is F_ice at max throughout ACCEL, or modulated?

**Essentially always at cap**: 100% of ACCEL intervals sit within 3% of
p_ice_max/v_mid (mean P_ice/400kW = 0.9992). Not modulated in any
economically meaningful way — this is the one control with no real
reconstruction ambiguity.

### Q6 — Aero switch (d_X) vs phase boundaries

Restricted to `zone_eligible=True` scenarios with a real switch (1,372/1,372
after filtering NaN): d_X always precedes or coincides with the end of the
ACCEL block (median offset −199 m, IQR [−387, −109] m, **max +41 m** — i.e.
essentially never occurs after acceleration ends). d_X sits close to the
sector start relative to its own length (median d_X/L = 0.021 — i.e. the
switch to X-mode happens early, within the first few percent of the
sector, for the median case, though the distribution has a long tail up to
0.34).

### Answering "are three scalars sufficient?"

No, on two independent grounds found in Step 0 alone, before reconstruction
error is even measured: (1) P_deploy_mean cannot express the measured taper
(median ratio 0.76, only 50% correlation with the best available proxy);
(2) none of the three scalars expose whether — or by how much — the solve
accelerates past the boundary speeds before braking down, which Step 3
shows to be the dominant error source (§4–5).

---

## 2. Simulator fidelity (Step 3a)

`simulate_sector()` (`phase4/simulate.py`) forward-integrates
`dynamics.py`'s functions unmodified, using the **same discretisation as
`problem.py`** (implicit trapezoidal collocation, ZOH controls per
interval) — required so that feeding the OCP's own trajectory through the
simulator isolates integration-scheme error from physics error, rather than
comparing two different numerical schemes and calling the gap "physics
disagreement."

**A real bug was caught and fixed during this validation, disclosed here:**
the per-interval implicit step solves a scalar nonlinear equation for
v[k+1]; under heavy braking the residual is non-monotonic (a 1/v
singularity as v→0 creates a spurious second root at very low speed), so a
naive two-point bracket check reports "no solution" even though the correct
root exists nearby. Confirmed directly on a pool example (residual +10.9 at
v=1.0, −35.4 at v=2.0, crossing back through the true root at v=83.3, never
crossing again below that) — a same-sign check on a wide fixed bracket
misses it entirely. Fixed by scanning outward from v[k] in both directions
and taking the nearest sign-change bracket, which is always the physically
continuous root since velocity cannot jump between adjacent knots. This
bug, before the fix, was producing spurious ~100 kJ-scale "fidelity" errors
in 3a that had nothing to do with reconstruction or simulator design — worth
naming explicitly since it would have silently inflated every downstream
number in this report.

**With the fix, feeding the 2,000 TRUE re-solved trajectories directly into
the simulator (bypassing reconstruction) and comparing against the
re-solve's own reported scalars:**

| quantity | median abs diff | p95 | max |
|---|---|---|---|
| dt | 4.3×10⁻⁸ s | 1.4×10⁻⁶ s | 0.53 s |
| dSoC_net (J) | 3.4×10⁻¹⁰ | 1.5×10⁻⁹ | 375,903 |
| E_final_gross (J) | 4.7×10⁻¹⁰ | 1.9×10⁻⁹ | 357,102 |
| E_har_final (J) | 1.2×10⁻¹⁰ | 8.6×10⁻⁹ | 357,156 |

Median and p95 are at machine precision — the simulator agrees with the
OCP's own arithmetic essentially exactly, as it must. The four outlier rows
behind every "max" column are the **same four scenarios** (0.2% of the
sample) where the fixed-point root search still fails (`integration_collapsed`)
— a residual, disclosed limitation, not a design flaw affecting the
aggregate result.

**Constraint flags on the TRUE trajectories** (91.7% flag-free): the 8.3%
that flag something decompose cleanly, not mysteriously:

- **Deploy-envelope, 86/2,000, median 1.9 kW over, max 2.4 kW over** — this
  is `problem.py`'s own documented smoothing permissiveness (its smooth
  clamp on the C5.2.8(ii) taper is "permissive by at most delta/2" = 2.5 kW
  by default); the simulator checks against `regs_2026.p_deploy_max`'s
  *exact* curve, so this gap is expected and bounded exactly where the
  OCP's own module docstring says it would be.
- **SoC-window on the NET basis, 81/2,000, median 42 kJ, max 104 kJ** — and
  **zero** on the GROSS basis. This is the direct, expected consequence of
  the accounting split (§3): the OCP only ever constrains its own real
  (GROSS) state to [0, capacity]; the NET/unity-efficiency bookkeeping is a
  different accounting convention with no corresponding hard constraint in
  the OCP, so it straying outside that window on an OCP-feasible trajectory
  is unsurprising, not a defect.
- Absolute 350 kW cap and the friction circle: **zero** violations on true
  trajectories, as expected.

`net_gross_residual_J` (this simulator's own analogue of `identity_residual_J`)
has median −60,767 J on this stratified, cold-resolved sample — larger in
magnitude than production's own reported median (−1,411 J) because this
sample is drawn to include high-λ, aero-shut, and cold-solve conditions
disproportionately relative to the full production population, not because
the accounting itself differs; same sign, same underlying mechanism
(F_dep/F_reg simultaneity).

---

## 3. Energy accounting convention (as instructed)

The production labels (`E_deploy_optimal`, `E_harvest_optimal`, and by
extension `P_deploy_mean_optimal`, the surrogate's primary training target)
bucket the **NET** force F_mguk = F_dep − F_reg into single-sided
deploy/harvest under **unity efficiency**. The OCP's own E[N] state (the
RAW `E_final` label as of v3.1) integrates F_dep and F_reg **separately**,
each through its own efficiency (**GROSS**). These differ whenever F_dep and
F_reg are simultaneously positive — the documented identity residual.

`simulate_sector()` therefore tracks **both** explicitly and treats NET as
primary, per instruction:

- `E_net_traj` / `dSoC_net_J` / `E_final_net`: dE/ds = −(F_dep − F_reg),
  unity efficiency — directly comparable to `E_deploy_optimal − E_harvest_optimal`.
- `E_gross_traj` / `dSoC_gross_J` / `E_final_gross`: `dynamics.dE_ds`, real
  v3 efficiencies — directly comparable to the raw `E_final` label.
- `net_gross_residual_J = E_final_gross − E_final_net` is reported per
  `SimResult`, not discarded.

Reconstructed controls carry a distinguishable (F_dep, F_reg) split, but
that split is reconstruction's own modelling choice (regen-first-to-cap
during braking), not a recovered fact — the surrogate only ever predicts
the NET scalar. Integrating that assumed split through the GROSS dynamics
would silently compound reconstruction error with the simultaneity penalty;
tracking both explicitly keeps the two error sources visible separately.

---

## 4. Reconstruction loss (Step 3b) — the number that matters

`reconstruct_controls()` (full algorithm and every stated assumption in its
module docstring) takes the **stored production scalars** as input — the
actual surrogate targets — and is validated against that **same** solve's
own dt_optimal / (E_initial − E_final) / E_har_final:

**dt error, seconds per sector:**

| | value |
|---|---|
| median | **0.0492 s** |
| mean | 0.188 s |
| p95 | 0.6755 s |
| p99 | 2.620 s |
| max | 15.25 s |

**Scaled to a 12.27-sector lap:**

| assumption | median | p95 |
|---|---|---|
| linear sum (errors fully correlated across sectors — same method, same bias direction, the more defensible assumption here since every sector uses the identical reconstruction policy) | **0.603 s** | **8.29 s** |
| √n scaling (errors fully independent — optimistic) | 0.172 s | 2.37 s |

Both exceed +0.05 s by a wide margin even under the optimistic independence
assumption; nothing in this reconstruction method gets within reach of the
lap target on its own.

**Breakdown (median dt error, seconds):**

| split | value |
|---|---|
| by λ | 0.031–0.065 (no strong trend; 3×10⁻⁷ lowest at 0.031, 5.5×10⁻⁸ highest at 0.065) |
| zone_eligible=False (shut) | **0.008** |
| zone_eligible=True (aero free) | **0.084** |
| length: short | 0.015 |
| length: mid | 0.038 |
| length: long | **0.150** |
| d_X not boundary-pinned | 0.034 |
| d_X boundary-pinned (≤1.5×L/50) | **0.065** |
| net-accelerating sector | 0.035 |
| net-decelerating sector | 0.063 |

Aero-free (`zone_eligible=True`) sectors are **10× worse** than aero-pinned
ones — consistent with §1: aero-pinned sectors remove a whole axis of
reconstruction guesswork (a≡0, no switch to place), so essentially all of
their small residual error is the deploy-taper/overshoot-timing effect;
eligible sectors add the d_X placement and its interaction with the
friction circle on top. Long sectors are 10× worse than short ones, as
expected — more distance for the unmodelled taper and the unmodelled
peak-then-brake dynamic to compound. d_X-boundary-pinned sectors (64.5% of
eligible sectors, per the production run's own characterisation) are
**worse**, not better, than genuinely-optimised d_X — the discretisation
artefact evidently correlates with harder-to-reconstruct dynamics, not
easier ones (p95 dt error 0.987 s pinned vs 0.474 s non-pinned).

**Feasibility:** the shooting method itself finds a solution (accel/coast/
brake curves join) in **94.1%** of cases; the remaining 5.9% are genuine,
reported `max_deceleration_insufficient` infeasibilities (even full-power
braking over the whole d_coast-implied window cannot reach v_entry_target —
not forced, not papered over). Separately, re-simulating the reconstructed
profile and checking constraints (§2's flags) shows only **5.95%** come back
fully flag-free — dominated by the regen cap (83.8% of scenarios exceed it
by a median 13.4 kW, up to 608 kW), the friction circle (36.1%, median
6.7 kN over), and the deploy envelope (19.1%, median 194 kW over — much
larger than the OCP's own 1.9 kW smoothing gap in §2, confirming this is a
reconstruction-policy issue, not a repeat of the same benign artefact).
This is exactly what "enforce and flag, do not clip" is for: the
regen-first-to-cap policy, iterated only via a 4-step fixed point during
reconstruction's own backward shooting, is not fully self-consistent once
the profile is re-integrated forward by the simulator with its own v(s) —
a genuine limitation of the current policy, reported rather than hidden,
and a natural next refinement (iterate reconstruction and simulation to a
joint fixed point) that was out of scope to chase further here given it
does not change the headline dt-error conclusion (dt error is computed from
`res.dt` regardless of whether flags fired; the flags are an independent,
additional diagnostic about internal consistency, not a filter applied to
the headline numbers above).

---

## 5. Does reconstruction alone exceed the +0.05 s target? — Yes, decisively

At the median, a single sector already costs **0.049 s**, essentially the
entire lap budget from one sector; over a lap the cost is **0.60 s**
(linear) to **0.17 s** (optimistic independent-error scaling) — 3.4× to 12×
over budget even in the best case considered. **The target as stated is
unreachable by this reconstruction method, regardless of surrogate
quality**, confirming the task's own framing: reconstruction loss is a hard
floor that no improvement in P_deploy_mean/d_X/d_coast's *prediction
accuracy* can fix, because the floor is about what those three numbers can
*represent*, not how well they are predicted.

**What a fourth label would most reduce it:** the single biggest,
independently-diagnosed gap is that none of the three scalars expose
whether, or by how much, the true solve accelerates *past* the boundary
speeds before braking down (§1, Q1) — this is invisible to
P_deploy_mean/d_X/d_coast by construction, since none of them describe a
velocity level. **Recommended addition: `v_peak` (or `d_peak`, its
location)** — the maximum velocity reached in the sector. It is already
computable from the existing OCP trajectory (`np.max(v_traj)`) with no
solver-side change, would let reconstruction's shooting method target the
correct entry speed for the backward brake integration directly instead of
inferring it from a constant-power forward run, and would plausibly recover
most of the "long sector" and "d_X-pinned" error categories above, since
both are dominated by exactly this timing mismatch compounding over
distance. A secondary, smaller-value addition would be a taper-shape
descriptor better-conditioned than `v_taper_optimal` (e.g. F_dep at the
midpoint of the accel phase as a second point, avoiding the linear-fit
guard's fragility) to address the residual §1 Q2 gap once the peak-speed
issue is fixed.

---

## Step 4 — Interface for lap assembly (documented, not built)

**Per-sector inputs the simulator/reconstruction pair needs**, all already
available at either the surrogate-prediction stage or from `SectorInputs`:
`sector: SectorInputs` (v_exit, v_entry_target, L_straight — v_exit for
sector *k* is sector *k−1*'s achieved `v_exit_sim`, chained), `soc0` (the
carried SoC fraction — see below), and the three (or four, per §5) predicted
scalars.

**Per-sector outputs consumed by the next sector / by lap aggregation**
(`SimResult`, `phase4/simulate.py`):
- `v_exit` → becomes the next sector's `sector.v_exit` (velocity carries
  forward as an achieved value, not the target — `dv_terminal_ms` reports
  the gap between the two, which the outer loop / projection layer needs to
  reconcile against the next sector's OWN v_exit feature, since the Phase 1
  feature matrix's v_exit/v_entry_target are geometry-derived, not solve
  outputs).
- `E_final_net` (primary) and `E_final_gross` (diagnostic) → the SoC
  carried into the next sector's `soc0 = E_final_net / e_batt_capacity`, per
  §3's instruction that NET is the basis matching what the surrogate was
  trained against. **Both should be tracked across the lap**, not just the
  primary one, so that lap assembly can report the accounting gap the same
  way this document does, rather than letting it silently drift over
  12+ sectors.
- `E_har_final` → **cumulative Recharge carries additively across the
  whole lap** (`E_har_lap += E_har_final` per sector) — this is the
  quantity C5.2.10 actually caps (8.5 MJ, reducible per B7.2.1d), and it is
  the one state in this module with no NET/GROSS ambiguity at all.
- `feasible` and `flags` → surfaced per sector, not silently dropped;
  lap assembly needs to know which sectors' reconstructed profiles were
  internally inconsistent (§4) so that a lap-level infeasibility can be
  traced back to its source sector rather than discovered only as a failed
  E_har/SoC-window check at the lap level.
- `dt` → summed directly for lap time.

**Not built here, per instruction:** the outer loop that bisects λ/μ to hit
a lap-level energy target, and the projection layer that reconciles
sector-to-sector v_exit/v_entry_target mismatches, both consume this
interface but are explicitly out of scope for this task.

---

## Files

- `phase4/reconstruct.py` — `reconstruct_controls()`, full algorithm and
  assumptions in its module docstring.
- `phase4/simulate.py` — `simulate_sector()`, `ControlTrajectory`,
  `SimResult`; energy-accounting convention in its module docstring.
- `output/phase4_step0_sample.parquet` — the 2,000-scenario stratified
  sample (production scalar labels + stratification keys).
- `output/phase4_step0_resolve_meta.parquet`,
  `phase4_step0_traj_{knots,intervals}.parquet` — the re-solve's scalars
  and full trajectories.
- `output/phase4_step0_results.json`, `phase4_step3a_results.parquet`,
  `phase4_step3b_results.parquet` — numeric results behind every figure in
  this report.
- `output/phase4_figs/step0_control_structure.png` — velocity/force
  examples, taper-ratio histogram, harvest-split histogram, regen-saturation
  histogram, aero-switch-vs-phase-boundary scatter.
- `output/phase4_figs/step3_reconstruction_loss.png` — dt-error
  distribution and its breakdown by zone_eligible and sector length.
