# Phase 4 — Sequential SoC Propagation, v2: Diagnosing the Dangerous-Error Rate

`phase4_sequential_soc.md` (v1) found that chaining SoC across real laps
moves the no-feasible-lambda rate from 21.42% (independent-SoC) to 1.08%
(like-for-like), converging on the independently-measured 3.68% structural
rate — the strongest validation result in this project. It also found the
dangerous-error rate (predicted feasible, actually infeasible) rising from
0.685% (prior, independent-SoC report) to 14.3% (sequential, like-for-like).
Three confounds were identified before that number could be trusted: (1)
`net_depletion_J` — the head that drives the entire recursion — had been
re-fit at a reduced 75,000-row subsample rather than Stage 3's 150,000, for
compute reasons, while `dt_optimal` had not; (2) the like-for-like
comparator's own SoC-grid linear interpolation has unmeasured noise; (3) a
14.3% *count* says nothing about violation *size*, and pure error
compounding (quadrature vs linear bounds on Stage 3's 45.97 kJ per-sector
RMSE) predicts 3.98%–13.79% depletion-window consumption, not obviously
enough to explain the jump from 0.685%.

**This report resolves all three. Answering the five questions up front:**

1. **No — restoring `net_depletion_J` to the exact Stage 3 config (150k
   subsample, seed 0) does not move the dangerous rate.** 14.26% → 14.28%.
   The compute-shortcut confound is ruled out.
2. **The comparator's own interpolation error is comparable to, or larger
   than, the model's reported error.** For `net_depletion_J` specifically —
   the target that matters — leave-one-out interpolation RMSE is 66.5 kJ,
   45% *larger* than the model's own 45.97 kJ RMSE. Part of the 14.3% is
   measuring comparator noise, not model failure — though, per point 3
   below, this is a smaller part of the story than compounding noise turns
   out to be.
3. **The dangerous violations are large, not near-boundary.** Median
   depletion overshoot at dangerous cases is 505 kJ (12.6% of the 4 MJ
   window), p95 is 2,013 kJ (50.3% of the window). The model's own
   predicted margin at those same cases was a comfortable 824 kJ (median) —
   it was not hovering near its decision boundary and getting tipped by
   noise; it was confidently wrong.
4. **Chained errors are correlated, and neither compounding bound holds —
   because the premise behind both bounds is false.** Consecutive-sector
   error correlation is r=0.30 (lag-1), decaying slowly (r=0.19 at lag-3).
   But the bigger finding is that per-sector error is not stationary along
   the chain: it matches Stage 3 almost exactly (45.9 kJ) at the first,
   on-grid sector, then grows monotonically — driven by a systematic,
   growing **negative bias** (the model under-predicts depletion) — to over
   250 kJ by the 18th sector of a lap. This is covariate shift: the model
   was scored on SoC values snapped to a 10-point grid, and the recursion
   feeds it continuous, increasingly off-grid values it was never evaluated
   on. This growing optimistic bias, not noise compounding, is what drives
   the dangerous rate, and it is a sharper, more damaging characterization
   than "errors compound."
5. Restated validation under the restored models is in §5 — every number
   from v1 either holds within noise or is explained by the mechanism
   above. The margin recommendation (**harvest ≤ 8.4 MJ, depletion ≤ 3.8
   MJ**) still holds, understood now as a genuine but limited mitigation:
   it cannot push the dangerous rate below ~12% in the swept range, because
   most violations are too large for a few-hundred-kJ margin to catch.

---

## Method and disclosure

Everything below reuses `run_phase4_sequential_soc.py`'s existing sequential
chain (real laps, `sector_id` order, LOCO-fold models, vectorised over all
70 soc×lambda combinations per lap) and the disclosed model-persistence
mechanism from v1: the 72 MLP models (3 targets × 24 LOCO folds) are re-fit
once, at Stage 3's exact configuration, because the fitted objects
themselves were never saved by the original training run. No hyperparameter,
architecture, feature, or seed change from Stage 3 — the only change made
in this report is restoring `net_depletion_J` and `E_har_final` from the
75,000-row subsample used in v1 (a disclosed compute shortcut) back to
Stage 3's 150,000. `dt_optimal` was never reduced. No re-solving, no new
labels, `problem.py`/`dynamics.py`/`solver.py`/`vehicle.py` untouched,
`reconstruct.py` untouched.

Re-fit timings (3 workers, raw-numpy `joblib` dispatch — the memory-
contention fix already diagnosed in v1): `dt_optimal` 6s (cache hit, unchanged),
`net_depletion_J` 880s, `E_har_final` 725s.

---

## §1 — Does restoring `net_depletion_J` change the dangerous rate?

**Verification gate (required before using the re-fit):** pooled LOCO
accuracy of the restored models against Stage 3's reported figures.

| target | this refit (seed 0) pooled R² | this refit RMSE | Stage 3 (mean ± SD, 5 seeds) |
|---|---|---|---|
| `net_depletion_J` | 0.9896 | 51,486 J | R²=0.990±0.0003, RMSE=45.97±18.14 kJ |
| `E_har_final` | 0.9923 | 26,794 J | R²=0.992±0.0003, RMSE=24.97±8.18 kJ |

`E_har_final` is within Stage 3's reported seed-to-seed SD outright.
`net_depletion_J`'s pooled R² differs from the 5-seed *mean* by 0.0004 —
slightly more than one reported SD on R², but its RMSE differs from the
5-seed mean by only 5.5 kJ, well under a third of the reported 18.14 kJ
seed-to-seed SD. **Stated plainly: the 0.990±0.0003 figure is itself a
measure of seed-to-seed variance (5 independent seeds, each a full 24-fold
LOCO sweep), not a per-seed reproducibility bound — a single seed landing
within ~1 SD of that mean is exactly what the reported spread predicts, not
a sign Stage 3 is unreproducible.** This is corroborated independently in
§4 below: the very first sector of every chained lap evaluates
`net_depletion_J` at an on-grid `E_initial`, identical to Stage 3's own
evaluation condition, and its RMSE there is 45,858 J — a 0.24% difference
from Stage 3's reported 45.97 kJ. Treating this as **PASS**, not a stop
condition, and proceeding on that basis, stated explicitly as an assumption.

**Effect on the dangerous rate**, re-running the full sequential chain and
like-for-like comparator with the restored models:

| | 75k config (v1) | 150k config (restored, this report) | Δ |
|---|---|---|---|
| Dangerous error (LFL) | 14.26% | 14.28% | +0.02pp |
| Conservative error (LFL) | ~0.14% | 0.1426% | ~0 |
| Dangerous error (naive) | 59.59% | 59.64% | +0.05pp |
| No-feasible-lambda (LFL) | 1.08% | 1.24% | +0.16pp |

**The compute-shortcut confound is ruled out.** Restoring the full Stage 3
training configuration for the head that drives the entire recursion
changes nothing material. Whatever produces the 14.3% dangerous rate, it
is not degraded training data.

---

## §2 — The comparator's own interpolation error

The like-for-like comparator linearly interpolates stored TRUE labels
between SoC grid points 0.1 apart (400 kJ of window per gap). Leave-one-out
on the grid (predict each interior point, soc=0.2..0.9, from its two
neighbours; compare to the actual stored label; no models, no re-solve)
bounds this comparator's own noise:

| target | interpolation LOO RMSE | model RMSE (Stage 3) | ratio (interp/model) |
|---|---|---|---|
| `net_depletion_J` | 66,456.6 J | 45,970 J | **1.446** |
| `dt_optimal` | 0.0724 s | 0.089 s | 0.814 |
| `E_har_final` | 26,429.7 J | 24,970 J | 1.058 |

For `net_depletion_J` — the target that determines the depletion-side
dangerous rate — **the comparator's own ground-truth noise is 45% larger
than the model's reported error.** For `E_har_final` the two are
essentially equal (6% gap). Only `dt_optimal`'s comparator noise is
meaningfully smaller than model error.

The interpolation error is not flat across the SoC range — it is worst at
both extremes and flattest in the middle, the textbook signature of the
saturating nonlinearity Phase 3 established:

| soc | RMSE (kJ) | bias (kJ) |
|---|---|---|
| 0.2 | 89.4 | −52.8 |
| 0.3 | 77.3 | −33.6 |
| 0.4 | 67.8 | −20.1 |
| 0.5 | 63.1 | −12.8 |
| 0.6 | 50.6 | −1.8 |
| 0.7 | 51.2 | +0.5 |
| 0.8 | 54.7 | +4.0 |
| 0.9 | 67.8 | +18.5 |

Bias sign-flips from −52.8 kJ at low SoC to +18.5 kJ at high SoC — linear
interpolation cannot capture that curvature, so part of every number in
this pipeline that treats the interpolated grid as ground truth carries
this caveat. **This is real, but as §3–§4 show, it is a second-order
contributor next to the systematic bias mechanism identified there** — it
would inflate the dangerous rate by some amount on its own, but not by
enough to explain a 20x jump from the independent-SoC 0.685% baseline.

---

## §3 — Are the dangerous violations large, or near-boundary?

Of 9,318 dangerous cases (14.28% of 65,240 lap-instances), **97.9% are
depletion-cap violations and only 2.1% are harvest-cap violations, with
zero overlap** — depletion drives essentially the entire dangerous rate.

**Violation magnitude** (how far the true value exceeds the cap, where it
actually does):

| | n | median | p95 | max |
|---|---|---|---|---|
| depletion, kJ (% of 4 MJ cap) | 9,119 | 505.1 kJ (12.6%) | 2,013.3 kJ (50.3%) | 3,044.5 kJ (76.1%) |
| harvest, kJ (% of 8.5 MJ cap) | 199 | 96.5 kJ (1.1%) | 253.0 kJ (3.0%) | 570.8 kJ (6.7%) |

Half of dangerous depletion violations exceed 12.6% of the entire
regulatory window; the top 5% exceed *half the window*. These are not
boundary-adjacent rounding errors.

**Margin distribution** (cap − predicted value), all 65,240 lap-instances,
not just dangerous ones: median depletion margin is 2,563 kJ; only 1.55%
of all predictions sit within 100 kJ of the cap, and only 4.43% sit within
one grid-gap (400 kJ). Harvest is similar (median margin 3,292 kJ, 0.76%
within 100 kJ). **Predictions are not clustered near the boundary — this
is not a density effect where small noise flips many marginal cases.**

Confirming this at the dangerous cases specifically: the model's own
predicted margin to the cap was median **823.6 kJ for depletion** and
**4,341.7 kJ for harvest**. The model was not uncertain or borderline in
its own terms — it predicted comfortable feasibility while being
substantially, confidently wrong. **This is the same conclusion the margin
sweep in §5/v1 already hinted at: no swept margin setting drives the
dangerous rate much below 12%, because the violations are too large for a
few-hundred-kJ safety margin to catch.**

---

## §4 — Are chained errors correlated, and which bound applies?

**Consecutive-sector `net_depletion_J` prediction-error correlation**,
pooled across all 735,070 within-lap sector-pairs (restored 150k models,
evaluated against the same interpolated-true labels used throughout):

| lag | r | n pairs |
|---|---|---|
| 1 | 0.303 | 735,070 |
| 2 | 0.263 | 669,830 |
| 3 | 0.190 | 604,590 |

Positive and only slowly decaying — **errors are correlated, not
independent noise.** This alone would push the accumulation toward the
linear bound rather than the quadrature bound. But it does not fully
explain what was observed:

| n_sectors (most common) | RMS(accumulated error) | quadrature bound (√n·45.97kJ) | linear bound (n·45.97kJ) |
|---|---|---|---|
| 12 (mean n=12.27, all instances) | **1,182.5 kJ** | 161.0 kJ (7.3x too small) | 563.9 kJ (2.1x too small) |

**The observed accumulated error exceeds even the linear, "worst-case
fully-correlated" bound by more than 2x.** A stationary AR-type model with
r=0.30 and constant per-step σ=45.97 kJ predicts an accumulated RMS around
337 kJ — nowhere near the observed 1,182.5 kJ. The premise behind *both*
bounds — that per-sector error is a stationary 45.97 kJ throughout the
chain — is false. Measuring per-sector error directly, by position in the
lap:

| sector position in lap | RMSE (J) | bias (J) |
|---|---|---|
| 0 (first sector, on-grid `E_initial`) | 45,858 | −1,248 |
| 1 | 98,258 | −28,711 |
| 3 | 121,093 | −49,573 |
| 6 | 153,255 | −78,076 |
| 9 | 144,788 | −65,337 |
| 12 | 183,044 | −111,158 |
| 15 | 215,885 | −137,378 |
| 18 | 257,782 | −230,574 |

At the first sector — the one condition genuinely identical to Stage 3's
own evaluation (on-grid `E_initial`) — RMSE is 45,858 J, a 0.24% match to
Stage 3's 45.97 kJ. From the second sector onward, RMSE roughly doubles
immediately and grows monotonically, reaching 5.6x Stage 3's figure by
sector 18. Critically, this growth is dominated by an increasingly
negative **bias**, not just growing variance: the model systematically
**under-predicts** `net_depletion_J` more and more as the chain lengthens.

**Mechanism**: Stage 3 scored the model at `E_initial` values snapped to
the 10-point SoC grid — the only condition it was ever evaluated on. The
sequential recursion feeds the model's own predicted depletion back as the
next sector's `E_initial`, so after one step `E_initial` is a continuous,
off-grid value, and it drifts further off-grid every subsequent step as
errors accumulate. This is a covariate-shift regime the model was never
scored in, and in that regime it systematically believes less energy has
been spent than actually has — the chained SoC state is optimistically
biased, and because the bias feeds directly into the next step's input, it
compounds by construction, not by chance.

**This is the actual mechanism behind §3's finding.** The model is not
hovering near its feasibility boundary and getting flipped by symmetric
noise; a growing, directional, structural bias pushes genuinely-infeasible
laps into "predicted feasible" by large, growing margins the longer the
lap runs. **Neither the quadrature nor the linear bound applies, because
both assume the wrong error model. The correct characterization is: a
covariate-shift-driven bias that grows with rollout length, which is a
sharper and more diagnostic limitation than "errors compound" — it says
precisely why they compound (recursive feedback into out-of-training-
distribution inputs) and precisely where to look for a fix (SoC-drift-
aware training or periodic re-grounding, not more data at the existing
grid points).**

---

## §5 — Restated lap-level validation, under the restored models

*(All figures below use the restored 150k configuration for `net_depletion_J`
and `E_har_final`; `dt_optimal` unchanged throughout.)*

**Dangerous / conservative error, like-for-like comparator:**

| | rate |
|---|---|
| Dangerous (LFL) | 14.28% (9,318/65,240) |
| Conservative (LFL) | 0.14% (93/65,240) |
| Dangerous (naive, disclosed as mismatched — independent-sum comparator against sequential predictions) | 59.64% |

**Lap-time signed error** (sequential prediction − interpolated-true, at
the SAME chained SoC — the like-for-like, defensible comparison):

| | value |
|---|---|
| median | +0.174 s |
| mean | +0.214 s |
| within ±0.05 s | 10.21% |
| within ±0.2 s | 38.87% |
| within ±0.5 s | 75.82% |
| max \|error\| | 3.20 s |

**No-feasible-lambda rate** (932 laps × 10 SoC = 9,320 combinations):

| side | rate |
|---|---|
| OCP-label, independent-sum (unchanged reference) | 21.42% |
| Prediction side (sequential, naive) | 0.00% |
| Interpolated-true side (LFL) | 1.24% (116/9,320) |
| Structural rate (measured independently) | 3.68% |

Unchanged from v1's headline finding: the like-for-like comparator's rate
(1.24%, vs v1's 1.08%) still converges strongly toward the independently-
measured 3.68% structural rate from the 21.42% independent-sum baseline —
this result is robust to the model restoration.

**Outer-loop lambda-selection agreement:**

| comparator | same-lambda rate | penalty when different (median / mean) |
|---|---|---|
| independent "true" (naive, mismatched) | 49.39% (3,617/7,324) | 0.313 s / 0.318 s |
| interpolated-true (LFL, defensible) | 74.88% (6,892/9,204) | 0.127 s / 0.192 s |

**SoC clamping:** 14.19% of lap-instances hit a floor or ceiling clamp at
least once (v1: 14.57%); floor:ceiling ratio ≈3.65:1 (v1: >4x) — same
qualitative pattern, running out of energy is still far more common than
overcharging.

**Margin recommendation**, re-swept against the restored models
(`phase4_results_v4/margin_sweep.csv`):

| harvest cap | depletion cap | dangerous | conservative | mean lap-time cost when selection differs |
|---|---|---|---|---|
| 8.5 MJ (baseline) | 4.0 MJ (baseline) | 14.28% | 0.14% | 0.048 s |
| **8.4 MJ** | **3.8 MJ** | **12.15%** | **0.45%** | **0.054 s** |
| 8.0 MJ | 3.8 MJ | 12.04% (floor of the swept range) | 1.59% | 0.077 s |

Essentially unchanged from v1 (12.03%/0.45%/0.055s at the same setting).
**Recommendation stands: harvest ≤ 8.4 MJ, depletion ≤ 3.8 MJ** — but per
§3–§4, this should now be understood as a genuine, bounded mitigation
(shaves ~2pp off the dangerous rate at the most aggressive setting swept)
rather than a fix: most dangerous violations are large enough, and driven
by a growing directional bias rather than boundary noise, that no margin
in a practical range eliminates them. The dangerous rate does not go to
zero anywhere in the sweep.

---

## Summary of assumptions carried by the numbers above

- §1's PASS on the verification gate rests on treating Stage 3's "0.990 ±
  0.0003" as 5-seed variance rather than a per-seed reproducibility bound,
  corroborated independently by the on-grid first-sector RMSE match in §4.
- §2–§5 all use the SoC-grid linear-interpolation comparator as "true";
  §2 quantifies that this comparator itself carries 45–6% more noise than
  the model for `net_depletion_J`/`E_har_final` respectively, so every
  downstream number inherits that ceiling on precision.
- §4's mechanism (covariate shift from off-grid `E_initial`) is inferred
  from RMSE/bias growing monotonically with sector position within a lap;
  position is used as a proxy for cumulative SoC drift because drift is
  monotonically non-decreasing in position by construction of the
  recursion, not because position itself is claimed to be causal.
- No result in this report was obtained by adjusting architecture,
  features, hyperparameters, or seed from Stage 3 — only the training
  subsample size for two heads was restored to Stage 3's own value, per
  the task's explicit constraint.
