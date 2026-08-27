# v3 OCP — lambda-bracket re-validation (targeted re-solve)

Corrects two conclusions from `output/smoke_v3_truncation_analysis.md` via a
targeted re-solve of the same 200-instance pool. **10,000 new solves, 100%
converged, 26.7 min wall clock, 8 workers.** Full batch not run.

New files: `smoke_v3_bracket_revalidation_solves.parquet` (10,000 label rows),
`smoke_v3_bracket_revalidation_realloc_diag.parquet` (raw-vs-canonical
diagnostic), `smoke_v3_reval_synthetic_laps_{12,13,merged}.parquet`,
`smoke_v3_reval_synthetic_lap_harvest_12.parquet`.

---

## Step 0 — E_har provenance

**The prior truncation analysis already used the correct quantity.** Verified
directly from `dynamics.py`: `dE_har_ds = F_reg * eta_regen` — this is the
DC-bus state (`E_har_final` in the parquet), and it's what `trunc_06_lap_harvest.py`
summed for the earlier (now-superseded-by-sector-count) harvest check.
`E_harvest_optimal` is the older wheel-mechanical extraction.

**Consistency-check ratio does NOT cleanly show eta_regen=0.95** — median
`E_harvest_optimal / E_har_final` = 0.998, not 1/0.95=1.053. This is not an
error in either quantity; it's because they're computed from **different
force allocations**, not just different efficiency scalings of the same one:
`E_harvest_optimal` uses the **canonically-reallocated** `F_canon` split,
while `E_har_final` uses the **raw** solved `F_reg` (the actual v3 state,
integrated during the solve). Splitting the sample by reallocation-delta
size did not resolve the ratio toward 1.053 either — confirming the
confound is real, not a subsample artifact. **This directly foreshadows
Step 4's finding:** raw and canonical F_reg differ substantially and
systematically, so a clean efficiency-only ratio was never going to appear.

---

## Step 1 — Targeted re-solve

Re-solved 200 instances × 10 SoC × 5 new lambda values
`[1.00e-8, 2.34e-8, 5.48e-8, 1.28e-7, 3.00e-7]`, parallelised across
**(instance, SoC) pairs** (2000 tasks, each an independent 5-step warm-start
chain along lambda only, cold-started at the chain's own first lambda — no
SoC-to-SoC or cross-pair warm start). 8 workers. **10,000/10,000 converged
(100%)** — a marked improvement over both the original 7-point bracket
(99.6%) and the previously truncated [1e-9,1e-7] bracket (99.98%).

**Overlap correction:** only **one** of the 5 new values exactly matches the
original 7-point grid (1.00e-8) — not two, as stated in the task. None of
the other four (2.34e-8, 5.48e-8, 1.28e-7, 3.00e-7) coincide with old grid
points; they're new interpolation points by design. Flagging this rather
than inventing a second overlap.

### Determinism / worker-count check: **PASSED**

Spot-checked 30 (instance, SoC) pairs (150 solves) by re-solving them
**serially** (no multiprocessing at all) and diffing against the same pairs'
results from the 8-worker main run. **Zero mismatches** on `E_har_final`,
`E_final`, `dt_optimal`, `ocp_converged` across all 150 solves. Worker count
and scheduling order do not affect results — the pair-scoped chain design
has no state leakage. **Not a reproducibility defect.**

### Overlap check at lambda=1.00e-8: reveals warm-start path-dependence directly

Comparing the SAME (instance, SoC, lambda=1e-8) triple between this run
(cold-started, first lambda of a fresh 5-point chain) and the original smoke
run (warm-started from the converged lambda=1e-9 solve in a 7-point chain):

| field | max\|diff\| | median\|diff\| | n differing >1e-3 (of 2000) |
|---|---|---|---|
| E_har_final | 652,945 J | 2,511 J | 1997 (99.85%) |
| E_final | 1,061,394 J | 828 J | 1980 (99.0%) |
| dt_optimal | 2.794 s | 0.000015 s | 53 (2.65%) |

This is **not** a determinism bug (the spot-check above rules that out) — it's
**direct, controlled evidence** that IPOPT's landing point genuinely depends
on warm-start history, even at a fixed (instance, SoC, lambda). Median
differences are modest (path-dependence is usually small), but the tails are
enormous (650 kJ, 1.06 MJ, nearly 3 s of dt) — almost certainly the same
degenerate-tie cases already implicated in finding 5. This is the clearest
evidence yet for the underlying mechanism, independent of any particular
lambda value.

---

## Step 2 — Lap-level monotonicity, corrected

**Sampling scheme restated (unchanged from the prior analysis):** no GP in
the 200-instance pool has ≥20 instances, so true within-circuit sampling was
already shown infeasible; still sampling 12 (or 13) distinct instances
without replacement from the full 200-instance pool, mixing circuits. Same
limitation as before — a synthetic lap tests whether summing independent
micro-sector responses cancels noise, not a specific real circuit's lap.

| test | (lap,SoC) monotone | lap-level (all SoC) monotone | worst reversal |
|---|---|---|---|
| new grid only, 12 sectors (4 steps) | **95.43%** (457/10000 violate) | 72.8% | 1,214,706 J = 0.304 of 4MJ window |
| new grid only, 13 sectors (sensitivity) | 96.32% (368/10000) | 75.7% | 1,578,262 J = 0.395 of window |
| merged grid incl. old 1e-9, 12 sectors (5 steps) | 87.95% (1198/9944) | 47.8% | 5,228,702 J = **1.307× window** |

**Violation step location:**

| step | new-grid-only (12 sec) | merged grid (12 sec) |
|---|---|---|
| 1e-9 → 1e-8 | *(not in this grid)* | **782** (65% of merged violations) |
| 1e-8 → 2.34e-8 | 69 | 69 |
| 2.34e-8 → 5.48e-8 | **386 (84% of new-grid violations)** | 345 |
| 5.48e-8 → 1.28e-7 | 2 | 2 |
| 1.28e-7 → 3e-7 | 0 | 0 |

### Hypothesis (a) — **partially confirmed, not fully**

The merged-grid test confirms lambda=1e-9 is the single largest contributor
(782/1198 = 65% of merged-grid violations sit at that one step), and dropping
it substantially improves the picture (combo-monotone rises from 87.95% to
95.43%, worst reversal drops from 1.31× the window to 0.30×). **But it does
not explain everything.** A second, distinct, and dominant violation cluster
sits at **2.34e-8 → 5.48e-8**, entirely inside the new bracket, unrelated to
the old epsilon-anchored point (386 violations there vs. 69 at the
first new-grid step). The 13-sector sensitivity reproduces the same pattern
(327 violations at the same step). **Truncating below 1e-9 removes most, but
not all, of the non-monotonicity — a real residual degeneracy persists
within [1e-8, 3e-7].**

---

## Step 3 — Lap harvest vs the 8.5 MJ cap (corrected sector count: 12)

Using the confirmed DC-bus `E_har_final`, 12 sectors/lap (same sampling
scheme, same seed as Step 2):

| lambda | median (MJ) | p95 (MJ) | max (MJ) | frac over 8.5 MJ cap |
|---|---|---|---|---|
| 1.00e-8 | 4.53 | 5.98 | 7.02 | **0.00%** |
| 2.34e-8 | 4.78 | 6.23 | 7.33 | **0.00%** |
| 5.48e-8 | 5.33 | 6.85 | 7.95 | **0.00%** |
| 1.28e-7 | 6.61 | 8.25 | 9.58 | **2.59%** (259/10000) |
| 3.00e-7 | 9.17 | 11.43 | 13.43 | **68.75%** (6875/10000) |

**The cap does not bind anywhere from 1e-8 through 5.48e-8** — clean, 0% over
cap at all three of the lowest tested points, confirming the prior naive
20-sector estimate was indeed the artifact the task's framing suspected.
**It starts binding between 5.48e-8 and 1.28e-7**, and is severely binding by
3e-7 (median already 8% over cap, over two-thirds of laps breach it).

**Coverage caveat restated, not resolved:** micro-sector coverage fraction of
total lap distance is still unverified. Harvest concentrates in braking
zones, which apex-to-apex sectors terminate in by construction, so coverage
of *harvest* specifically is plausibly better than coverage of *distance* —
but this is a plausibility argument, not something checked here. If coverage
is incomplete, true lap harvest could exceed what's modelled, which would
push the safe lambda ceiling below what Step 3 shows, not above it.

---

## Step 4 — Is the canonical reallocation still doing anything? **Yes — it remains highly active.**

Captured as a byproduct of Step 1 (no extra re-solving): for every solve,
independently recomputed the canonical split via the unmodified
`_canonical_energy_reallocation` and compared to the raw solved F_reg.
Cross-check: independently-recomputed `E_final_canon` matches solver.py's own
internal value to **exactly 0.0** across all 10,000 solves — confirms the
diagnostic capture is correct.

| lambda | \|delta_E_har\| median (J) | \|delta_E_har\| p90 (J) | mean frac intervals differing | median peak force diff (N) |
|---|---|---|---|---|
| 1.00e-8 | 31,052 | 86,956 | 99.3% | 1,476 |
| 2.34e-8 | 36,034 | 72,384 | 99.4% | 771 |
| 5.48e-8 | 36,190 | 63,882 | 99.4% | 589 |
| 1.28e-7 | 35,100 | 61,040 | 99.4% | 481 |
| 3.00e-7 | 42,605 | 78,794 | 99.7% | 466 |

- **100%** of the 10,000 solves have at least one interval where raw ≠
  canonical F_reg; **99.98%** exceed the codebase's own G4 energy-determinism
  tolerance (2,000 J) in aggregate.
- **The aggregate energy effect (|delta_E_har|) does NOT shrink monotonically
  with lambda** — sequence is 31.1k → 36.0k → 36.2k → 35.1k → 42.6k J,
  essentially flat with a slight rise at the top, not the "price breaks the
  degeneracy" pattern the hypothesis predicted.
- The **peak per-interval force difference** does shrink with lambda
  (1,476 N → 466 N) — some evidence the price sharpens individual decisions —
  but this doesn't translate into a shrinking aggregate, because the
  *fraction* of intervals affected stays ~99%+ throughout (even ticking up
  slightly at the top).

**Conclusion: the hypothesis that a strictly-positive lambda makes the
reallocation redundant is not supported in this range.** It remains
load-bearing — doing real, tens-of-kJ-scale work on essentially every solve,
uniformly across [1e-8, 3e-7], not fading out as price rises.

---

## Step 5 — P_deploy spread across the bracket: **stays compressed throughout**

Percentiles as a fraction of the 332.5 kW wheel-equivalent ceiling:

| lambda | p10 | p25 | p50 | p75 | p90 | p95 | IQR width (pts) | never-deploy |
|---|---|---|---|---|---|---|---|---|
| 1.00e-8 | 62.6% | 82.2% | 91.6% | 97.1% | 98.4% | 98.7% | 14.8 | 0.55% |
| 2.34e-8 | 62.6% | 82.3% | 91.7% | 97.1% | 98.4% | 98.7% | 14.8 | 1.30% |
| 5.48e-8 | 62.6% | 82.2% | 92.0% | 97.3% | 98.4% | 98.8% | 15.2 | 0.85% |
| 1.28e-7 | 64.7% | 81.2% | 92.0% | 96.4% | 97.9% | 98.6% | 15.2 | 1.80% |
| 3.00e-7 | 65.6% | 79.4% | 88.9% | 93.5% | 95.9% | 96.6% | 14.1 | 2.70% |

**The spread does not open up.** IQR width is flat at 14.1–15.2 percentage
points across the entire tested bracket; p75 and above sit within 1–7% of
saturation at *every* lambda tested, not just at the original lambda=1e-9
point. `never_deploy` climbs modestly (0.55%→2.70%) but the bulk of the
distribution stays compressed near the physical ceiling throughout.
**P_deploy has limited variance for regression purposes across this whole
bracket** — target compression is a property of the bracket, not an artifact
of the old floor.

---

## Recommendation

**Final [lambda_min, lambda_max] and N_lambda.** Recommend **lambda_min =
1e-8** (not 1e-9) — supported both by the merged-grid monotonicity test
(removing 1e-9 eliminates 65% of violations) and by the overlap-check
experiment (direct evidence the calibrated-epsilon point is where warm-start
path-dependence is most extreme). For lambda_max, **the harvest-clean and
monotonicity-clean zones do not fully overlap** — flagging this rather than
reconciling it:
- Harvest is clean (0% over cap) through **5.48e-8**, starts breaching at
  1.28e-7, severely breaches by 3e-7.
- The **dominant remaining monotonicity violation cluster (386/457, 84% of
  new-grid violations) sits at exactly 2.34e-8 → 5.48e-8** — inside the
  harvest-safe zone.

There is no bracket within what's been tested that is simultaneously
harvest-safe AND monotonicity-clean. Recommend **[1e-8, 5.48e-8]** as the
conservative choice (harvest-clean, and it excludes the worst single
reversal source at 1e-9) while explicitly acknowledging it still carries
most of the residual monotonicity risk (the 2.34e-8→5.48e-8 step is inside
it). **N_lambda = 4** (the 4 points at or below 5.48e-8, dropping 3e-7 for
harvest safety) is the practical recommendation; extending to 1.28e-7 buys
one more point at a known, small (2.6%) harvest-breach risk.

**Is lap-level dSoC monotone enough for Phase 4 bisection? Still no — improved,
not resolved.** New-grid-only: 95.4% (lap,SoC)-monotone, but only 72.8% of
laps are monotone across every SoC, and the worst single reversal (1.2 MJ,
0.30 of the 4 MJ window) is still large enough to plausibly derail a
bisection landing near that boundary. This is meaningfully better than the
original 78.2%/1.28× figures, but the underlying mechanism (warm-start
path-dependence, now demonstrated directly via the overlap-check) is not
confined to lambda=1e-9 and was not fully eliminated by removing it.

**Is the mu two-price hook needed, or contingent?** **Contingent on where
Phase 4 actually needs to operate**, not a flat yes or no: clean and
unnecessary for lambda ≤ 5.48e-8; **required** if bisection needs to reach
1.28e-7 or beyond (2.6%→69% of laps breach the cap there). Given the
recommended bracket tops out at 5.48e-8, the hook is not immediately
required — but if Phase 4's energy targets can't be met within this narrow,
low-dynamic-range bracket (Step 5 shows P_deploy barely varies across it),
the natural next move is to extend lambda_max, which immediately reintroduces
the harvest-cap risk this bracket was chosen to avoid.

**Should the canonical reallocation be retired for v3? No.** Step 4 directly
contradicts the hypothesis — the reallocation remains highly active (100% of
solves affected, tens-of-kJ aggregate effect, not shrinking with lambda)
throughout the entire tested range. It should be kept.

**Implied full-batch wall clock**, using this bracket's own mean solve time
(0.676 s/solve — notably cheaper than either the full 7-point bracket's
1.144 s or the previously truncated [1e-9,1e-7] bracket's 1.038 s, since this
range avoids both the epsilon degeneracy and the high-lambda convergence
difficulty near 1e-3), at 11,434 × 10 × N_lambda:

| N_lambda | solves | core-hours | @8 workers | @12 workers |
|---|---|---|---|---|
| 4 | 457,360 | 85.8 | 10.7 h | 7.2 h |
| 5 | 571,700 | 107.3 | 13.4 h | 8.9 h |
| 6 | 686,040 | 128.7 | 16.1 h | 10.7 h |

---

## Findings that contradict the recommendation (stated plainly, not reconciled)

1. **Hypothesis (a) is only partially right.** Removing lambda=1e-9 does not
   fully resolve lap-level non-monotonicity — a distinct, dominant violation
   cluster remains at 2.34e-8→5.48e-8, inside the recommended bracket.
2. **The harvest-safe zone and the monotonicity-clean zone don't coincide.**
   The recommended [1e-8, 5.48e-8] bracket is harvest-clean but still
   contains most of the residual monotonicity risk.
3. **P_deploy's target compression is not an artifact of the old floor.** It
   persists identically across the entire re-tested bracket — narrowing the
   bracket for the other two reasons does not buy back label variance.
4. **The canonical reallocation hypothesis was wrong.** It was expected to
   fade in relevance as lambda rises; instead it stays essentially constant
   in aggregate effect and remains necessary.
