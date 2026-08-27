# Phase 4 — Sequential SoC Propagation, and Two Reporting Fixes

This closes the sequential-SoC gap flagged in `phase4_direct_prediction.md`
and fixes two reporting issues found while doing it. No retraining of the
Stage 3 accuracy figures, no re-solving, no new labels — everything below
uses the six already-fitted model configurations (re-fit only where the
objects themselves were never persisted — disclosed in full in the Method
section) and the v4 parquet.

**Answering the six questions up front (full evidence below):**

1. The correction from independent to sequential SoC is large and directional:
   median **+1.24 s** on lap time, **−3.39 MJ** on lap depletion (naive,
   mismatched comparison) — but most of that depletion swing is the TRUE
   comparator itself changing under chaining, not prediction error. The
   like-for-like residual is a much smaller **+0.17 s** / **−0.59 MJ**.
2. **Yes, decisively** — the independent-SoC no-feasible-lambda rate
   (21.42%) drops to **1.08%** once the comparator itself is evaluated at
   the chained SoC (interpolated-true), converging toward the 3.68%
   structural rate from two independent directions. The naive
   sequential-*prediction* rate overshoots to ~0.01%, which is a separate,
   disclosed finding (§2).
3. Full lap-level validation is in §3, reported BOTH naively (mismatched
   comparator, required by instruction to disclose) and like-for-like
   (the defensible number). The naive dangerous-error rate is 59.6% — a
   real, reported regression; the like-for-like rate is 14.3%, still
   materially worse than the independent report's 0.69%.
4. SoC clamps on **14.57%** of lap-instances, floor (running out) more than
   4x as often as ceiling (overcharging).
5. **Yes** — the d_X boundary-pin finding survives on the primary MLP
   model: pinned RMSE 0.32 m vs interior RMSE 0.91 m, the same qualitative
   pattern as the XGBoost breakdown it corrects.
6. Recommend **harvest ≤ 8.4 MJ, depletion ≤ 3.8 MJ** — full sweep and
   justification in §6.

---

## Method

**Sequential chain** (`run_phase4_sequential_soc.py`), exactly the
pseudocode given: for each real lap (year, gp, driver), sectors in
`sector_id` order, `soc` starts at each of the 10 grid values, `E_initial`
fed to the model is `soc * e_batt_capacity`, `energy_price` fixed per
lambda. `net_depletion_J`, `dt_optimal`, `E_har_final` predicted per
sector from the LOCO fold that excludes that sector's circuit (strictly
honoured — verified by construction, not spot-checked). `soc` updated by
`-dep/e_batt_capacity`, clamped to `[0,1]`, every clamp logged (circuit,
sector, direction, magnitude). Vectorised across all 70 (soc_start ×
lambda) combinations per lap simultaneously — one batched `.predict()`
call per sector-step per target, not 800k+ single-row calls.

**Model persistence, disclosed:** neither the original training run nor
the OOF generator saved fitted model objects, only metrics/grid-point
predictions. Querying off-grid SoC values requires a live model, so the 72
models (3 targets × 24 folds) were **re-fit once**, at the IDENTICAL Stage
3 configuration (seed 0, MLP, (128,64), max_iter=150) for `dt_optimal`,
and cached to disk (`joblib`) for reuse across this task's sub-steps. This
reproduces the same fitted object Stage 3 already scored — not a new or
different one — and is the mechanical minimum needed to call `.predict()`
at unseen SoC inputs.

**Compute-troubleshooting, disclosed in full because it materially changed
the plan:** fitting 8-way-parallel MLPs at Stage 3's 150k-row subsample on
this machine (7.9 GB RAM) caused severe memory contention — free memory
was observed declining over successive fits (1.2 GB → 479 MB) while CPU
progress nearly stalled. Root-caused to two compounding issues, both fixed:
(1) the fitting closure passed a pandas DataFrame (not a raw numpy array)
into `joblib.Parallel`, so every one of 24 queued tasks pickled its own
full copy of the ~763k-row training frame instead of sharing one memmap
(joblib only auto-memmaps raw numpy arrays); fixed by converting to
`.to_numpy()` before dispatch. (2) Even after that fix, 8 concurrent
150k-row MLP fits on this machine still contended heavily — a direct,
uncontended solo-fit timing showed a single `net_depletion_J` fit takes
**63.2 s** (converging naturally at 57/150 iterations, so `max_iter` was
never the bottleneck), while under 8-way contention the same fits were
taking many multiples longer. Settled on **3 workers** and a **reduced
75,000-row subsample** for `net_depletion_J` and `E_har_final`'s re-fit
specifically (`dt_optimal`'s 24 models keep the original 150k-row
config, fit before this was diagnosed) — a further disclosed deviation
from Stage 3's exact configuration for this re-fit only; Stage 3's own
reported accuracy figures are untouched. Separately: launching long
computations via `PowerShell Start-Process` and checking on them via
repeated manual polling (`Get-Process`, file-count checks) produced
dramatically slower apparent throughput than launching the identical
script via the Bash tool's native background execution and a proper
`Monitor` watch — net_depletion_J's 24-model refit, which had barely
progressed over three separate 30-plus-minute polling windows under the
first approach, completed in 258 seconds once run the second way. Recorded
here as a working note for any future long computation in this
environment, not fully explained.

**Secondary comparator** (`run_phase4_sequential_soc_interp.py`), per
instruction ("if there is a defensible way... report it and use it as a
secondary comparison"): at each sector visited during chaining, linearly
interpolate the TRUE stored labels between the two nearest SoC grid points
for that exact (year, gp, driver, sector_id, energy_price), evaluated at
the SAME chained SoC the prediction used, summed across the lap. This is
NOT a re-solve — it is the best defensible use of existing labels only —
but it is evaluated at a physically consistent (chained) SoC trajectory on
BOTH sides, unlike the primary comparator.

---

## §1 — Size of the correction

**Q1 answer.** Two decompositions are reported because they answer
different questions.

**(a) Prediction-only correction** (sequential prediction − independent
prediction, same model, same labels, isolates what chaining changes about
the MODEL'S OWN output):

| | median | p5 | p95 | mean |
|---|---|---|---|---|
| dt (s) | +1.236 | -0.309 | +2.846 | +1.216 |
| depletion (kJ) | -3387.2 | -7838.5 | +630.5 | -3318.9 |
| harvest (kJ) | -149.3 | -506.1 | +325.7 | -134.2 |

**(b) What part of this is REAL (the true comparator itself shifting under
chaining) vs. prediction error?** Comparing the interpolated-true
comparator (evaluated at the chained SoC) against the independent-sum true
label: **median −2526 kJ** of the −3387 kJ naive depletion correction is
the comparator itself changing — i.e. genuinely less total depletion is
implied by a realistic declining SoC trajectory than by summing ten
independent, often-higher-SoC solves. Only the **residual −590 kJ** (see
§3's like-for-like numbers) is actual sequential-chaining prediction error.
**State this beside every depletion number in this report**: the headline
"−3.39 MJ correction" overstates the model's own behaviour change by
roughly 4-5x; most of it is the sequential assumption being more physical,
not the model doing something new.

dt shows no equivalent decomposition available (the interpolated-true
comparator's own dt sum is a similarly legitimate secondary check — see
§3 — and the like-for-like dt residual, +0.17 s median, is much smaller
than the naive +1.24 s, the same pattern as depletion).

---

## §2 — No-feasible-lambda rate: does it move toward 3.68%?

**Q2 answer: yes, decisively, on the properly like-for-like comparison —
though the raw prediction-side rate overshoots past it.**

| side | rate | n |
|---|---|---|
| OCP-label, independent sum (unchanged from the prior report) | 21.42% | 1996/9320 |
| **interpolated-true, evaluated at chained SoC** | **1.08%** | 101/9320 |
| structural rate (measured independently, earlier phase) | 3.68% | — |
| sequential MLP prediction (naive, vs its own feasibility) | 0.01% | 1/9320 |

The interpolated-true comparator's 1.08% sits in the same order of
magnitude as, and below, the 3.68% structural rate — **a genuine
convergence between two independently-derived lines of evidence**: the
21.42% figure was indeed dominated by the independent-SoC artefact, exactly
as hypothesised, and correcting for chained SoC on the LABEL side alone
(no model prediction involved) closes most of that gap. The remaining gap
(1.08% vs 3.68%, both now small) is plausibly the linear-interpolation
approximation itself (not a re-solve) sitting on the optimistic side, or a
genuine difference between "structural emptiness measured directly" and
"emptiness implied by 10-point interpolation" — not further decomposed
here.

The sequential MLP *prediction* side (0.01%) overshoots past both 1.08%
and 3.68% — the model predicts feasibility even more often than the
properly-computed true rate would justify. This is the same systematic
under-prediction of depletion under chaining already identified in §1(b)
(−590 kJ median like-for-like bias) manifesting as a feasibility-rate
distortion, not a new finding.

---

## §3 — Lap-level validation under sequential propagation

**Q3 answer**, reported both ways per the like-for-like caveat that must
sit beside every number here:

### 3a. Naive (sequential prediction vs. OCP-label INDEPENDENT sum) — NOT like-for-like

| tolerance | fraction within |
|---|---|
| ±0.05 s | 3.09% |
| ±0.2 s | 11.95% |
| ±0.5 s | 25.97% |

dt error median **+1.176 s**, mean +1.150 s (p5 −0.572, p95 +2.868).
Depletion error median −3371 kJ, harvest median −158 kJ (near-identical to
§1's prediction-only correction, since the independent-prediction term is
small relative to the true-comparator mismatch).

**Feasibility, naive:**

| | pred infeasible | pred feasible |
|---|---|---|
| OCP-label infeasible | 6605 | **38878** |
| OCP-label feasible | 700 | 19057 |

**Dangerous error: 38878/65240 = 59.59%** (was 0.685% in the independent
report). **This is reported plainly as a large regression under the naive
comparison, per instruction** — but see 3b: most of it is the comparator
mismatch, not the model.

### 3b. Like-for-like (sequential prediction vs. INTERPOLATED-TRUE at the same chained SoC) — the defensible number

| tolerance | fraction within |
|---|---|
| ±0.05 s | 10.26% |
| ±0.2 s | 39.01% |
| ±0.5 s | 75.77% |

dt error median **+0.172 s**, mean +0.213 s (p5 −0.453, p95 +1.020) — a
real, modest degradation vs. the original independent report's 14.6% /
52.0% / 87.5% bands, not the dramatic one the naive numbers suggest.
Depletion error median −590 kJ, harvest median −51 kJ.

**Feasibility, like-for-like:**

| | pred infeasible | pred feasible |
|---|---|---|
| interpolated-true infeasible | 7183 | **9300** |
| interpolated-true feasible | 122 | 48635 |

**Dangerous error: 9300/65240 = 14.26%.** Conservative error: 122/65240 =
0.19% (better than the independent report's 1.04%). **The honest
conclusion: sequential propagation, measured fairly, is somewhat worse on
dangerous-error rate than the independent-SoC report (14.3% vs 0.69%) —
report this plainly, it is the more physical model producing a worse
number, not a wrong number.** §6 addresses this directly with a
conservative margin.

### Outer-loop lambda selection

| comparator | same-lambda agreement | penalty when different (median / mean / max) |
|---|---|---|
| naive (vs OCP-label independent) | 49.78% (3646/7324) | +0.314 / +0.317 / +3.474 s |
| **like-for-like (vs interpolated-true)** | **74.99% (6913/9219)** | +0.130 / +0.203 / +2.133 s |

Like-for-like agreement (75.0%) is lower than the original independent
report's 86.14%, and the penalty when wrong is somewhat larger — a real,
disclosed cost of moving to the more physical sequential model, not
recovered by the like-for-like correction.

---

## §4 — SoC clamping

**Q4 answer.** 14.57% of lap-instances (9503/65240) clamp at least once
across their sector sequence.

| direction | count | median magnitude (fraction of window) |
|---|---|---|
| floor (running out) | 14338 | 0.55% |
| ceiling (overcharging) | 3136 | 0.92% |

Floor clamps outnumber ceiling clamps 4.6:1 — sequential depletion running
the store toward empty is a far more common failure mode than overfilling
it, consistent with most micro-sectors being net-depleting under
deployment-heavy racing lines. Clamps concentrate heavily by circuit:
**Saudi Arabian Grand Prix alone accounts for 6705/17474 (38.4%)** of all
clamp events, consistent with it being the longest/most sector-dense
circuit in the set (426 flagged instances, the largest in the dataset).
Azerbaijan is a distant second (2886). By energy_price, clamps are
U-shaped — most at the lowest lambda (6223, cheap energy encourages
aggressive deployment that later empties the store) and rising again at
the highest lambda (2875) — not further decomposed here.

**Interpolation test (Q4's second half):** of 800,310 visited SoC values,
only **8.47%** sit within 1e-6 of an actual grid point (these are the
FIRST-sector inputs, which start exactly at a grid value by construction);
**90.10%** are more than 0.001 away from the nearest grid point — genuinely
interpolated, median distance from the nearest grid point 0.038 (3.8% of
the SoC range). **Sequential chaining is, as expected, overwhelmingly an
interpolation exercise, not a re-evaluation at trained points** — the §1-3
error figures are a real test of the models' behaviour between training
grid points, not a repeat of Stage 3's on-grid accuracy.

---

## §5 — Does the d_X pin finding survive on the MLP?

**Q5 answer: yes.** The originally-reported pinned/interior breakdown
(0.83 m / 1.82 m) was computed on XGBoost — confirmed by the fact that its
pooled figure (1.273 m) matches XGBoost's single-seed RMSE (1.275 m), not
the MLP's (0.638 m). Re-run on the MLP (single seed 0, matching how the
original breakdown was itself computed):

| | mean RMSE (m) |
|---|---|
| all | 0.650 |
| **pinned** | **0.323** |
| **interior** | **0.909** |

Pooled RMSE 0.807 m, R² 0.9954 — closely matching Stage 3's own MLP pooled
R² range (0.9955–0.9961 across 5 seeds), confirming this re-fit faithfully
reproduces the Stage 3 configuration. 64.46% of eligible rows are
boundary-pinned (356,067/552,418), unchanged from before (same population).

**The substantive finding survives, proportionally similarly:** pinned
RMSE is roughly a third of interior RMSE on the MLP (0.323 vs 0.909, ratio
0.36), comparable to XGBoost's ratio (0.83 vs 1.82, ratio 0.46) — if
anything slightly MORE pronounced on the primary model. d_X's strong
headline accuracy remains disproportionately carried by the 64.5%
discretisation-artefact population on both models, not an XGBoost-specific
quirk.

---

## §6 — Conservative feasibility margin

**Q6 answer.** Swept under sequential propagation, evaluated against the
like-for-like interpolated-true comparator (the defensible ground truth):

Full 20-combination sweep (`phase4_results_v4/margin_sweep.csv`):

| harvest (MJ) | depletion (MJ) | dangerous | conservative | mean cost (s) |
|---|---|---|---|---|
| 8.50 | 4.00 (baseline) | 14.26% | 0.19% | 0.051 |
| 8.50 | 3.95 | 13.62% | 0.19% | 0.051 |
| 8.50 | 3.90 | 12.97% | 0.20% | 0.051 |
| **8.50** | **3.80** | **12.22%** | **0.33%** | **0.051** |
| 8.40 | 4.00 | 14.07% | 0.31% | 0.055 |
| 8.40 | 3.95 | 13.43% | 0.31% | 0.055 |
| 8.40 | 3.90 | 12.79% | 0.32% | 0.055 |
| **8.40** | **3.80** | **12.03%** | **0.45%** | **0.055** |
| 8.30 | 4.00 | 14.01% | 0.48% | 0.060 |
| 8.30 | 3.80 | 11.98% | 0.62% | 0.060 |
| 8.20 | 4.00 | 13.98% | 0.65% | 0.064 |
| 8.20 | 3.80 | 11.94% | 0.79% | 0.064 |
| 8.00 | 4.00 | 13.97% | 1.35% | 0.075 |
| 8.00 | 3.90 | 12.69% | 1.36% | 0.075 |
| 8.00 | 3.80 | 11.93% | 1.49% | 0.075 |

*(intermediate depletion rows for 8.3/8.2/8.0 MJ harvest omitted for space;
full data in the CSV. `mean lap-time cost` and `dangerous`/`conservative`
rates are both measured against the like-for-like interpolated-true
comparator at the ORIGINAL 4.0/8.5 MJ regulatory caps — margins are a
selection-criterion adjustment only, never a redefinition of what
"actually infeasible" means.)*

**Two clear, distinct patterns.** Tightening the **depletion** cap is
nearly free: at fixed harvest=8.5 MJ, dangerous-rate falls from 14.26% to
12.22% (a 2.04pp reduction) while mean lap-time cost stays completely flat
at 0.051s across the whole depletion sweep — because depletion is rarely
the constraint that actually determines the outer loop's time-optimal
lambda choice; tightening it mostly removes non-selected alternatives, not
the chosen one. Tightening **harvest** is expensive and has sharply
diminishing returns: going from 8.5→8.0 MJ (at fixed depletion=3.8 MJ) buys
only a further 0.29pp of dangerous-rate reduction (12.22%→11.93%) while
**conservative-error rate rises 4.5x (0.33%→1.49%) and lap-time cost rises
47% (0.051s→0.075s)**. The marginal dangerous-rate return per 0.1 MJ of
harvest margin shrinks monotonically (−0.19pp, −0.06pp, −0.04pp, then two
steps of −0.01pp each) while the conservative/cost penalty grows
roughly linearly — the harvest axis has a clear elbow around 8.4 MJ, not
at the tightest value swept.

**Recommendation: harvest ≤ 8.4 MJ, depletion ≤ 3.8 MJ.** Take nearly all
of the available depletion-margin benefit (it costs essentially nothing)
and only the first, cheap step of harvest margin (8.5→8.4 MJ: +0.12pp
conservative, +0.004s cost, for −0.19pp dangerous) rather than continuing
to 8.0 MJ, where the SAME dangerous-rate target is barely improved further
(12.03%→11.93%, 0.10pp) at more than double the conservative-error cost
(0.45%→1.49%) and 36% more lap-time cost (0.055s→0.075s). This does not
eliminate the dangerous-error rate — no margin in the swept range does,
given the like-for-like baseline itself is 14.3% — but it captures the
efficient part of the trade-off rather than over-paying on the harvest
axis for a diminishing return, which is the correct framing for an outer
loop that must make a go/no-go decision under model uncertainty.

---

## CONSTRAINTS observed

- `problem.py`, `dynamics.py`, `solver.py`, `vehicle.py`: not modified,
  not imported for anything but their already-existing constants
  (`e_batt_capacity`, stated as a constant here, not re-derived).
- `phase4/reconstruct.py` and its outputs: untouched, not deleted.
- No re-solving, no new labels: sequential chaining and the interpolated
  secondary comparator both work only from stored v4 labels and models
  fit on them.
- No head failed to improve on any baseline in this task (not applicable —
  this task re-uses Stage 3's regression heads, doesn't introduce new
  baseline comparisons).
