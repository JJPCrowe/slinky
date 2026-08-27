# Phase 4 outer-loop architecture: does the harvest cap need a second price?

Analysis only, on data already on disk. No re-solving, no full batch. Answers
the five questions in order, then the supporting steps.

**Synthetic-lap construction (applies to every number below unless noted):**
12 sectors (`round(11434/932) = round(12.268) = 12`) sampled without
replacement from the 200-instance pool, mixing circuits (no GP in the pool
has ≥20 instances, so within-circuit sampling was already shown infeasible in
the prior report — same limitation, restated). Each of the 12 sectors is
solved **independently** at the **same nominal initial SoC** — there is no
sector-to-sector energy carry-over. This is not a sequential lap trace; every
crossing/median/fraction below inherits that approximation. 1,000 synthetic
laps × 10 SoC = 9,944 usable (lap, SoC) combos (56 dropped for missing data
in the merged 6-point lambda grid: 1e-9 + the 5 new re-solve values). Rebuilt
fresh with `dt_optimal` included (the existing lap parquets didn't retain
lap-time or per-lap instance membership) and **cross-validated exact-match
(0.0 J diff)** against the previous report's `smoke_v3_reval_synthetic_laps_12.parquet`
and `smoke_v3_reval_synthetic_lap_harvest_12.parquet` — same seed, same draws,
confirmed reproducible.

**Raw states used throughout**, per instruction: net depletion =
`E_initial − E_final`, harvest = `E_har_final` (DC bus). `E_deploy_optimal` /
`E_harvest_optimal` (canonical) are used only in Step 3, where they're the
subject of the comparison.

---

## 1. Is the empirical marginal time value of energy near 1e-7 s/J? **Yes.**

For each synthetic lap, at each adjacent pair of merged-grid lambda values:
`dt/dE = (lap_time(hi) − lap_time(lo)) / (net_depletion(lo) − net_depletion(hi))`
— seconds of lap time bought per joule of additional store energy spent.

| step | median (s/J) | IQR | frac wrong-sign |
|---|---|---|---|
| 1e-9 → 1e-8 | 8.61e-9 | [7.0e-9, 1.07e-8] | 0.3% |
| 1e-8 → 2.34e-8 | 1.82e-8 | [1.75e-8, 1.91e-8] | 6.1% |
| 2.34e-8 → 5.48e-8 | 4.07e-8 | [3.96e-8, 4.17e-8] | 14.1% |
| 5.48e-8 → 1.28e-7 | **9.38e-8** | [9.23e-8, 9.51e-8] | 9.3% |
| 1.28e-7 → 3e-7 | 2.15e-7 | [2.11e-7, 2.18e-7] | 1.6% |

**Overall (pooled, correct-sign only, n=46,613/49,720): median 6.98e-8 s/J**,
IQR [1.78e-8, 2.14e-7], p10–p90 [8.4e-9, 3.0e-7].

The empirical marginal value **rises steadily across the tested range and
lands almost exactly on 1e-7 s/J right at the 5.48e-8→1.28e-7 step
(9.38e-8)**. Your reasoning was correct, not the existing bracket. Energy
priced at the previously-recommended bracket's floor (1e-8 to 5.48e-8) is
priced at **8.6e-9 to 4.1e-8 s/J — roughly 2–10× below its true marginal
worth**, not merely "somewhat below." The "wrong-sign" fraction peaks at
exactly the 2.34e-8→5.48e-8 step (14.1%) — the same step the previous report
identified as the dominant residual non-monotonicity cluster. Consistent,
not coincidental: that's where the price signal is weakest relative to noise.

---

## 2. Where does the SoC-neutral crossing sit, and is it inside the tested span? **Mostly, but a large minority sits above it.**

Found via log-linear interpolation on the merged 6-point grid (per-lap, exact
crossings of `net_depletion(lambda) = 0`); exhaustive search means multiple
crossings are reported natively rather than treated as a problem.

| | n | fraction |
|---|---|---|
| single crossing | 6,747 | 67.9% |
| multiple crossings | 13 | 0.1% |
| **no crossing — depletion positive everywhere (crossing lies ABOVE the tested span, need lambda > 3e-7)** | **2,909** | **29.3%** |
| no crossing — depletion negative everywhere (crossing lies BELOW, need lambda < 1e-9) | 275 | 2.8% |

**For the 6,760 combos with a crossing: median = 2.12e-7 s/J**, IQR
[1.65e-7, 2.50e-7], p5–p95 [4.9e-8, 2.89e-7]. Only 0.3% of found crossings
sit at or below the 1e-9→1e-8 step — the result does not meaningfully depend
on the potentially-degenerate old epsilon point.

**This says the bracket needs to extend upward, and by more than a little.**
The median SoC-neutral price (2.12e-7) already sits near the very top of the
previously tested range (3e-7), and **29% of (lap, SoC) combos don't reach
SoC-neutral at all within the tested span** — for those, an even higher
lambda is needed. This is the single most consequential number in this
report for grid design.

**Secondary case — 4 MJ excursion window** (net depletion = 4.0 MJ, "spends
the pack"):

| | n | fraction |
|---|---|---|
| single crossing | 8,352 | 84.0% |
| multiple crossings | 121 | 1.2% |
| no crossing, above span | 0 | 0.0% |
| no crossing, below span (need lambda < 1e-9) | 1,471 | 14.8% |

**Median crossing = 1.07e-7 s/J**, IQR [7.1e-8, 1.45e-7] — comfortably inside
the tested span, and landing right at the same ~1e-7 mark as the marginal
time value from Step 1. Internally consistent: two independently-derived
quantities converge on the same price.

---

## 3. Is harvest at the crossing over the cap — is mu required or contingent? **Required. The previous report's conclusion is reversed.**

Harvest interpolated at the actual crossing lambda for each combo (not
harvest as a function of lambda in isolation — this is what the outer loop
would actually see at its selected operating point):

**At the SoC-neutral crossing (n=6,783, every crossing counted):**

| | value |
|---|---|
| median harvest | **8.20 MJ** |
| p95 | 10.41 MJ |
| max | 13.04 MJ |
| **fraction over 8.5 MJ cap** | **41.2%** (2,795/6,783) |
| fraction over 7.0 MJ cap (C5.2.10(i)) | 81.3% |
| fraction over 5.0 MJ cap (C5.2.10(ii), Qualifying floor) | 89.1% |

**At the 4 MJ window crossing (n=8,606):**

| | value |
|---|---|
| median harvest | 6.35 MJ |
| p95 | 8.37 MJ |
| fraction over 8.5 MJ cap | 4.3% |
| fraction over 7.0 MJ cap | 29.8% |
| **fraction over 5.0 MJ cap (Qualifying floor)** | **87.1%** |

**The harvest constraint is active at the optimum, not merely a tail risk.**
At the natural SoC-neutral target, 41% of laps already breach even the full
8.5 MJ cap, and the large majority breach the reduced caps. At the "spend the
pack" target, the full cap mostly isn't breached (4.3%), but the
**Qualifying-specific 5.0 MJ floor (C5.2.10(ii)) — the cap most relevant to
this dissertation's scope — is breached by 87%** of laps regardless of which
crossing target is used. **Say this plainly since it contradicts the
previous report: mu is required, not contingent.** The previous conclusion
("cap does not bind, mu stays a hook") was computed from harvest-as-a-function-
of-lambda in isolation, without asking where the outer loop would actually
operate; once evaluated at the actual candidate operating points, the
constraint binds for a majority of laps under the regulation's own reduced-cap
clause.

---

## 4. Raw or canonical labels for surrogate training? **Raw. Canonical is a defect, not a design choice.**

Read directly from `solver.py`'s `_extract_deployment_aggregates` (as in the
prior report): `E_harvest_optimal = -sum(F_canon[F_canon<0]) * h` —
wheel-mechanical, using the canonical force split, no efficiency applied.
Confirmed by cross-check: `E_har_canonical_equiv_J` (my independent
recomputation, DC-bus basis) equals `eta_regen * E_harvest_optimal` to
**2×10⁻¹¹ J** across all 10,000 solves — exact match, confirms both the
basis identification and the diagnostic capture.

**On the common DC-bus basis, canonical harvest is LESS than raw harvest in
99.15% of solves** (9,915/10,000; only 0.85% show the "intended" direction).
Median `delta_E_har_J = E_har_canonical_equiv − E_har_raw = −35,931 J` per
solve — canonical typically harvests **36 kJ less** than the solver's own raw
choice, not more.

**This contradicts the reallocation's stated intent.** "Regen-first" was
built for v2's unity-efficiency world, where reassigning retard force from
brake to regen was a pure win (no efficiency cost, so more regen could only
help). Under v3, regen carries a genuine `eta_regen < 1` cost and the
canonical reallocation is a **greedy, forward-only, locally-capped heuristic**
— it doesn't have the OCP's global, price-aware optimization foresight. The
raw solve already trades off regen against brake optimally given the true
efficiency and headroom; the canonical pass can only ever match or undercut
that, and empirically it undercuts it 99% of the time. This is a defect
relative to what the name and docstring promise, not a legitimate design
choice — flagging it as such, not fixing it (per instruction).

**Train the surrogate on raw labels** (`E_har_final`, `E_initial − E_final`).
The Phase 4 forward simulator propagates SoC using raw physics (per the task's
own framing); training on canonical labels — which systematically understate
harvest relative to what the simulator will actually execute — means the
surrogate and the simulator describe different vehicles. This isn't a close
call: the two label sets differ by tens of kJ per solve in a consistent
direction, which will bias any surrogate trained on the wrong one toward
under-predicting achievable harvest.

---

## 5. Proposed 2-D grid, since mu is required

**Lambda: 8 points, log-spaced across [1e-8, 1e-6], `np.geomspace(1e-8, 1e-6, 8)`.**
Informed directly by Steps 1–2: the floor stays at 1e-8 (avoids the 1e-9
degeneracy documented in the prior report); the ceiling extends a further
1.3 decades past the previously-tested 3e-7, because the SoC-neutral median
crossing (2.12e-7) sits near the old ceiling and 29% of laps don't cross
within it at all — 1e-6 gives roughly a decade of headroom past the observed
p95 (2.89e-7) for laps that need to go higher still.

**Mu: 5 points, log-spaced across [1e-8, 1e-6], mirroring lambda's own
range.** Derivation, stated plainly as an estimate rather than a calibrated
shadow price (a true shadow price would need actual 2-D solves, out of scope
for analysis-only work): mu prices cumulative harvest in the same s/J
currency as lambda prices stored energy, and Step 3 shows the harvest
constraint starts binding within lambda's own already-tested range (harvest
crosses 8.5 MJ between 5.48e-8 and 1.28e-7, per the prior report). There is
no principled reason mu's effective scale would differ by orders of magnitude
from lambda's — both are prices on the same physical currency (joules
through the same DC bus) over the same lap timescale. **Treat this range as
a starting bracket to be checked against the actual constraint-activity rate
in a pilot run, not a validated final choice.**

**Total solves, cost:**

| scope | solves | core-hours (@0.676 s/solve) | @8 workers | @12 workers |
|---|---|---|---|---|
| 200-instance pool (pilot, this report's scale) | 200×10×8×5 = 80,000 | 15.0 | 1.9 h | 1.3 h |
| full production (11,434 instances) | 11,434×10×8×5 = 4,573,600 | 858.8 | 107.3 h (~4.5 days) | 71.6 h (~3 days) |

**Should the SoC grid drop from 10 to compensate? Recommend against it,
though the cost case for considering it is real.** Halving to 5 SoC values
would halve both figures above (429.4 core-hours / ~54h@8w / ~36h@12w at
production scale) — a substantial saving. But lambda/mu and initial SoC are
not interchangeable: SoC is a boundary *state* (what energy the car actually
has at sector start, which also gates feasibility — a low-SoC sector cannot
deploy regardless of price), while lambda/mu are *prices* (shadow values on
energy and harvest). They correlate in effect (both push toward more or less
conservative energy use) but are not substitutes for representing where the
car actually is in state of charge. The prior reports found the sharpest
nonlinearities (E_final pegging at the 4 MJ capacity bound, P_deploy
saturating) concentrated at the SoC extremes — exactly where coarsening this
grid would hurt most. If compute must be cut, cut lambda/mu grid density
first (a quick pilot at 4×3 could establish whether 8×5 resolution is even
needed before committing to it), not SoC resolution.

---

## Assumptions, stated beside what depends on them

- **Synthetic-lap construction** (stated at top): 12 sectors, independent
  per-sector solves, shared nominal SoC, no sequential carry-over, sampled
  across circuits. Every crossing lambda, every harvest-at-crossing figure,
  and Step 0's dt/dE all inherit this — none of them describe a real
  sequential lap.
- **Step 1/2 crossing search** uses log-linear interpolation between grid
  points; resolution is limited by the 6 available merged-grid points (5
  intervals) — a crossing reported at, say, 2.1e-7 is an interpolate between
  the real solved points at 1.28e-7 and 3e-7, not itself a solved value.
- **Mu's proposed range is an estimate, not a calibrated shadow price** — no
  2-D solves exist yet to derive one properly; flagged explicitly in Step 5.
- **Step 0's "wrong-sign" fractions** (up to 14.1%) mean the dt/dE medians are
  computed after filtering to positive-sign values only — the full
  distribution including sign-violating laps would be noisier; the filtered
  medians represent the "well-behaved" majority.

## Where this contradicts the previous report — stated, not reconciled

The previous report (`smoke_v3_bracket_revalidation.md`) concluded the mu
hook was "not immediately required" within its recommended [1e-8, 5.48e-8]
bracket, based on harvest-as-a-function-of-lambda alone. **This report
reverses that conclusion**: evaluated at the lambda the outer loop would
actually select (the SoC-neutral or 4MJ-window crossing), harvest breaches
the Qualifying-relevant 5.0 MJ cap for 87–89% of laps regardless of which
target is used, and breaches the full 8.5 MJ cap for 41% of laps at the
SoC-neutral target. The two reports are not in conflict about the data —
they ask different questions (harvest at a fixed lambda vs. harvest at the
lambda the loop would pick) — but the second question is the one that
actually decides the architecture, and it points the opposite way.
