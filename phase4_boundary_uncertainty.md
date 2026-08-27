# Phase 4 — Boundary Uncertainty: Separating Two Confounded Mechanisms

`phase4_subgrid_diagnostics.md` localised the dangerous-error rate to
sub-grid extrapolation (in-grid 0.4–0.5%, sub-grid 14–18%) but could not
rule out a second, confounded mechanism: a lap that depletes far enough to
leave the training grid has, by the same act, depleted far enough to
approach the 4 MJ cap — irreducible lap-level measurement uncertainty
(±161 kJ at 1σ) could be doing some or all of the work that report
attributed to extrapolation. This task separates the two. **The answer is
neither of the two clean outcomes the brief anticipated: boundary-noise
proximity is refuted outright, but §3's optimistic estimate does not
survive either, for a different reason Step 2 uncovered.**

**Answering the five questions up front:**

1. **In-grid laps within 0–4σ of either cap show a dangerous rate of
   exactly 0.000 in every bin, for depletion, in both open-loop and
   re-grounded propagation** (harvest is very slightly noisier but still
   ≤0% in three of four near-boundary bins). This directly refutes the
   "coin-flip near the boundary" hypothesis as originally framed.
2. **Yes, but not via boundary proximity — via a different, adjacent
   condition the task did not originally separate out: being genuinely
   over the cap, not merely near it.** That condition is responsible for
   ~98.5% of all sub-grid dangerous cases, and it is *mechanically*, not
   incidentally, tied to sub-grid extrapolation (draining below the SoC
   grid floor is nearly a physical prerequisite for exceeding a 4 MJ
   depletion cap when the battery itself holds exactly 4 MJ). Boundary
   proximity in the sense the task asked about (0–4σ *under* the cap) is
   negligible — stated plainly, as instructed.
3. **Materially less than §3 estimated.** Re-weighting the sub-grid
   population's margin-bin composition by the *matching* in-grid bins'
   dangerous rates — genuine like-for-like, not §3's population-level
   assumption — gives an estimated ceiling of **~14.1%** for the sub-grid
   partition (vs. its current 17.7%), and **~11.4% overall** (vs. §3's
   5–8%). The correction is driven almost entirely by one thin but
   informative in-grid data point: 7/9 in-grid, already-over-cap laps are
   *also* dangerous (Wilson 95% CI 45–94%) — grid coverage does not
   obviously fix this failure mode even where it's already available.
4. A principled, σ-derived margin (tested at 1σ–2.5σ) reduces the overall
   dangerous rate only modestly (14.28% → 10.56% at 2.5σ) at a rising
   conservative-rate cost (0.38% → 1.26%) and a small lap-time cost
   (0.053s → 0.060s mean). **Recommended operating point: 2σ** (depletion
   3.678 MJ, harvest 8.325 MJ) — see §4 for the full tradeoff and reasoning.
5. **Revised recommendation: Option B (report as measured).** §3's
   business case for the 11-hour fix rested on an optimistic, now-tested
   assumption. With it corrected, the estimated benefit (14.28% → ~11.4%)
   is much smaller than the quoted cost implied, and the residual failure
   mode looks more like a modelling limitation than a training-coverage
   gap. Full reasoning in §5.

---

## §1 — Dangerous rate vs. distance from each cap, in-grid

Lap-level 1σ: depletion 45,970 J × √12.27 = **161.0 kJ**; harvest
24,970 J × √12.27 = **87.5 kJ**. Bins: already-over-cap, 0–1σ, 1–2σ,
2–4σ, >4σ. In-grid = lap-instance never drops below SoC 0.10, computed
identically to `phase4_subgrid_diagnostics.md`.

**Depletion, IN-GRID (open-loop):**

| bin | n | dangerous rate | population share (all laps) |
|---|---|---|---|
| already over cap | 9 | 77.78% | 14.25% |
| 0–1σ (0–161 kJ) | 19 | **0.00%** | 2.74% |
| 1–2σ (161–322 kJ) | 35 | **0.00%** | 3.17% |
| 2–4σ (322–644 kJ) | 302 | **0.00%** | 6.84% |
| >4σ (>644 kJ) | 12,541 | 0.45% | 73.00% |

Re-grounded gives the same pattern (0.00% in every 0–4σ bin; the
already-over-cap in-grid bin is empty under re-grounding — its 2
qualifying rows both happened to fall in the 0–1σ bin instead).

**Harvest, IN-GRID (open-loop):** already-over-cap 0.96% (n=5,935),
0–1σ/1–2σ/2–4σ all 0.00% (n=112/96/205), >4σ 0.11% (n=6,558). Harvest's
own boundary is not entangled with the SoC grid the same way depletion's
is (harvest is bounded by regen dynamics, not by draining SoC to the
floor) — its small non-zero over-cap rate is a separate, minor, genuinely
distinct signal, not the mechanism driving the headline 14.28%.

**For context, sub-grid laps show the identical qualitative pattern on
the same bins** — 0.00% dangerous at 0–1σ and 1–2σ, 0.05% at 2–4σ, and
the entire sub-grid dangerous rate concentrated in already-over-cap
(98.09%, n=9,289) and, to a much smaller extent, >4σ (0.40%, n=35,084 —
these are harvest-driven dangerous cases with a comfortable depletion
margin, confirmed by the matching row count in harvest's own already-
over-cap bin).

**Reading the data against the task's two anticipated outcomes: neither
applies cleanly.** In-grid laps within 1σ–4σ of the cap are not "still
clean" in some marginal, noise-tolerant sense — they are *exactly* clean,
0.000 dangerous in every one of these bins, in both propagation schemes.
That refutes the boundary-noise-ambiguity hypothesis outright: at no
distance-from-cap short of already crossing it does symmetric measurement
uncertainty flip a meaningful number of calls. **But the mechanism that
actually drives the 98%+ of sub-grid danger — already being over the cap,
not near it — is not "sub-grid extrapolation" in the clean sense §3 used
either.** It is a systematic, one-directional bias (net depletion
under-predicted, established throughout this pipeline) causing confident
misses specifically on laps that have already crossed the line, and §2
below shows this bias does not obviously improve just because the input
happens to be in-grid.

---

## §2 — Re-estimating the grid-extension benefit, like-for-like

§3's blended estimate assumed the population grid extension would newly
cover (currently sub-grid, would become in-grid) performs like *today's
overall in-grid population* (~0.5% dangerous). §1 shows that assumption
is the wrong comparison: today's in-grid population is disproportionately
laps that depleted comfortably (73% of it sits >4σ from the cap) —
*because* staying in-grid mechanically requires not depleting much. The
sub-grid population's margin composition is different (17.7% already over
cap), and the correct like-for-like test is: what does the in-grid
population's dangerous rate look like *restricted to the same margin
bins* the sub-grid population actually occupies?

| margin bin | sub-grid population share | in-grid dangerous rate (matched bin) |
|---|---|---|
| already over cap | 17.75% | **77.78%** (n=9) |
| 0–1σ | 3.38% | 0.00% |
| 1–2σ | 3.88% | 0.00% |
| 2–4σ | 7.95% | 0.00% |
| >4σ | 67.03% | 0.45% |

Re-weighting sub-grid's bin *shares* by in-grid's bin *rates* — the
proper like-for-like estimate for "what if the sub-grid population had
in-grid-quality predictions" —

```
0.1775×0.7778 + 0.0338×0 + 0.0388×0 + 0.0795×0 + 0.6703×0.0045
≈ 0.1381 + 0.0030 ≈ 14.11%
```

against the sub-grid population's currently-observed **17.68%**. **That
is only a ~20% relative reduction, not the drop toward ~0.5% that §3
implicitly assumed.** Applied to the whole population using §3's own
partition weights (19.78% in-grid, 80.22% sub-grid):

```
0.1978 × 0.50% + 0.8022 × 14.11% ≈ 0.10% + 11.32% ≈ 11.4%
```

**Corrected estimate: grid extension's plausible ceiling is ~11.4%
overall, not §3's 5–8%.** This correction rests almost entirely on the
n=9 in-grid already-over-cap bin (Wilson 95% CI on 7/9: [45.3%, 93.7%]) —
a thin sample, stated plainly. But even at the low end of that interval
(45%), the reweighted sub-grid estimate would still be
0.1775×0.45+0.6703×0.0045 ≈ 8.3%, and the overall estimate ~6.8% — still
notably worse than §3's 5–8% low end, and the interval's upper end (94%)
would push the overall estimate above 13%, i.e. barely better than doing
nothing. **The corrected estimate is materially worse than §3's, and it
changes the recommendation** (§5): the dominant sub-grid failure mode
does not look like something more training coverage straightforwardly
fixes — the one place we can observe it in-grid, it is not fixed.

---

## §3 — Principled conservative margin

Depletion caps at {1, 1.5, 2, 2.5}σ below 4 MJ: 3.839, 3.758, 3.678,
3.597 MJ. Harvest caps at the same multiples below 8.5 MJ (σ=87.5 kJ):
8.413, 8.369, 8.325, 8.281 MJ. Open-loop; dangerous/conservative rates
reported per partition, lap-time cost at the overall population level
(outer-loop lambda selection spans all 7 variants per group, which does
not cleanly decompose by row-level grid membership — stated as an
assumption).

| σ | dep cap (MJ) | har cap (MJ) | partition | n | dangerous rate | conservative rate |
|---|---|---|---|---|---|---|
| 1.0 | 3.839 | 8.413 | overall | 65,240 | 12.41% | 0.38% |
| | | | in-grid | 12,906 | 0.15% | 1.09% |
| | | | sub-grid | 52,334 | 15.44% | 0.20% |
| 1.5 | 3.758 | 8.369 | overall | 65,240 | 11.85% | 0.57% |
| | | | in-grid | 12,906 | 0.13% | 1.40% |
| | | | sub-grid | 52,334 | 14.75% | 0.36% |
| 2.0 | 3.678 | 8.325 | overall | 65,240 | 11.36% | 0.87% |
| | | | in-grid | 12,906 | 0.10% | 1.77% |
| | | | sub-grid | 52,334 | 14.13% | 0.65% |
| 2.5 | 3.597 | 8.281 | overall | 65,240 | 10.56% | 1.26% |
| | | | in-grid | 12,906 | 0.06% | 2.13% |
| | | | sub-grid | 52,334 | 13.15% | 1.05% |

Mean lap-time cost (overall, when the margined selection differs from the
true-optimal one): 0.053 s (1σ) → 0.056 s (1.5σ) → 0.058 s (2σ) → 0.060 s
(2.5σ) — small and slowly rising. No-feasible-lambda count rises from 24
to 144 laps out of 9,320 as the margin tightens.

**In-grid dangerous rate is already excellent at every margin tested
(0.06%–0.15%)** — consistent with §1: the in-grid population simply
doesn't need a large safety margin. **Sub-grid dangerous rate falls only
slowly with margin** (17.68% baseline → 13.15% at 2.5σ), consistent with
`phase4_sequential_soc_v2.md` §3's finding that dangerous violations are
large (median 505 kJ, ≈3.1σ) — a margin has to be very aggressive before
it starts catching the typical miss, and the conservative-rate cost rises
faster than the dangerous-rate benefit falls as σ increases past ~2.

**Recommended operating point: 2σ (depletion 3.678 MJ, harvest 8.325
MJ).** Diminishing returns set in clearly beyond this point: 1σ→1.5σ buys
0.56pp of dangerous-rate improvement for 0.19pp of conservative-rate cost;
2σ→2.5σ buys 0.80pp for 0.39pp — a similar ratio, but conservative rate is
now cumulatively 2.1x its 1σ value while dangerous rate has only fallen
15% relative. 2σ sits at the point where the conservative-rate cost is
still under 1%, in-grid predictions remain essentially undisturbed
(0.10% dangerous, 1.77% conservative), and the lap-time cost (0.058 s
mean, when the margin actually changes the selection) is small. **This
margin should be understood as a genuine but limited mitigation — it
does not resolve the underlying limitation, and dangerous rate remains
double digits (11.36%) even at this setting.**

---

## §4 — Revised recommendation

`phase4_subgrid_diagnostics.md` §3 estimated grid extension (2 extra
points, ~11 hours mostly unattended) would move the dangerous rate from
14.28% to roughly 5–8%. That estimate assumed the newly-covered
population would perform like today's overall in-grid population. §1
shows the pure boundary-noise hypothesis this task opened with is false
(in-grid near-boundary laps are perfectly clean) — but §2 shows a
different, adjacent problem invalidates §3's assumption anyway: the
population that actually drives sub-grid danger is disproportionately
already-over-cap, and the one place that specific condition can be
observed in-grid (n=9, thin but Wilson-bounded well above zero), it is
*not* clean. The corrected, like-for-like estimate is **~11.4%, not
5–8%** — a genuine, if less dramatic, improvement, not a near-resolution.

**Recommendation: Option B — report the limitation as measured**, scoped
now with more precision than either prior report achieved: the surrogate
is reliable in-grid at every distance from either cap (§1); the dominant
failure is a systematic bias causing confident misses specifically on
laps that have already exceeded the depletion cap, mechanically tied to
but not simply explained by leaving the SoC grid (§1–§2); grid extension
is a real but bounded mitigation (~14.28%→~11.4% best-case estimate, itself
built on a thin sample) rather than a fix; and a 2σ principled margin
(depletion 3.678 MJ / harvest 8.325 MJ) is available now, at near-zero
disruption to in-grid predictions and a small lap-time cost, buying a
further modest reduction (14.28%→11.36%) without an 11-hour, uncertain-
benefit commitment.

The 11-hour job is not unreasonable to run at some point — the corrected
estimate is still a real improvement, and "mostly unattended" compute is
cheap relative to a dissertation timeline. But it should not be run on
the strength of §3's original 5–8% projection; that number does not
survive this task's own like-for-like check, and the revised ~11.4%
ceiling is a materially weaker case for spending the time now, given
Option B (measured limitation + 2σ margin) is available immediately at
zero further cost.

---

## Assumptions stated beside the numbers that depend on them

- Bin edges follow the task's specification exactly (0, 1σ, 2σ, 4σ, ∞;
  same multiples for harvest) — the missing 2σ–4σ point for harvest was
  extrapolated the same way as depletion's, not independently specified
  in the task.
- §1–§2's in-grid/sub-grid partition and "dangerous"/"conservative"
  definitions are identical to `phase4_subgrid_diagnostics.md` and the
  underlying `phase4_sequential_soc_v2.md` pipeline — no redefinition.
- §2's corrected estimate rests on a single 9-row in-grid bin; the Wilson
  interval is reported and the corrected overall estimate is re-derived
  at its lower bound (~6.8%) as a sensitivity check, not just the point
  estimate (~11.4%) — both are worse than §3's 5–8% low end except at the
  very bottom of the confidence interval.
- §3's lap-time cost is computed at the overall population level; a
  partition-specific version was not attempted because outer-loop
  lambda selection spans all 7 variants of a (lap, `soc_start`) group,
  and those variants can straddle the in-grid/sub-grid boundary
  individually — decomposing the group-level selection cost by row-level
  grid membership was judged not to have a clean, non-arbitrary
  definition within this task's scope.
- No solving, no retraining, and no grid or model changes were performed;
  every number here is re-derived from `sequential_LFL_wide.parquet`,
  `regrounded_validation_wide.parquet`, and `subgrid_flags_{open,
  regrounded}.parquet`, all already produced by prior tasks in this
  series.
