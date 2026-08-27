# Phase 4 — Sub-Grid Diagnostics: Is the 11-Hour Fix Worth Running?

`phase4_offgrid_probe.md` sharpened "covariate shift" into a specific
design-gap claim: the SoC training grid's floor (0.10) does not cover the
operating range, and 34.2% of all chained per-sector predictions land
below it. Two cheap diagnostics on the existing sequential-chain results —
no solving, no retraining — decide whether extending the grid downward and
retraining (an ~11-hour, mostly-unattended job) is worth running.
**Answer: the mechanism is confirmed and precisely localized, but
Diagnostic 2 overturns the "not operationally relevant" framing this task
opened with — the failure concentrates at the HIGH starting-SoC states a
real qualifying lap actually begins at, not at unrealistic low ones.**

**Answering the three questions up front:**

1. **In-grid dangerous rate is 0.50% (open-loop) / 0.42% (re-grounded) —
   low single digits, as the decision criterion required.** Sub-grid
   dangerous rate is 17.68% / 14.07%. The surrogate is reliable within its
   training envelope; the headline 14.28% is dominated by extrapolation
   beyond it, in both propagation schemes.
2. **No — the opposite.** Dangerous rate rises monotonically from 2.47% at
   `soc_start=0.1` to 44.47% at `soc_start=1.0`; 55.4% of all dangerous
   cases come from `soc_start ∈ {0.9, 1.0}` alone. Since a real qualifying
   lap begins charged (high SoC), essentially none of the 14.28% comes
   from starting states that "would not occur" — if anything, the
   low-`soc_start` states are the less realistic ones, and they contribute
   only 3.46% of the dangerous count (`soc_start ∈ {0.1, 0.2}`).
3. **Moderately favours Option A, with a specific, hedged estimate:
   extending to two points (0.02, 0.05) plausibly moves the dangerous rate
   to roughly 5–8%, not down to the ~0.5% in-grid baseline** — because a
   meaningful share of currently-sub-grid predictions sit below even a
   0.02 floor. Reasoning and the arithmetic behind that estimate in §3.

---

## §1 — In-grid vs sub-grid partition (Diagnostic 1)

Reconstructed entirely from already-computed artefacts — `sequential_soc_
visited.npy` (the restored-150k-model open-loop trajectory, split back
into per-lap blocks using each lap's own sector count) for the open-loop
partition, and a cheap re-derivation of the TRUE-depletion-chained SoC
trajectory (dict lookups only, no model calls, no solving) for the
re-grounded partition. A lap-instance is "sub-grid" if its chained SoC
ever drops below 0.10 at any sector.

**The split:** open-loop 19.78% in-grid / 80.22% sub-grid (12,906 /
52,334 of 65,240); re-grounded 20.21% / 79.79% (13,188 / 52,052) —
essentially identical between the two schemes, confirming this is a
property of the real depletion trajectories, not an open-loop artefact.

| | OPEN-LOOP in-grid | OPEN-LOOP sub-grid | RE-GROUNDED in-grid | RE-GROUNDED sub-grid |
|---|---|---|---|---|
| n | 12,906 | 52,334 | 13,188 | 52,052 |
| Dangerous rate | **0.50%** | **17.68%** | **0.42%** | **14.07%** |
| Conservative rate | 0.56% | 0.04% | 0.46% | 0.06% |
| Lap-time error, median | −0.048 s | +0.237 s | −0.050 s | +0.399 s |
| Lap-time error, p95 | 0.401 s | 1.107 s | 0.406 s | 1.463 s |
| Lap-time error, mean | −0.065 s | +0.282 s | −0.062 s | +0.467 s |
| within ±0.05 s | 14.55% | 9.14% | 14.32% | 7.11% |
| within ±0.2 s | 54.55% | 35.01% | 54.41% | 26.41% |
| within ±0.5 s | 89.66% | 72.41% | 89.97% | 56.06% |

**This is the number that decides the fix, and it comes back decisively in
favour of the training envelope being sound: in-grid dangerous rate is
0.4–0.5% in both propagation schemes — low single digits by a wide
margin.** The 14.28% headline is a population-weighted blend of a reliable
19.8–20.2% in-grid slice and a genuinely unreliable 79.8–80.2% sub-grid
slice (consistency check: 0.1978×0.50% + 0.8022×17.68% = 14.27%, matching
the reported 14.28% within rounding).

**Outer-loop same-lambda agreement**, at the (lap, `soc_start`) GROUP
level (a group classified "sub-grid" if *any* of its 7 lambda variants
ever goes sub-grid — stated as an explicit assumption, since almost every
group has at least one such variant, leaving the "in-grid group" sample
very small, n=63–68):

| | in-grid groups | sub-grid groups |
|---|---|---|
| OPEN-LOOP | 39.71% (n=68) | 75.14% (n=9,136) |
| RE-GROUNDED | 41.27% (n=63) | 80.03% (n=9,192) |

The in-grid-group sample is too small (63–68) to draw a firm conclusion
from directly — noted rather than over-interpreted. The large, well-
powered sub-grid-group figures (75–80% agreement) are consistent with
§5 of the offgrid-probe report.

---

## §2 — Breakdown by starting SoC (Diagnostic 2)

| soc_start | n | dangerous rate | dangerous share | frac. ever sub-grid | median first-cross sector | true-infeasible rate | dangerous / true-infeasible |
|---|---|---|---|---|---|---|---|
| 0.1 | 6,524 | 2.47% | 1.73% | 93.58% | 1 | 12.31% | 20.05% |
| 0.2 | 6,524 | 2.47% | 1.73% | 88.04% | 1 | 12.91% | 19.12% |
| 0.3 | 6,524 | 3.23% | 2.26% | 85.12% | 2 | 14.09% | 22.96% |
| 0.4 | 6,524 | 4.46% | 3.12% | 81.50% | 3 | 15.31% | 29.13% |
| 0.5 | 6,524 | 5.98% | 4.19% | 80.13% | 3 | 16.78% | 35.62% |
| 0.6 | 6,524 | 8.29% | 5.81% | 79.52% | 4 | 19.13% | 43.35% |
| 0.7 | 6,524 | 13.90% | 9.73% | 77.56% | 5 | 24.83% | 55.99% |
| 0.8 | 6,524 | 22.93% | 16.05% | 75.15% | 6 | 33.89% | 67.66% |
| 0.9 | 6,524 | 34.63% | 24.24% | 72.26% | 6 | 45.59% | 75.96% |
| 1.0 | 6,524 | 44.47% | 31.13% | 69.31% | 7 | 57.60% | 77.20% |

**The failure does NOT concentrate at low `soc_start`. It concentrates at
high `soc_start` — the opposite of this task's opening hypothesis, stated
plainly per instruction.** Dangerous rate rises monotonically and
steeply (2.47% → 44.47%), even as the *fraction of laps that ever go
sub-grid* falls monotonically (93.6% → 69.3%) — a genuine, initially
counter-intuitive dissociation. Two further columns explain it: true
infeasibility rate itself rises sharply with `soc_start` (12.3% → 57.6%
— mechanically expected, since the battery capacity and the depletion cap
are both 4 MJ, so a fuller starting charge gives the optimal controller
more room to legitimately approach or exceed the cap), and the
*conditional* dangerous rate — dangerous cases as a fraction of genuinely
infeasible ones — also rises sharply (20.1% → 77.2%): even restricted to
laps that truly are infeasible, the model's miss rate is far higher when
`soc_start` is high.

**Decomposing this trend by in-grid/sub-grid membership resolves it
completely** (same computation as §1, now sliced by `soc_start`):

| soc_start | in-grid dangerous rate (open-loop) | sub-grid dangerous rate (open-loop) | in-grid dangerous rate (regrounded) | sub-grid dangerous rate (regrounded) |
|---|---|---|---|---|
| 0.1 | 0.95% | 2.57% | 0.95% | 2.59% |
| 0.3 | 0.21% | 3.76% | 0.22% | 3.07% |
| 0.5 | 0.85% | 7.25% | 0.86% | 5.09% |
| 0.7 | 0.48% | 17.79% | 0.59% | 11.86% |
| 0.9 | 0.17% | 47.86% | 0.10% | 36.17% |
| 1.0 | 0.50% | 63.93% | 0.24% | 59.62% |

**In-grid dangerous rate is flat and low (0.10%–0.95%) across the ENTIRE
`soc_start` range, in BOTH propagation schemes.** The entire `soc_start`
trend lives in the sub-grid partition, rising from ~2.6% at `soc_start=0.1`
to 60–64% at `soc_start=1.0`. The mechanism: a lap starting at 1.0 that
still manages to reach sub-grid territory has depleted close to the *full*
4 MJ battery — mechanically near or over the 4 MJ cap already — and the
model has had many more in-grid sectors over which its own small,
persistent bias (§0 of the offgrid-probe report: +10 kJ to −11 kJ across
the covered interior) could accumulate before the trajectory ever reaches
the region where its error becomes severe. This holds under re-grounding
too, which rules out compounding as the explanation for the `soc_start`
trend itself — it is a property of *how far into the depletion range* the
lap has travelled, not of open-loop error feedback.

**This directly corroborates the asymmetry flagged in the task: open-loop
SoC is biased high (depletion under-predicted), which keeps the
trajectory nearer the well-covered part of the grid for longer — visible
here as the open-loop sub-grid rate at every `soc_start` sitting at or
above the re-grounded figure (e.g. 63.93% vs 59.62% at `soc_start=1.0`),
because open-loop's optimistic bias delays, but does not prevent, the
eventual crossing into sub-grid territory, and the resulting dangerous
error is if anything a shade worse for having been delayed.**

**Fraction of the headline 14.28% from starting states that would not
occur in a real qualifying lap:** the task's premise was that low
`soc_start` might be the culprit and could be scoped away as an artefact
of the modelling grid rather than a real limitation. The data says the
opposite: `soc_start ∈ {0.1, 0.2}` together contribute only **3.46%** of
the dangerous count, while `soc_start ∈ {0.8, 0.9, 1.0}` — precisely the
charged, operationally-realistic starting states — contribute **71.42%**.
**Essentially none of the 14.28% can be dismissed as an unrealistic
scenario; if anything, restricting to only the realistic high-`soc_start`
band would show the problem is worse, not smaller, as a fraction of the
laps that actually matter.**

One further dissociation worth flagging plainly: lap-time signed error
(open-loop) moves in the *opposite* direction from dangerous rate across
`soc_start` — median error falls from +0.290 s at `soc_start=0.1` to
+0.074 s at `soc_start=1.0`. Feasibility-classification failure and
point-forecast lap-time error are not the same failure and do not track
each other across `soc_start`; a fix aimed at one should not be assumed to
help the other.

---

## §3 — Recommendation: extend the grid, or report as measured?

**The mechanism is now precisely localized**: reliable in-grid (0.4–0.5%
dangerous, flat across the whole `soc_start` range, in both propagation
schemes), unreliable and `soc_start`-dependent sub-grid (2.6%–64%), driven
by depth of depletion rather than compounding. **And it is not scopeable
away**: the failure hits hardest exactly where a real qualifying lap
starts. Both of these push toward Option A being worth serious
consideration — a materially different conclusion than if the failure had
concentrated at unrealistic low-`soc_start` states as originally
hypothesized.

**But the benefit of the quoted 2-extra-point option (0.02, 0.05, ~11
hours) is bounded, and should be stated as an estimate, not a promise.**
From `step0_bias_vs_soc.parquet`'s full sub-grid population (267,541
per-sector predictions currently below 0.10): extending the floor to 0.02
would newly cover **68.3%** of that population (median/mean of the
sub-grid distribution, 0.037/0.042, sit comfortably above 0.02), but
**31.7% would remain below even a 0.02 floor** — still genuinely
extrapolating after the fix. A blended estimate, assuming the
newly-covered 68.3% would perform like the currently-observed in-grid
rate (~0.5%) and the remaining 31.7% of the sub-grid population keeps
something like its current elevated rate (~17.7%, unchanged as a
conservative assumption):

```
new sub-grid-weighted rate ≈ 0.8022 × (0.683 × 0.5% + 0.317 × 17.68%)
                            ≈ 0.8022 × (0.34% + 5.60%)
                            ≈ 0.8022 × 5.94% ≈ 4.77%
new overall rate ≈ 0.1978 × 0.50% + 4.77% ≈ 5.1%
```

**Estimate: the 2-extra-point option (0.02, 0.05) plausibly moves the
dangerous rate from 14.28% to roughly 5–8%** (the arithmetic above; the
range acknowledges that the "newly-covered performs like current in-grid"
assumption is a plausibility argument, not a measurement — the actual
model, retrained with two new grid points, could do better or worse than
today's in-grid figure). This is **not** the "low single digits" bar this
task's own Diagnostic 1 used as the go/no-go criterion for the fix as a
whole — it is a real, roughly 60–65% reduction, not a resolution. A third,
deeper point (the quoted 8.2 h / 3-value option) would be needed to close
most of the remaining 31.7% residual and approach the ~0.5–1% in-grid
baseline more closely; the 2-value, ~11-hour option quoted in this task's
brief should not be expected to get there on its own.

Two further considerations bound the estimate from below, independent of
grid extension: `phase4_offgrid_probe.md` §2 found the comparator's own
off-grid error is comparable to or larger than the model's, and beats the
model head-to-head 75–90% of the time — so some of the residual dangerous
rate reflects comparator imprecision that grid extension cannot fix at
all, at any floor.

**Recommendation: the diagnostics moderately favour Option A, but with an
explicit ceiling on what it buys.** The mechanism is real, well-localized,
non-compounding, and hits the operationally relevant regime hardest —
that case is stronger than the task's opening framing suggested, and
strong enough to justify the ~11 hours of *mostly unattended* compute if a
~60–65% reduction (14.28% → ~5–8%) is worth having. It is explicitly not
strong enough to promise the fix resolves the limitation to the in-grid
baseline (~0.5–1%) — that would need the deeper, more expensive 3-value
option, un-costed beyond its 8.2-hour solve component in this task's
brief. **If the dissertation's timeline or scope favours the conservative
path, Option B — report the measured 14.28%, scoped precisely by this
report's in-grid/sub-grid and `soc_start` breakdowns, with grid extension
named as costed further work — is equally defensible and does not require
running an unverified 11-hour job this task was explicitly told not to
execute.**

---

## Assumptions stated beside the numbers that depend on them

- "In-grid" / "sub-grid" is defined at the level of a full lap-instance
  trajectory (any sector, any point, below 0.10) — a single sector's dip
  classifies the whole (lap, `soc_start`, λ) instance as sub-grid, even if
  most of its sectors are comfortably in-grid.
- The re-grounded partition's SoC trajectory was re-derived fresh for this
  report (dict lookups against the same interpolated-true label
  cache already built for `phase4_sequential_soc_v2.md`) — it was not
  previously saved to disk, but required no model calls and no solving.
- The outer-loop group-level in-grid/sub-grid split classifies a whole
  7-lambda group as sub-grid if *any* one of its variants ever crosses —
  this leaves a very small (n=63–68) in-grid-group sample, flagged rather
  than treated as conclusive.
- §3's blended estimate assumes grid-extended in-grid performance would
  match today's already-observed in-grid rate — a plausibility argument
  from the pattern in §1–§2, not a measurement of the retrained model this
  task was explicitly told not to build.
- No solving and no retraining were performed for this report; all
  numbers are re-derived from `sequential_soc_visited.npy`,
  `sequential_LFL_wide.parquet`, `regrounded_validation_wide.parquet`, and
  `step0_bias_vs_soc.parquet`, all already produced by prior tasks in this
  series.
