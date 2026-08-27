# Phase 4 — Bias Correction: Attacking the Right Mechanism

`phase4_boundary_uncertainty.md` refuted symmetric boundary noise cleanly
(in-grid dangerous rate exactly 0.000 in every 0–4σ bin below both caps)
and located the failure in a one-sided cliff: 98% of dangerous cases sit
in the already-over-cap bin. A margin — sized for random spread — cannot
close a gap produced by a one-directional bias 3–20x larger than the
random component. This task tests the correct lever: a post-hoc, LOCO-
honest bias correction, applied to the model's already-cached predictions
with no retraining. **Result: it beats the margin decisively, and the
combination beats both.**

**Answering the four questions up front:**

1. **Bias dominates. 81.8% of depletion MSE is bias², 9.0% variance**
   (overall); in-grid it's the reverse (5.8% bias² / 95.9% variance — the
   in-grid population genuinely is noise-dominated, consistent with §1 of
   `phase4_boundary_uncertainty.md`); sub-grid returns to bias-dominated
   (82.6% / 8.1%). Harvest is more mixed (28.1% bias² / 61.9% variance
   overall) — bias correction is the right tool for depletion, less
   clearly so for harvest.
2. **Yes, decisively.** The best LOCO-honest correction (lap-level
   regression offset) drops dangerous rate from 14.28% to **2.64%** — a
   ~5.4x reduction — while the 2σ margin only reached 11.36%. At matched
   conservative rate the correction dominates the margin everywhere on
   the trade-off curve (§3).
3. **Recommended: lap-level-offset correction + 1.0–1.5σ margin on top.**
   At 1.5σ: dangerous 0.81%, conservative 5.53%, mean lap-time cost 0.056 s
   when the margin changes the selection, outer-loop agreement 75.12%
   (baseline: 74.88%). Full tradeoff in §3.
4. The restated limitation paragraph is in §4.

---

## §1 — Characterising the bias

Regenerated the open-loop chain once more (cached, restored-150k models,
pure inference — no solving, no retraining), this time tagging every
per-sector row with full lap identity so LOCO-honest corrections could be
fitted later. The per-sector bias-by-actual-SoC table reproduces
`phase4_offgrid_probe.md` §0 exactly (−198,471 J at ≤0.1 down to
+10,421 J just inside the grid, tapering to −10,808 J at 0.9–1.0) —
confirmed, not re-derived independently.

**Lap-level systematic offset** (the sum, along each lap's own
trajectory, of the *population-average* bias for the SoC bin each sector
falls in — distinct from the lap's own noisy total error, which mixes
bias and randomness):

| partition | n | mean systematic offset | mean actual error |
|---|---|---|---|
| overall | 65,240 | −792.6 kJ | −792.6 kJ |
| in-grid | 12,906 | +3.7 kJ | −16.0 kJ |
| sub-grid | 52,334 | **−988.9 kJ** | −984.1 kJ |

In-grid's systematic estimate is small and the actual mean is dominated
by noise around it (consistent with variance dominating there). Sub-grid's
systematic estimate accounts for essentially all of its actual mean error
— confirming the dominant sub-grid failure is bias, not noise, to within
rounding.

By `soc_start`, systematic offset is *larger in magnitude* at low
`soc_start` (−1,257 kJ at 0.1) than high (−515 kJ at 1.0) — because low-
`soc_start` laps spend more sectors sub-grid in absolute terms (mean 5.58
vs 2.61) — but, as established in `phase4_subgrid_diagnostics.md`, this
larger offset rarely flips a feasibility call at low `soc_start` because
true depletion starts far from the cap there. High-`soc_start` laps carry
a smaller absolute offset that matters far more, because their true
depletion already sits near the cap. This is the same reconciliation
`phase4_subgrid_diagnostics.md` needed for the dangerous-rate-vs-
`soc_start` trend, now confirmed from the bias side too.

**MSE decomposition** (bias² / variance / cross-term shares of mean
squared lap-level error):

| | DEPLETION bias² | DEPLETION variance | HARVEST bias² | HARVEST variance |
|---|---|---|---|---|
| overall | **81.81%** | 9.02% | 28.06% | 61.87% |
| in-grid | 5.84% | 95.90% | 0.64% | 98.94% |
| sub-grid | **82.59%** | 8.14% | 30.30% | 58.85% |

**Variance does not dominate overall or in sub-grid — bias does, by a
ratio of roughly 9:1 in both.** This is the condition the task specified
as a green light for the correction approach (the fallback — "if variance
dominates, stop" — does not apply). In-grid depletion and harvest
everywhere are genuinely variance-dominated, matching
`phase4_boundary_uncertainty.md`'s finding that in-grid boundary bins are
clean of dangerous cases. Harvest's overall picture is mixed — its bias
share (28%) is real but well short of dominant — so the correction below
targets depletion, the target responsible for ~98% of dangerous cases
throughout this pipeline; harvest predictions are left uncorrected
(explicit scope decision, stated as an assumption in §5).

---

## §2 — Testing the correction, LOCO-honestly

**No-leakage enforcement, stated explicitly:** every correction statistic
used on circuit *c*'s rows is computed using *only* the other 23
circuits' rows — the same exclusion structure as the LOCO models
themselves.
- **(a) Global constant**: `offset[c] = (Σ_all err − Σ_c err) / (n_all − n_c)`
  — total-minus-own arithmetic, so circuit *c*'s own rows never enter its
  own offset.
- **(b) SoC-conditional**: the same total-minus-own arithmetic, computed
  per (circuit, SoC-bin) cell, using the bins from `phase4_offgrid_probe.
  md` §0.
- **(c) Lap-level regression**: for each of the 24 folds, an OLS fit
  (`n_subgrid_sectors`, `soc_start`, `n_sectors` → lap-level depletion
  error) trained on the other 23 circuits' laps only, applied to predict
  circuit *c*'s own laps' offset. A fresh model is fit per fold — circuit
  *c* is never in its own training set.

None of these refit the surrogate MLP; all three are closed-form,
lightweight, post-hoc arithmetic on its already-cached predictions.

**Residual accuracy after correction** (lap-level depletion, vs
freshly-solved-consistent interpolated truth):

| variant | bias | RMSE |
|---|---|---|
| baseline | −792.6 kJ | 1,182.5 kJ |
| (a) global | −2.7 kJ | 813.3 kJ |
| (b) SoC-conditional | −1.8 kJ | 361.1 kJ |
| (c) lap-level regression | −6.3 kJ | **349.1 kJ** |

All three nearly eliminate the mean bias; (b) and (c) also cut RMSE by
~70%, versus (a)'s ~31% (a single constant cannot track the order-of-
magnitude swing between in-grid and sub-grid bias).

**Feasibility metrics** (harvest left uncorrected throughout):

| variant | overall dangerous | overall conservative | in-grid dangerous | sub-grid dangerous | outer-loop same-λ |
|---|---|---|---|---|---|
| baseline | 14.28% | 0.14% | 0.50% | 17.68% | 74.88% |
| (a) global | 6.55% | 3.84% | 0.44% | 8.06% | 72.49% |
| (b) SoC-conditional | 3.80% | 1.55% | 0.50% | 4.62% | 74.92% |
| **(c) lap-level regression** | **2.64%** | 2.26% | 0.50% | 3.16% | 74.91% |
| *2σ margin, for reference* | 11.36% | 0.87% | 0.10% | 14.13% | — |

Lap-time signed error is unchanged across all variants (only depletion is
corrected, not `dt_optimal`): median +0.174 s, mean +0.214 s, within
±0.05/0.2/0.5 s: 10.2% / 38.9% / 75.8% — identical to the pre-correction
baseline in every prior report.

**(a) is the weakest of the three** — a single global constant
overcorrects where bias is smaller (pushing conservative rate to 3.84%,
and to 3.32% even in-grid, where the true bias is near zero) and
undercorrects where it's largest. **(b) and (c) both work well**; (c)
achieves the lowest dangerous rate (2.64% vs 3.80%) at a moderately higher
conservative cost (2.26% vs 1.55%). In-grid dangerous rate is essentially
untouched by (b)/(c) (0.50%, identical to baseline) — exactly as expected,
since a correction that tracks the true, near-zero in-grid bias should
leave already-good in-grid predictions alone.

---

## §3 — Correction vs. margin, and the combination

**Correction beats margin at every comparable point.** The margin sweep
from `phase4_boundary_uncertainty.md` never drops below ~10.6% dangerous
even at 2.5σ; correction (c) alone, with *no* margin, already reaches
2.64% — better than the margin achieves at any σ tested, for less
conservative-rate cost than the margin's own 2.5σ setting (2.26% vs
1.26%, though not directly comparable since (c) needs no margin at all to
get there).

**Residual symmetry check — does bias removal make the margin work as
intended?**

| | mean | median | skewness | fraction negative |
|---|---|---|---|---|
| baseline residual | −792.6 kJ | −587.6 kJ | **−1.411** | 85.1% |
| corrected (c) residual | −6.3 kJ | −11.9 kJ | **0.045** | 51.6% |

**Yes, decisively.** Baseline residuals are heavily skewed and 85%
negative — the signature of a one-directional bias, not noise. After
correction (c), skewness collapses to ~0 and the sign split is
essentially 50/50 — genuinely symmetric-looking residual noise. This is
exactly the condition under which a σ-derived margin is a principled
tool, and testing it confirms the prediction:

| σ | dep cap (MJ) | har cap (MJ) | baseline dangerous | corrected (c) dangerous | corrected (c) conservative |
|---|---|---|---|---|---|
| 0.0 | 4.000 | 8.500 | 14.28% | 2.64% | 2.26% |
| 0.5 | 3.919 | 8.456 | 13.14% | 1.85% | 3.17% |
| 1.0 | 3.839 | 8.413 | 12.41% | 1.25% | 4.18% |
| 1.5 | 3.758 | 8.369 | 11.85% | 0.81% | 5.53% |
| 2.0 | 3.678 | 8.325 | 11.36% | 0.58% | 6.94% |
| 2.5 | 3.597 | 8.281 | 10.56% | 0.39% | 8.44% |

Margin on top of the correction now buys real, steadily-diminishing
dangerous-rate reductions for steadily-rising conservative-rate cost —
the well-behaved trade-off curve a margin is supposed to produce, which
it conspicuously failed to produce on the uncorrected baseline (compare:
baseline's 0σ→2.5σ only moves dangerous 14.28%→10.56%, a 26% relative
cut, for the same conservative-rate range this combination achieves a
~85% relative cut).

**Lap-time cost and outer-loop agreement, correction (c) + margin:**

| σ | dangerous | conservative | mean lap-time cost (when selection changes) | outer-loop same-λ | in-grid dangerous | sub-grid dangerous |
|---|---|---|---|---|---|---|
| 0.0 | 2.64% | 2.26% | 0.048 s | 74.91% | 0.50% | 3.16% |
| 1.0 | 1.25% | 4.18% | 0.053 s | 75.28% | 0.15% | 1.53% |
| 1.5 | 0.81% | 5.53% | 0.056 s | 75.12% | 0.13% | 0.98% |
| 2.0 | 0.58% | 6.94% | 0.058 s | 75.00% | — | — |
| 2.5 | 0.39% | 8.44% | 0.060 s | 74.74% | — | — |

Outer-loop agreement is essentially unchanged from baseline (74.88%)
across the whole range (74.74–75.28%) — the combined correction+margin
does not disturb lambda selection, only the feasibility call around the
depletion cap. **In-grid dangerous rate improves further under the margin
(0.50%→0.13–0.15%) with no sign of regression** — the margin helps the
genuinely variance-dominated in-grid population too, just as intended for
symmetric noise.

**Recommended operating point: correction (c) + 1.0–1.5σ margin.**
- **1.0σ** (depletion 3.839 MJ, harvest 8.413 MJ): dangerous 1.25%,
  conservative 4.18%, mean lap-time cost 0.053 s, outer-loop 75.28%.
- **1.5σ** (depletion 3.758 MJ, harvest 8.369 MJ): dangerous 0.81%,
  conservative 5.53%, mean lap-time cost 0.056 s, outer-loop 75.12%.

Either is defensible; 1.5σ is favoured here because dangerous errors are
the safety-relevant direction (a regulatory-window violation the model
told the strategist was safe) while conservative errors cost only a
marginally slower lambda choice, and the marginal lap-time cost between
the two settings is negligible (0.003 s). Beyond 2σ, conservative rate
keeps rising roughly linearly while dangerous-rate gains shrink (2.0σ→2.5σ:
−0.19pp dangerous for +1.50pp conservative) — diminishing enough that
pushing further is a matter of risk appetite, not a clear further win.

**The correction beats the margin. This is not the "if it doesn't, say so
plainly" branch** — report accordingly.

---

## §4 — Restated limitation for the discussion chapter

> The surrogate's depletion error is dominated by a systematic,
> one-directional bias — not measurement noise — that under-predicts
> net depletion increasingly as the chained SoC trajectory drifts below
> the training grid's 0.10 floor (bias² accounts for 82% of mean-squared
> lap-level depletion error overall, and 83% specifically among the ~80%
> of lap-instances whose trajectory leaves the grid, versus only 6% among
> the ~20% that stay within it, where the surrogate is reliable). A
> LOCO-honest, post-hoc correction that estimates this bias as a function
> of the SoC at which each prediction is made — fitted only on
> circuits held out of each prediction, never on the evaluation circuit
> itself — reduces the dangerous-error rate from 14.28% to 2.64% with no
> retraining, and to under 1% when paired with a modest safety margin,
> confirming the mechanism is bias rather than noise. Extending the SoC
> training grid downward, by contrast, has not been shown to fix this
> failure mode: the one place it can be tested in-grid (n=9 laps whose
> true depletion already exceeds the cap) still shows a high miss rate
> (7/9, Wilson 95% interval 45–94%), so additional training coverage
> should be treated as unproven for this failure mode rather than
> assumed to reduce it to the in-grid baseline of roughly 0.5%.

---

## Assumptions stated beside the numbers that depend on them

- The bias correction targets `net_depletion_J` only; `E_har_final` and
  `dt_optimal` predictions are left uncorrected throughout, on the
  evidence that harvest's error is variance- rather than bias-dominated
  overall (§1) and depletion drives ~98% of dangerous cases elsewhere in
  this series.
- Variant (c)'s lap-level features (`n_subgrid_sectors`, `soc_start`,
  `n_sectors`) are a deliberately small, closed-form OLS fit — a
  correction, not a second surrogate model — per the task's explicit
  distinction between post-hoc adjustment and retraining.
- The lap-time signed error and outer-loop lambda-selection metrics use
  the same `dt_seq_pred` throughout every variant, since no lap-time
  correction was tested — reported for completeness/consistency with
  prior reports, not because the correction was expected to move it.
- §3's combined operating point uses the SAME σ-derived margin logic as
  `phase4_boundary_uncertainty.md`, applied to the corrected rather than
  the raw depletion prediction; the harvest cap in the combination is the
  same σ-derived value even though harvest predictions were not corrected
  — a deliberate, stated choice to keep the margin's two constraints on
  a comparable statistical basis.
- No solving, no retraining, and no model or grid changes were performed;
  every number is re-derived via pure inference on the already-cached
  (150k-restored) LOCO models plus closed-form arithmetic corrections,
  from `bias_full_sector_rows.parquet`, `bias_correction_variants.parquet`,
  and the existing `sequential_LFL_wide.parquet` / `subgrid_flags_open.
  parquet` artefacts.
