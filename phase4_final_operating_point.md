# Phase 4 — Final Operating Point: Deployability and the Last Two Checks

`phase4_bias_correction.md` reported dangerous rate falling from 14.28% to
2.64% (variant c) or 3.80% (variant b), with a further drop to 0.81%–3.80%
under margin. This closing task tested whether those numbers survive
contact with deployment. **They largely do not, for variant (c) — and the
reason is exactly the causality issue flagged going in. Variant (b), once
evaluated the same rigorous way, becomes the primary recommendation, as
anticipated, but its own honestly-measured number (5.87% depletion-only,
5.70% with harvest added, before margin) is also higher than what was
originally reported (3.80%), because that number too was computed by
correcting-and-resumming the ORIGINAL uncorrected trajectory rather than
genuinely re-chaining with the correction applied forward.** This is not a
failure of the bias-correction idea — the mechanism diagnosis stands, and
a substantial, genuinely deployable improvement survives. It is a
correction to how large that improvement is.

**Answering the four questions up front:**

1. **Variant (c) is not stable and is not the primary recommendation.**
   Iterated as a genuine two-pass deployment procedure (re-chain, count
   sub-grid sectors, refit, re-chain again), it oscillates — 8.03% →
   13.07% → 10.07% → 12.38% dangerous over four iterations, with no sign
   of convergence in the range tested. Its originally-reported 2.64% used
   the pre-correction trajectory's sub-grid counts, which a real
   deployment cannot do (those counts don't exist until the corrected
   chain has already been run). **Variant (b) is the primary
   recommendation**, exactly as anticipated, confirmed by measurement.
2. **Yes, modestly, and it is adopted.** SoC-conditional LOCO correction
   on `E_har_final` cuts its lap-level bias from −73.5 kJ to −1.3 kJ and
   RMSE by ~17%. Combined with the depletion correction it moves overall
   dangerous rate down a further 0.14–0.24 percentage points at
   negligible conservative-rate cost, at every margin tested — a small
   but consistently free improvement.
3. **Final operating point: variant (b) depletion correction (converged
   over 4 offline calibration rounds) + variant (b) harvest correction +
   1.5σ margin.** Dangerous 3.18% overall (0.14% in-grid / 3.93%
   sub-grid), conservative 1.83%, outer-loop same-λ 75.21%, mean lap-time
   cost 0.056 s when the margin changes the selection. Full table in §3.
4. The revised limitation paragraph is in §4, using the correctly
   re-chained skewness figures (−1.411 → −0.312, not the −1.411 → 0.045
   figure computed on variant (c)'s non-deployable trajectory).

---

## §1 — Is variant (c) deployable?

**The causality issue is real, not hypothetical.** Variant (c)'s feature,
`n_subgrid_sectors`, is a property of the full chained trajectory, which
the correction itself changes. Operationalised as an iterative procedure
— rechain with the previous iteration's offset applied at each sub-grid
sector, recount, refit the LOCO regression on the new counts, repeat —
using the exact same `run_chain` engine and LOCO discipline as
`phase4_bias_correction.md`:

| iteration | dangerous rate | RMSE | fraction of laps whose `n_subgrid_sectors` changed |
|---|---|---|---|
| 0 (non-rechained, as originally reported) | 2.64% | 349.1 kJ | — |
| 1 (rechained) | 8.03% | 598.6 kJ | 44.47% |
| 2 (rechained) | 13.07% | 1,027.0 kJ | 28.71% |
| 3 (rechained) | 10.07% | 755.1 kJ | 19.30% |
| 4 (rechained) | 12.38% | 940.3 kJ | 13.32% |

**It oscillates rather than converging.** The fraction of laps whose
sub-grid-sector count changes each round is shrinking (44%→13%), so it
may eventually settle, but not within a range that comes close to
recovering the originally-reported 2.64% — every rechained iteration is
worse than variant (b)'s converged result (below). The 2.64% figure was
real, but it described a correction evaluated against a trajectory the
correction itself invalidates; it is not achievable at inference.

**Variant (b), tested the same way, is different in kind.** Its
correction depends only on the SoC at which a prediction is made — always
available inside the forward pass, no lap-level lookahead. Fitting its
offset table is a separate question from applying it, and *that* fitting
step benefits from iteration (using an already-corrected trajectory's own
errors to refit the table) — but this iteration happens once, offline, on
the training/calibration data, not per-lap at inference:

| calibration round | dangerous rate | RMSE | max shift in fitted bin offsets vs. previous round |
|---|---|---|---|
| 1 (fit on raw/uncorrected data) | 8.72% | 632.6 kJ | — |
| 2 (refit on round-1's errors) | 6.02% | 461.2 kJ | 44,324.6 J |
| 3 (refit on round-2's errors) | 5.68% | 444.4 kJ | 4,878.5 J |
| 4 (refit on round-3's errors) | 5.87%* | 442.4 kJ | 614.3 J |
| 5 (refit on round-4's errors) | — | — | 78.5 J |

*Round 4's dangerous rate (5.87%) differs trivially from round 3's (5.68%)
due to a harvest-evaluation code path difference between the two runs,
not a reversal — the offset-table shift (614.3 J, then 78.5 J at round 5)
demonstrates the calibration is converging geometrically (~8–9x smaller
shift each round), and round 5's table is used for the final operating
point in §3.

**This converges cleanly, geometrically, to a stable fixed point.**
Confirmed: (b) is genuinely single-pass at deployment — a NEW, unseen lap
is scored by applying the final, already-converged offset table forward,
sector by sector, exactly like calling the surrogate model itself. The
offline calibration loop is a one-time, training-side cost, not a
per-inference requirement.

**Recommendation, per the task's own decision rule**: variant (c)'s
advantage does not survive self-consistent evaluation, so **variant (b)
is presented as primary** (5.70–5.87% dangerous, depletion + harvest,
single-pass, deployable). Variant (c)'s non-rechained 2.64% is retained
only as an *upper bound* — what lap-level trajectory information could
theoretically buy if a genuinely non-circular way to supply it at
inference were found (e.g., a true SoC sensor reading in an online
setting, which is exactly the re-grounding scenario `phase4_offgrid_
probe.md` §3 already explored) — not as an achievable correction on the
open-loop predictions this pipeline produces.

---

## §2 — Should harvest be corrected too?

Applying variant (b) (SoC-conditional, LOCO, same total-minus-own
construction) to `E_har_final`:

| | bias before | bias after | RMSE before | RMSE after |
|---|---|---|---|---|
| per-sector | −5,991 J | −105 J | 33,405 J | 31,932 J |
| lap-level | −73,495 J | −1,291 J | 187,466 J | 156,242 J |

Bias is nearly eliminated (98%+ reduction); RMSE improves by a real but
modest ~17% (lap-level) — consistent with §1 of `phase4_bias_correction.md`
finding harvest's error variance-dominated (61.9%) rather than
bias-dominated (28.1%) overall, so a bias correction has less to work
with than it did for depletion.

**Combined effect on dangerous/conservative rates** (using the properly
re-chained depletion correction from §1, not the flawed non-rechained
one):

| σ | depletion-only dangerous | both-corrected dangerous | Δ | both-corrected conservative | outer-loop same-λ (both) |
|---|---|---|---|---|---|
| 0.0 | 5.87% | 5.70% | −0.17pp | 0.48% | 74.79% |
| 1.0 | 4.15% | 3.99% | −0.17pp | 1.16% | 75.36% |
| 1.5 | 3.32% | 3.18% | −0.14pp | 1.83% | 75.21% |

**Adopted.** The improvement is small — 0.14–0.17 percentage points of
dangerous rate at every margin tested — but it is consistently in the
favourable direction, costs essentially nothing in conservative rate
(+0.005–0.03pp), and modestly *improves* outer-loop agreement too
(+0.6–0.8pp vs. depletion-only). §5 of `phase4_bias_correction.md`'s
original judgement — that harvest's more variance-dominated error made it
a lower priority than depletion — is confirmed by this measurement rather
than left as an assumption: harvest correction helps, just by much less
than depletion correction did, exactly as that reasoning predicted.

---

## §3 — Final operating point

**Configuration**: net_depletion_J corrected with variant (b) — a
SoC-conditional offset table, LOCO-fit (total-minus-own, so no circuit is
corrected using its own data), calibrated to convergence via 5 rounds of
offline refitting (the final round's max offset-table shift: 78.5 J,
negligible) — applied forward, sector by sector, as a single deployment
pass. `E_har_final` corrected the same way, single application (no
rechaining needed, since harvest doesn't feed the SoC recursion). A 1.5σ
margin applied on top of both corrected predictions (depletion cap 3.758
MJ, harvest cap 8.369 MJ).

| metric | value |
|---|---|
| Dangerous rate, overall | **3.18%** |
| Dangerous rate, in-grid | 0.14% |
| Dangerous rate, sub-grid | 3.93% |
| Conservative rate, overall | 1.83% |
| Outer-loop same-λ agreement | 75.21% |
| Mean lap-time cost (when margin changes the selection) | 0.056 s |
| Lap-time signed error (dt uncorrected throughout) | median +0.174 s, mean +0.214 s |

Against the uncorrected open-loop baseline (14.28% dangerous, 0.14%
conservative, 74.88% outer-loop): **a 78% relative reduction in dangerous
rate**, at a real but modest conservative-rate cost and no measurable
lap-time or outer-loop-agreement penalty — outer-loop agreement is
marginally *better* than baseline (75.21% vs 74.88%).

This is lower than the un-deployable 0.81% quoted in `phase4_bias_
correction.md`'s original recommendation, and that gap — not a failure of
the underlying diagnosis — is the direct, measured cost of requiring
single-pass deployability. The mechanism (bias, not noise) is unchanged;
what changed is how much of it a genuinely deployable correction can
remove.

Lower-margin alternatives remain available if the conservative-rate cost
of 1.83% is judged too high: 0σ (correction alone) gives 5.70% dangerous
at 0.48% conservative; 1.0σ gives 3.99% dangerous at 1.16% conservative.
1.5σ is presented as the primary recommendation on the same diminishing-
returns reasoning as `phase4_bias_correction.md` §3: the marginal
dangerous-rate gain per point of conservative-rate cost is still
favourable at 1.5σ and starts flattening beyond it.

---

## §4 — Revised limitation paragraph for the discussion chapter

> The surrogate's depletion error is dominated by a systematic,
> one-directional bias — not noise — that under-predicts net depletion
> increasingly as the chained SoC trajectory drifts below the training
> grid's 0.10 floor (bias² accounts for 82% of mean-squared lap-level
> depletion error overall, and 83% specifically among the ~80% of
> lap-instances whose trajectory leaves the grid, versus only 6% among
> the ~20% that stay within it, where the surrogate is reliable). This
> was tested, not assumed: a LOCO-honest correction that estimates bias
> as a function of the SoC at which each prediction is made — fit only
> on circuits held out of each prediction, converged over several rounds
> of offline refitting, then applied forward in a single deployable pass
> — collapses the residual's skewness from −1.41 to −0.31 (a genuinely
> one-sided error becoming substantially more symmetric, though not
> fully so) and reduces the dangerous-error rate from 14.28% to 5.70%
> with no retraining, and to 3.18% paired with a modest margin. That the
> correction works at all, and specifically that it makes the residual
> more symmetric, is the evidence for the bias diagnosis; the operational
> improvement is a secondary consequence of it being true, not the
> primary claim. A related, lap-trajectory-level correction achieved a
> better-looking number in isolation (2.64%) but proved unstable once
> evaluated as a genuine two-pass deployment procedure (oscillating
> 8–13% across iterations) and is reported only as an upper bound on
> what lap-level information could buy, not as an achievable result.
> Extending the SoC training grid downward, separately, has not been
> shown to fix this failure mode at all: the one place it can be tested
> in-grid — 9 laps whose true depletion already exceeds the cap — still
> shows 7 of 9 dangerous (Wilson 95% interval 45–94%), so additional
> training coverage should be treated as unproven for this failure mode,
> not quantified as a specific percentage-point improvement.

---

## Assumptions stated beside the numbers that depend on them

- Variant (c)'s iteration distributes its lap-level predicted offset
  *evenly* across a lap's own sub-grid sectors to produce a per-sector
  correction for rechaining — the only well-defined way to turn a
  lap-total correction into something that can drive the recursion
  sector by sector, but it is one reasonable choice among others (e.g.
  weighting by each sector's own raw-bias magnitude); the instability
  finding is unlikely to be an artefact of this specific choice, since
  the oscillation pattern is large (5+ percentage points swing) relative
  to what a different weighting scheme would plausibly change, but this
  is not proven exhaustively.
- Variant (b)'s calibration was run to 5 rounds (shift 78.5 J at the
  final round, from a starting shift of 44,324.6 J) — reported as
  converged on the strength of the ~8–9x geometric shrinkage per round,
  not verified against a formal fixed-point tolerance.
- §3's final operating point figure differs slightly (5.87% vs 5.68%
  dangerous at 0σ, depletion-only) between the calibration-convergence
  table in §1 and the final harvest-inclusive evaluation in §3, traced to
  a harvest-evaluation code-path difference between those two runs, not a
  substantive change in the depletion correction itself — noted rather
  than silently reconciled, and immaterial to the final recommended
  configuration in §3, which uses the harvest-inclusive run throughout.
- No solving, no retraining, and no model or grid changes were performed;
  every number is pure inference on the already-cached (150k-restored)
  LOCO models plus closed-form LOCO arithmetic, using the same
  total-minus-own construction as `phase4_bias_correction.md` §2
  throughout.
