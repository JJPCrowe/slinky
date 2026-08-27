# Phase 4 — Direct Prediction of OCP Outputs (v4, raw-basis labels)

Training complete: `run_phase4_v4_training.py` ran ablation -> baselines ->
5-seed x 24-fold MLP-vs-XGBoost learner comparison across all 6 heads ->
production two-stage/gate architectures -> d_X boundary-pin breakdown,
05:15-18:43 (13.5h). Lap-level validation and inference timing below use
the models this run actually produced. See the CONSTRAINTS section at the
end for what has and has not been touched.

**Executive summary (six questions, one line each — full evidence below):**

1. All three original heads survive, with real, explained accuracy shifts
   (P_deploy RMSE more than doubles for legitimate reasons; d_X improves;
   d_coast's feature contract changed) — and the MLP-over-XGBoost claim is
   now confirmed at p<0.001 on every head with 5-seed evidence v3 never had.
2. No — d_X's headline accuracy is inflated by the 64.5% boundary-pinned
   population being trivially easy (RMSE 0.83m) vs the genuine interior
   population (RMSE 1.82m), the opposite failure mode from what was
   hypothesised but the same underlying concern.
3. Yes, every head beats both trivial baselines by wide margins (57-97%
   RMSE reduction), including the flagged near-degenerate P_deploy target.
4. Median lap-time error is small (-0.032s) but only 14.6% of laps fall
   within +/-0.05s (52.0% within +/-0.2s, 87.5% within +/-0.5s) — direct
   prediction meets the target's spirit, not its tight letter, and is still
   a large improvement over the abandoned reconstruction approach's +0.78s
   median.
5. The outer loop picks the same lambda as the OCP 86.1% of the time (when
   both sides have a feasible option); when it differs, the median cost is
   +0.029s but a real tail exists up to +2.18s.
6. 27x faster per single sample (25.2ms vs 685.6ms median), up to ~29,000x
   faster batched — both exclude fit/load time.

## Architecture change (context, not new work)

Phase 4 previously validated lap time by predicting three control scalars
(P_deploy_mean, d_X, d_coast), reconstructing a control trajectory, and
forward-simulating it. That reconstruction work is preserved as a scoped
negative result — `phase4/reconstruct.py`, `phase4/simulate.py` and their
outputs (`output/phase4_forward_simulator.md`,
`output/phase4_reconstruction_floor.md`) are unmodified and undeleted. This
report replaces reconstruction-based validation with DIRECT prediction of
the OCP's own outputs (dt_optimal, net depletion, E_har_final), which are
already columns in the production parquet and require no reconstruction
step at all.

## Method summary (see individual scripts for full detail)

- `phase4_data_v4.py` — dataset contract: v4 parquet, `ocp_converged==True`
  only (label_quality_exclusions_v4.csv already applied at production-batch
  generation time — verified 0/63 excluded keys present in the v4 file, so
  it is not re-applied here), `energy_price` added as a feature on every
  head, `net_depletion_J = E_initial - E_final` computed (raw/gross basis;
  `E_final_canonical` and the net-bucketed `E_deploy_optimal`/
  `E_harvest_optimal` columns are never used as this target or as
  `E_har_final`'s source).
- `phase4_train_v4.py` — `PDeployTwoStageGate` (new, mirrors
  `DCoastTwoStageRatio`'s two-stage structure but combines by hard gate,
  not expected-value blend — see its docstring for why), trivial-baseline
  helpers, multi-seed LOCO wrapper, d_X boundary-pin breakdown.
- `run_phase4_v4_training.py` — the checkpointed driver (ablation ->
  baselines -> learner comparison -> two-stage/gate architectures -> d_X
  pin breakdown), resumable per (stage, head, arm/seed/model).
- `run_phase4_lap_oof.py` / `run_phase4_lap_validate.py` — Step 3, built
  and unit-tested against synthetic data ahead of the real run (see
  CONSTRAINTS).
- `run_phase4_inference_timing.py` — Step 4.

**Compute-budget disclosure (stated once here, applies throughout):** a
timing probe found XGBoost fits the full ~763k-row LOCO training set in
~42s; sklearn's MLPRegressor at the exact v3 architecture (256,128,64) on
the same full data did not complete in a reasonable probe window and was
abandoned rather than timed. The MLP arm in every result below trains on a
**150,000-row uniform random subsample** of each fold's training set (not
the full ~763k) with a **(128, 64)** hidden-layer architecture and
`max_iter=150` (down from (256,128,64)/200), sized by direct probe
(150k rows at this architecture: 31.3s/fit) to make 5-seed x 24-fold x
6-head evaluation completable at all. XGBoost is unaffected — full data,
unchanged hyperparameters from phase3_train.py's `make_xgb_model` defaults.
This is a deviation from the exact v3 MLP configuration and is reported as
such wherever the MLP arm's numbers appear below.

---

## Stage 1 — Feature ablation (re-run on v4)

Same decision rule as `phase3_data.py` (prefer geometry-only unless "full"
wins significantly, p<0.05, AND on >=13/24 folds):

| target | wilcoxon p | full wins | decision | mean RMSE full | mean RMSE geo |
|---|---|---|---|---|---|
| P_deploy_mean_optimal | 0.375 | 15/24 | **geometry_only** | 23.72 kW | 23.86 kW |
| d_X_optimal | 0.065 | 15/24 | **geometry_only** | 1.164 m | 1.384 m |
| d_coast_optimal | 0.317 | 14/24 | **geometry_only** | 23.18 m | 23.51 m |

**This is a genuine change from v3.** v3's d_coast significantly preferred
the full 12-feature set (p=0.0016, full won 19/24 folds) — the execution-
profile features (v_max_kph, brake_frac, etc.) carried real signal there.
Under v4, that preference is no longer significant (p=0.317, full wins only
14/24) and d_coast now defaults to geometry-only like the other two heads.
Two candidate explanations, not distinguished further here: (1) `energy_price`
is now present in BOTH arms and may explain some of the variance the
execution-profile features used to carry (lambda and driving style both
correlate with how hard braking/coasting is), or (2) the corrected v3.1
deployment envelope and raw-basis extraction changed d_coast's own
structure (recall from `phase4_forward_simulator.md`: d_coast rarely
describes a genuine force-free glide, mostly a trailing braking-with-regen
window) enough to shift which features are informative. All three heads now
use the SAME 7-feature geometry-only contract (`FEATURES_GEOMETRY_ONLY` +
`energy_price`).

## Stage 2 — Trivial baselines

| target | mean-baseline RMSE | ceiling-baseline RMSE (P_deploy only) |
|---|---|---|
| P_deploy_mean_optimal | 51.03 +/- 12.80 kW | 69.43 +/- 18.33 kW |
| d_X_optimal | 11.57 +/- 2.54 m | — |
| d_coast_optimal | 136.17 +/- 47.98 m | — |
| dt_optimal | 2.806 +/- 0.905 s | — |
| net_depletion_J | 509.29 +/- 95.78 kJ | — |
| E_har_final | 306.70 +/- 37.16 kJ | — |

## Stage 3 — Learner comparison (MLP vs XGBoost, 5 seeds x 24 folds, geometry-only contract)

| target | XGBoost RMSE | MLP RMSE | XGB pooled R2 | MLP pooled R2 | paired (seed 0) | Wilcoxon p |
|---|---|---|---|---|---|---|
| P_deploy_mean_optimal | 24.06 +/- 8.53 kW | **22.02 +/- 8.85 kW** | 0.738 +/- 0.005 | 0.771 +/- 0.001 | MLP wins 18/24 | 3.7e-4 |
| d_X_optimal | 1.275 +/- 0.619 m | **0.638 +/- 0.487 m** | 0.986 +/- 0.001 | 0.996 +/- 0.0004 | MLP wins 23/24 | 2.4e-7 |
| d_coast_optimal | 25.34 +/- 13.83 m | **17.28 +/- 10.63 m** | 0.961 +/- 0.005 | 0.980 +/- 0.001 | MLP wins 23/24 | 2.4e-7 |
| dt_optimal | 0.272 +/- 0.121 s | **0.089 +/- 0.036 s** | 0.989 +/- 0.002 | 0.999 +/- 0.0001 | MLP wins 24/24 | 1.2e-7 |
| net_depletion_J | 69.17 +/- 13.95 kJ | **45.97 +/- 18.14 kJ** | 0.980 +/- 0.0002 | 0.990 +/- 0.0003 | MLP wins 24/24 | 1.2e-7 |
| E_har_final | 32.37 +/- 6.48 kJ | **24.97 +/- 8.18 kJ** | 0.988 +/- 0.0003 | 0.992 +/- 0.0003 | MLP wins 24/24 | 1.2e-7 |

RMSE and pooled-R2 columns are mean +/- SD across the 5 seeds (each seed
itself a full 24-fold LOCO sweep — RMSE column pools fold x seed, n=120;
pooled-R2 column is the per-seed pooled value, so its SD is genuinely
seed-to-seed variance, the thing this report was specifically asked to
establish). **MLP beats XGBoost on every single head, with p<0.001 in every
case** — the seed-to-seed SD on pooled R2 is small relative to the XGB-MLP
gap throughout (e.g. dt_optimal: MLP 0.999 +/- 0.0001 vs XGB 0.989 +/- 0.002
— the arms do not overlap even accounting for seed noise), so the
MLP-over-XGBoost claim survives 5-seed scrutiny with room to spare, not by
a coin-flip margin.

**Production two-stage / gate architectures** (XGBoost, single seed, matching
the v3 convention that these auxiliary structures are evaluated separately
from the learner comparison — see `run_learner_comparison`'s own docstring
in `phase3_train.py`):

| head | architecture | RMSE | R2 | gate |
|---|---|---|---|---|
| d_coast_optimal | DCoastTwoStageRatio | 21.21 +/- 12.80 m | pooled 0.972 | precision 0.986, recall 1.000, F1 0.993 |
| P_deploy_mean_optimal | PDeployTwoStageGate (new) | 25.03 +/- 9.66 kW | fold-mean 0.727 +/- 0.165 | accuracy 0.998, but non-deploy-class precision 0.379 / recall 0.177 / F1 0.225 |

**The P_deploy gate does not solve the "never deploys" problem well.**
99.8% accuracy is not informative here: the non-deploy class is 0.37% of
the data (2,944/796,919), so a trivial "always predict deploys" classifier
already scores 99.63%. The gate's OWN recall on the class it exists to
catch is only 17.7% — it misses roughly 5 in 6 genuine non-deploy
scenarios, defaulting them to a (wrong) hard-gated regressor prediction
instead of the physically-correct zero. This is disclosed rather than
smoothed over: the instruction to "not impute zero" was followed (the
architecture never defaults to zero without a gate decision), but the gate
itself is weak on its minority class and is a genuine weak point of this
head, not a solved problem. A probability-threshold tuned for recall over
accuracy, or the same expected-value blend d_coast uses instead of a hard
gate, are the natural next things to try and were not in scope to iterate
on further here.

## 1. Do the three original heads survive the move to raw v4 labels? What changed against v3?

**Yes, with a real and explained accuracy cost, not a modelling regression.**
Against the v3 figures cited in the task (P_deploy RMSE 10.05 kW, d_X RMSE
0.95 m):

- **P_deploy: 10.05 kW -> 22.02 kW, more than DOUBLED.** Three compounding,
  legitimate reasons, not a regression: (i) v3's canonical-basis label was a
  deterministic greedy reallocation, smoother and easier to predict than
  the true price- and efficiency-aware raw solve it approximated (raw
  measurably undershoots/diverges from canonical in the majority of solves,
  per `solver.py`'s own v3.1 documentation); (ii) v3 had no lambda sweep at
  all (a single calibrated tie-break), so the v3 task was implicitly
  single-price, while v4 sweeps `energy_price` across a ~30x range that the
  label is now genuinely, if weakly, sensitive to (§3 below); (iii) the
  corrected v3.1 deployment envelope changed which sectors are
  power-limited vs envelope-limited (27.9% of instances previously
  mis-capped). The raw v4 target is a harder, richer quantity to predict,
  not the same quantity predicted worse.
- **d_X: 0.95 m -> 0.638 m, IMPROVED.** d_X's physical driver (aero-switch
  placement, geometry-led per the reconstruction-floor findings) is stable
  across this change, and the 7x larger dataset (lambda sweep) likely helps
  more than it hurts here since d_X is only weakly lambda-sensitive.
- **d_coast: no directly comparable v3 RMSE figure was carried into this
  task's brief**, but the production two-stage architecture's pooled R2
  rose sharply (v3: 0.801; v4: 0.972) even though absolute RMSE rose too
  (v3: 16.43 m; v4: 21.21 m) — consistent with v4's label carrying
  substantially more total variance (the lambda sweep widens the range of
  coast behaviour) such that a larger absolute error still explains a
  larger share of a larger variance.
- **The MLP-over-XGBoost claim survives, and is now backed by seed-variance
  evidence v3 never reported**: MLP wins all three original heads with
  p<0.001, matching or exceeding the strength of v3's "24/24 and 22/24
  folds" framing (v4: 18/24, 23/24, 23/24 — plus a clean sweep on all three
  NEW heads too, 24/24 each).

## 2. Is d_X carried by the boundary-pinned subset?

**Not in the direction the question anticipated — the opposite pattern
holds, which is its own finding.** 64.46% of eligible rows are boundary-
pinned (matching the task's own 64.5% figure closely). RMSE on that subset
is **0.828 m**, LOWER than the interior subset's **1.820 m** (both XGBoost,
single seed, per-fold breakdown in `dx_pin_breakdown.csv`) — the model is
NOT failing on the pinned population and succeeding on interior; if
anything the reverse.

**Why this still matters, stated plainly per instruction:** the pinned
label is `L_straight_m / 50` by construction (a[0]==0 boundary condition
plus N=50 discretisation, not a physical optimum) — an almost-deterministic
function of a feature already in the model. Predicting it accurately is a
much easier task than predicting where a genuine optimal aero switch lands,
and 64.5% of the eligible population is this easy case. So while the model
is not "carried" in the failure-mode sense, the **headline pooled R2
(0.996, MLP) is still substantially inflated by the majority-pinned, easy
population** — the interior RMSE (1.82 m XGBoost single-seed; not separately
re-run for MLP within the time available, but the same population effect
applies) is the honest measure of the model's ability to predict a genuine
physical aero-switch decision, and it is meaningfully worse than the
headline number suggests. Both numbers should be reported together in the
methods chapter, not the pooled figure alone.

## 3. Does every head beat its trivial baseline?

**Yes, decisively, on every head, against both the mean-baseline and (for
P_deploy) the ceiling-baseline:**

| target | mean-baseline RMSE | ceiling-baseline RMSE | best model (MLP) RMSE | reduction vs best baseline |
|---|---|---|---|---|
| P_deploy_mean_optimal | 51.03 kW | 69.43 kW | 22.02 kW | 57% |
| d_X_optimal | 11.57 m | — | 0.638 m | 94% |
| d_coast_optimal | 136.17 m | — | 17.28 m | 87% |
| dt_optimal | 2.806 s | — | 0.089 s | 97% |
| net_depletion_J | 509.29 kJ | — | 45.97 kJ | 91% |
| E_har_final | 306.70 kJ | — | 24.97 kJ | 92% |

**P_deploy's flagged near-degeneracy is real but does not defeat the
model.** Measured directly: P_deploy sits at median 91.4% of the 332.5 kW
ceiling, IQR 16.25 percentage points (~54 kW), and its mean barely moves
with lambda — 86.5% of ceiling at the lowest grid value down to 83.6% at
the highest, only a ~3-point swing across a 30x price range. This is a
genuinely low-signal target. Despite that, XGBoost/MLP still cut RMSE by
53-57% against the better trivial baseline — evidence that real, learnable
structure exists beneath the compression (most likely per-corner friction-
circle interactions, per `problem.py`'s own documented mechanism), even
though the LAMBDA-response specifically is weak and this head should not
be oversold as strongly lambda-driven.

---

## Step 3 — Lap-level validation, directly

**Real laps, not synthetic draws.** Built from the actual (year, gp, driver)
sector sequence, sorted by `sector_id`: **932 distinct real laps**, mean
**12.25 sectors/lap** (median 12, range 7-21, std 3.06) — consistent with
the 12.27 figure used throughout this project's earlier synthetic-lap work,
now confirmed as the real empirical average rather than an assumed one.
91% of laps have gaps in their `sector_id` sequence (different drivers'
laps don't share an identical straight-segment inventory on the same
circuit) — sectors present for that specific driver are simply summed, gaps
are not an error condition.

**Model used for OOF predictions: MLP**, not XGBoost. An earlier version of
this pipeline defaulted to XGBoost for lap-level validation "for compute
convenience... the established v3 production choice" — that was wrong once
Stage 3 actually landed and showed MLP beating XGBoost on every head,
dt_optimal by 3x (RMSE 0.089s vs 0.272s). Validating the lap-time claim
against the weaker model would have understated Objective 4's real
achievable accuracy. Corrected before generating OOF predictions (the
XGBoost-based OOF run was killed after 3/72 folds and restarted with MLP,
same architecture/subsample as Stage 3, plus fold-level joblib parallelism
added since the original script had none).

**ASSUMPTION, stated once and applying to every number in this section:**
SoC does NOT carry across sectors — each sector's label (and prediction)
was solved/scored at an independent `initial_SoC` grid draw, not one
inherited from the previous sector's terminal energy. Each of the 10 SoC
grid values is evaluated as its own complete "lap instance" (same SoC
applied uniformly across every sector of that lap), giving 932 laps x 10
SoC x 7 lambda = **65,240 lap-instances**. This is NOT a simulation of
sequential energy carry-over, which remains separate future work.

**Lap-time error, signed (dt_pred_sum - dt_true_sum), n=65,240:**

| p5 | p25 | median | p75 | p95 | max\|·\| | mean |
|---|---|---|---|---|---|---|
| -0.703s | -0.228s | **-0.032s** | +0.153s | +0.427s | 4.38s | -0.066s |

| tolerance | fraction of laps within |
|---|---|
| +/-0.05s | **14.60%** |
| +/-0.2s | 52.05% |
| +/-0.5s | 87.54% |

**Lap depletion error** (signed, kJ): median **+7.93**, IQR [-76.7, +103.9],
mean -2.09 kJ — negligible relative to the 4,000 kJ (4 MJ) C5.2.9 limit.
**Lap harvest error** (signed, kJ): median **-7.21**, IQR [-55.9, +41.6],
mean -2.43 kJ — negligible relative to the 8,500 kJ (8.5 MJ) C5.2.10 cap.

**Feasibility confusion matrix** (depletion<=4MJ AND harvest<=8.5MJ, both
sides independently):

| | predicted feasible=False | predicted feasible=True |
|---|---|---|
| **OCP-label feasible=False** | 45,036 | **447** |
| **OCP-label feasible=True** | 676 | 19,081 |

**Dangerous error (predicted feasible, actually infeasible): 447/65,240 =
0.685%.** Conservative error (predicted infeasible, actually feasible):
676/65,240 = 1.036%. Neither is zero — a deployed outer loop using these
predictions would, roughly 1 time in 146, wave through a lap/SoC/lambda
combination that actually breaches C5.2.9 or C5.2.10 — a real, disclosed
residual risk, not eliminated by this architecture change, though small in
absolute terms. Note also that 70% of all lap-instances (45,712/65,240) are
OCP-infeasible in the first place: at unconstrained random SoC/lambda draws
without sequential carry-over, most combinations do not satisfy the energy
budget for a full ~12-sector lap — expected given the no-carry-over
assumption above, and a further reason sequential SoC propagation is the
natural next piece of work.

## 4. Lap-time error, and what fraction of laps are within +/-0.05s?

**Median signed error is small (-0.032s) but the +/-0.05s band is tight
relative to it: only 14.60% of laps land inside it.** 52.0% are within
+/-0.2s and 87.5% within +/-0.5s. This is a dramatically better CENTRAL
result than the abandoned reconstruction approach ever achieved (whose
best measured configuration had a lap-level median signed error of +0.78s,
over 20x larger) — direct prediction of dt_optimal is a substantially
better-conditioned problem than reconstructing a control trajectory and
re-integrating it. But the tight +/-0.05s target is still missed by the
large majority of individual laps: summing ~12 independent per-sector
errors (each with its own sign and roughly 0.09s RMSE from Stage 3) widens
the lap-level spread even when the underlying per-sector model is
excellent, and the +/-0.05s band is comparable in width to a SINGLE
sector's typical error, let alone twelve summed. The honest statement for
the methods chapter: direct prediction meets the target's spirit (tiny
typical bias) but not its letter (a tight per-lap tolerance) at the current
per-sector accuracy level.

## 5. Does the outer loop select the same lambda as the OCP, and at what cost when it does not?

Exhaustive search over the 7 lambda values, per (real lap, SoC) combination
(n=9,320 = 932 laps x 10 SoC), selecting minimum-time lambda subject to
both energy constraints on each side independently:

- OCP-label side has NO feasible lambda at all 7 grid points: 21.42% of
  combinations (1,996/9,320).
- Prediction side has no feasible lambda: 22.63% (2,109/9,320) — close to
  the OCP-side rate, a consistency check that passes.
- **Of the 7,025 combinations where BOTH sides have >=1 feasible lambda:
  the same lambda is selected 86.14% of the time (6,051/7,025).**
- **When they differ (974 cases, 13.86%)**, the lap-time penalty (true dt
  at the predicted lambda minus true dt at the OCP-optimal lambda) has
  median **+0.029s**, mean +0.132s, IQR effectively [+0.010s, +0.200s], and
  a max of +2.18s. The penalty is asymmetric toward small values (median
  far below mean), so most disagreements cost very little, but a real,
  non-negligible tail exists (values above 1s occur, though rare) where
  picking the wrong lambda meaningfully costs lap time.

## Step 4 — Inference timing vs IPOPT

**System**: Windows 11, AMD64 (AMD Zen-family, "Family 23 Model 104"), 8
physical / 16 logical cores, 7.9 GB RAM, Python 3.14.0. Model FITTING and
LOAD time are excluded from every number below.

**Threading, corrected mid-run and disclosed exactly as found**: the
script originally pinned OMP/OPENBLAS/MKL/NUMEXPR threads to 1 at import
time, which also crippled the one-time representative-model fitting step
(8 XGBoost fits on the full ~763k-row training set) onto a single core —
caught when that step, normally ~4 minutes multi-threaded, was still
running after 10 minutes having accumulated under a minute of CPU time.
Fixed by moving the pinning to apply ONLY immediately before the IPOPT
timing loop. Consequence: **the IPOPT figures below are genuinely
single-threaded** (as the production batch itself was); **the surrogate's
single-sample and batched figures use XGBoost's/sklearn's natural
multi-threaded defaults** — i.e. what a real deployment on this machine
would actually get, not an artificially handicapped or artificially
favoured number. The `inference_timing.json` file's `system.
thread_env_pinned_to_1: true` field is a leftover from the pre-fix script
and should be read as "true only for the IPOPT loop", not globally.

| measurement | median | p95 | mean | n |
|---|---|---|---|---|
| **Single-sample, full surrogate** (8 fitted objects: P_deploy gate, d_X, d_coast two-stage, dt, net_depletion, E_har) | **25.2 ms** | 33.4 ms | 26.6 ms | 1,200 |
| IPOPT cold-start (tol=1e-4, N=50, max_iter=500, single-threaded) | **685.6 ms** | 912.6 ms | 805.1 ms | 20 |

**Median speedup: 27.2x** for a single, unbatched sample — dominated by
Python/pandas call overhead (8 separate small-DataFrame constructions and
predict calls), not by the models themselves:

| batch size | per-sample amortised |
|---|---|
| 100 | 358.6 us |
| 1,000 | 47.9 us |
| 5,000 | **23.6 us** |

At batch=5,000 the per-sample cost falls to 23.6 microseconds — roughly
**29,000x faster than one IPOPT cold-start** per sample, if predictions can
be requested in batches (e.g. evaluating a lambda grid or an outer-loop
search rather than one scenario at a time). The realistic deployment
number depends entirely on the calling pattern: single-scenario, on-demand
inference gets ~27x; any batched/vectorised use of the surrogate (which an
outer loop sweeping 7 lambda values per sector naturally is) gets several
orders of magnitude more.

## 6. Inference time vs IPOPT

**27x faster per single sample (25.2ms vs 685.6ms median), up to ~29,000x
faster when batched (23.6us/sample at batch=5,000 vs 685.6ms).** Both
figures exclude model fit/load time, as instructed. The IPOPT comparator
runs the exact unmodified `problem.py`/`solver.py` path at the production
batch's own tolerance and node count, single-threaded on the same machine
as every other number in this report.

---

## CONSTRAINTS observed

- `problem.py`, `dynamics.py`, `solver.py`, `vehicle.py`: imported and
  called unmodified (Step 4's IPOPT comparator uses them exactly as-is);
  no edits.
- `phase4/reconstruct.py` and its outputs: untouched, not deleted.
- No re-solving: everything in this report is computed from the stored
  v4 parquet's existing labels and predictions derived from them.
- No head failed its trivial baseline, so the "report it plainly, don't
  adjust the baseline" instruction was not tested by a failure — but the
  baselines were computed exactly as specified (train-mean; 332.5kW
  ceiling for P_deploy) and are reported in full above, not selectively.
- Every bug found and fixed during this run is disclosed at the point it
  is relevant, not silently corrected: the MLP fold-level parallelism
  omission (Stage 3, caught before any Stage-3 output existed and
  restarted), the OOF/lap-validation model choice defaulting to XGBoost
  instead of the measured-better MLP (caught after only 3/72 OOF folds and
  restarted), and the global thread-pinning that crippled representative-
  model fitting in Step 4 (caught after 10 minutes of near-zero CPU
  progress and fixed to scope the pinning to only the IPOPT loop).
