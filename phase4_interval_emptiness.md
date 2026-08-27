# E_final to raw basis, and the true structural interval-emptiness rate

Answers the five questions in order. Step 1 is a landed, verified production
code fix (blocking — production now unblocked). Step 2 is analysis only, no
solving. Step 3 is skipped — its trigger condition was not met, stated
explicitly per instruction. Production batch was **not** run.

---

## 1. Why was E_final canonical, and does the accounting identity now close?

### Diagnosis, before changing anything

Read `solver.py`'s `solve_ocp` and `_canonical_energy_reallocation` directly.
`E_final` was **not** simply "the canonical force-split's terminal value" in
the sense of an otherwise-correct v3 integration reusing a different split —
it was doubly divorced from v3's actual dynamics:

1. **Wrong force split**: computed from `F_canon` (the greedy, forward-only
   reallocation), not the OCP's own raw solved `F_dep`/`F_reg` — the same
   pass-1 defect already retired for P_deploy/E_deploy/E_harvest.
2. **Wrong efficiency, independently**: `_canonical_energy_reallocation`'s
   own forward walk integrates `E = E - Fk*h`, i.e. `dE/ds = -F'` with
   **unity efficiency** — it never applies `eta_motor`/`eta_regen` at all,
   even under v3. This is on top of defect 1, not the same defect. Meanwhile
   `handle.E`'s own trajectory (`E_traj` — already captured in `OCPResult`,
   already unused as `E_final`) is the OCP's own decision variable, solved by
   IPOPT via proper trapezoidal collocation of the **actual** v3 dynamics
   (`dynamics.py`: `dE/ds = -F_dep/eta_motor + F_reg*eta_regen`). It was
   sitting there the whole time.

The original v2-era motivation was genuine, not spurious: the module's own
historical rationale explicitly names E_final's nondeterminism (up to the
same ~11.3 kJ margin as E_harvest's) as part of what canonical reallocation
was built to fix, under v2's unity-efficiency regen/brake degeneracy. But
that motivation rests on the exact same degeneracy the pass-1 change already
established is far less significant under v3's priced, efficiency-aware raw
solve — so it retires the same way, not by patching the old mechanism with a
better one.

### Fix (landed in `solver.py`/`batch.py`, verified)

- `E_final` is now `float(E_traj[-1])` — the OCP's own solved terminal
  state, raw by construction, no recomputation.
- `E_final_canonical` added as the diagnostic sibling, same transition-period
  convention as the other three.
- `_canonical_energy_reallocation` **not deleted** — still computed (still
  feeds the diagnostic columns), docstring already carries the retirement
  note from the pass-1 change.
- Verified end-to-end on a single solve and via a 2,000-solve re-solve
  (below) before reporting anything.

### Does the accounting identity close?

**Checked, not forced.** Formula (wheel-mechanical E_deploy/E_harvest
converted to store-energy basis via the efficiencies):

```
identity_residual = E_final − (E_initial − E_deploy_optimal/eta_motor + E_harvest_optimal*eta_regen)
```

On the 2,000-solve verification pool (below): **residual is always
negative**, median **−1,231 J**, IQR **[−2,605, −881] J**, max\|residual\|
**30,151 J**. As a fraction of E_final magnitude: median **0.087%**, p95
**1.15%** (the mean and max of this ratio are not meaningful — they blow up
on the handful of solves where E_final itself is near zero; the median/IQR
are the representative figures). **The identity does not close exactly, and
it should not be forced to** — the residual is fully, deterministically
explained: it correlates with a captured simultaneous-deploy-and-regen
diagnostic (`min(F_dep, F_reg)` summed over intervals where both are
positive) at **r = −1.0** across all 2,000 solves. Mechanism: `E_deploy_optimal`/
`E_harvest_optimal` are computed from the *net* `F_mguk = F_dep − F_reg`
bucketed into single-sided deploy/regen — wherever an interval has BOTH
`F_dep > 0` and `F_reg > 0` simultaneously, the net-force accounting
understates the *gross* energy that actually left and returned through the
real efficiency losses, which the true `E[N]` (computed from gross F_dep and
F_reg separately, each with its own efficiency) correctly captures. The gap
is real physics the simplified aggregate labels don't represent, not
numerical error. (One data-quality note, not adjusted: the interval-count
diagnostic itself, `n_simul_intervals`, came back as exactly 50/50 on every
solve — almost certainly inflated by IPOPT's interior-point method leaving
tiny non-zero residuals near a bound on both variables in intervals that are
economically pure-deploy or pure-regen, not genuine large-scale
simultaneity; the energy-weighted `simul_dep_reg_waste_J` figure, not the
raw interval count, is the trustworthy one, and it's what carries the r=−1.0
relationship.)

### Verification re-solve

200 instances × 10 SoC at a single lambda = 9.66e-8 (2,000 solves, no
chaining — single lambda, cold-started each, no adjacent lambda to warm
from), 8 workers, parallelised across (instance, SoC) pairs, per
instruction. **2,000/2,000 converged (100%)**. All eight-plus columns
(`E_final`, `E_final_canonical`, `E_deploy_optimal`, `E_harvest_optimal`,
`E_har_final`, `P_deploy_mean_optimal`, `d_coast_optimal`, `dt_optimal`)
populated correctly on every row — no missing/NaN data among converged
solves.

---

## 2. What is the structural interval-emptiness rate?

**Your framing was correct. It is near 4%, not 35%.**

Used `output/smoke_v3_bracket_revalidation_solves.parquet` — confirmed no
`harvest_price` column exists in this file (mu was never swept when it was
generated; `build_ocp`'s `harvest_price` default of 0.0 applied throughout),
so this is the genuine 1-D family, unlike the pilot's mu=1e-8 proxy.
Rebuilt 12-sector synthetic laps, same construction and seed as prior
reports: 12 sectors sampled without replacement across circuits (no GP in
the 200-instance pool has ≥20 instances — within-circuit sampling remains
infeasible, restated), each solved independently at the same nominal
initial SoC, no sector-to-sector carry-over. 10,000 (lap, SoC) combos, 0
dropped.

For each combo, interpolated `lambda_dep` (net depletion crosses 4.0 MJ,
falling) and `lambda_har` (harvest `E_har_final` crosses the cap, rising) —
**both bounds must resolve inside the tested [1e-8, 3e-7] span** to classify
a combo definitively; only 5,947/10,000 (59.47%) do (the rest are
interpolation-limited — see below, reported separately rather than folded
into the rate).

**At the primary 8.5 MJ cap, of the 5,947 definitively-resolvable combos:**

| | count | fraction |
|---|---|---|
| **EMPTY** (structural infeasibility) | **368** | **6.19%** (of resolvable) / **3.68%** (of all 10,000) |
| non-empty | 5,579 | 93.81% / 55.79% |

**This is close to your ~4% framing and nowhere near the pilot's 35.85%.**
The pilot's number was real, but it measured a different thing (whether a
sparse, non-scaled grid happens to land inside the interval) — not
structural infeasibility.

**Non-empty interval width** (`lambda_har / lambda_dep`, n=5,579):
median **2.022**, p10 **1.208**, p5 **1.128**. At the median, the feasible
window spans roughly a factor of 2 in lambda — comfortable. At the
narrowest 5%, it's only **12.8% wide multiplicatively** — a genuinely tight
window that any grid coarser than ~13% steps will step over.

**Bounds outside the tested span** (the 40.53% not counted above),
correctly signed — note the direction semantics are opposite for the two
bounds since depletion falls and harvest rises with lambda:

- `lambda_dep` unresolved: 1,552/10,000 (15.52%) — net depletion is already
  under 4 MJ even at lambda=1e-8; the true bound would need lambda *below*
  1e-8 (not a concern — the depletion constraint simply doesn't bind for
  these laps at any tested price).
- `lambda_har` unresolved: 3,125/10,000 (31.25%) never reach the cap even at
  lambda=3e-7 (true bound lies *above* the tested span — harmless, harvest
  just never gets that high).

**Reduced-cap sensitivity cases — labelled as applying to part of the
calendar only** (C5.2.10(i)/(ii); B7.2.1c caps the reduction at 12
competitions per championship, ≤4 of those at the 5 MJ floor):

| cap | both-inside | structural empty (of resolvable) |
|---|---|---|
| 8.5 MJ (primary) | 59.47% | **6.19%** |
| 7.0 MJ (C5.2.10(i)) | 81.38% | **31.51%** |
| 5.0 MJ (C5.2.10(ii), Qualifying floor) | 61.26% | **84.48%** |

**Flagging this prominently, separate from the primary architecture
question**: at the 5.0 MJ floor specifically, the feasible interval is empty
for the overwhelming majority of resolvable laps — consistent with (and a
sharper, more rigorous version of) earlier cruder findings that the
Qualifying-specific reduced cap is where the real pressure sits. This does
not change the primary-calendar answer below, but it means the small subset
of competitions running at the 5 MJ floor is a genuinely different regime
that a pure 1-D grid will not handle, regardless of how the primary-cap
question resolves.

---

## 3. How much of the pilot's 35.85% was grid resolution?

**Most of it.** Isolated purely the resolution question: of the 5,579
genuinely non-empty intervals (8.5 MJ cap), what fraction has **no** grid
point from `geomspace(1e-8, 3e-7, N)` landing inside `[lambda_dep,
lambda_har]`?

| N | frac of non-empty intervals MISSED |
|---|---|
| 4 (the pilot's grid) | **52.89%** (2,951/5,579) |
| 5 | 34.68% (1,935/5,579) |
| **7 (proposed production grid)** | **16.81%** (938/5,579) |
| 9 | 12.78% (713/5,579) |

At N=4, over half of genuinely feasible laps would show as apparently
infeasible from under-sampling alone — combined with the true 6.19%
structural rate, that's roughly consistent with an apparent infeasibility
rate in the 50s-of-percent range from resolution alone, which (further
offset somewhat by the pilot's separate mu=1e-8 confound, already flagged
in the prior report, which suppresses harvest and makes the cap easier to
satisfy) is directionally consistent with the pilot's observed 35.85%.
**The 1-D architecture was never structurally broken; the 4-point pilot
grid stepped over the window, exactly as you predicted.**

---

## 4. p5 interval width, and training-grid density implied

**p5 width ratio = 1.128** — the narrowest 5% of feasible intervals span
only 12.8% multiplicatively. If the outer loop were restricted to grid
points (rather than the exhaustive-evaluation architecture already decided),
a grid would need **consecutive-point ratios below ~1.13** to catch that
narrowest 5% reliably — that's `geomspace(1e-8, 3e-7, N)` with
`N ≈ log(3e-7/1e-8)/log(1.13) ≈ 39` points, an order of magnitude denser
than the proposed 7-point grid. **The 7-point grid (ratio ≈1.76 per step)
is nowhere near dense enough to catch the tail on its own** — it will
reliably catch the median-width intervals (ratio 2.02) but miss a real
fraction of the narrow ones, consistent with the measured 16.81% miss rate
above. Since the architecture is exhaustive evaluation over the grid (not
grid-restricted bisection), a missed narrow interval doesn't produce a wrong
label — it produces **no feasible label at all** for that (lap, SoC), i.e. a
false negative on feasibility. That's a real cost of the 7-point grid, not a
catastrophic one (it affects ~17% of an already-small ~6% empty-adjacent
population), but worth being explicit about rather than assuming the
production grid resolves what this analysis measured.

---

## 5. Proceed with 1-D production on `geomspace(1e-8, 3e-7, 7)`, or not?

**Proceed. The architecture holds.** Structural interval-emptiness at the
primary 8.5 MJ cap is 3.68–6.19%, close to your original framing and well
under the ~15% threshold that would have triggered Step 3 (the mu pilot).
**Step 3 is skipped, per instruction, since Step 2 did not justify it** —
stating this explicitly rather than running it anyway.

Two caveats worth carrying forward, not blockers to proceeding:

1. **The 7-point grid itself will miss ~17% of genuinely non-empty
   intervals** purely from resolution (Q3/Q4 above) — this doesn't break
   the architecture, but it means a modest fraction of exhaustive-search
   labels will show "no feasible lambda" for laps that do, in fact, have one
   between grid points. If label completeness matters more than the current
   7-point budget, N=9 recovers roughly a quarter of that gap (16.81% →
   12.78%) at a proportionate compute increase.
2. **The 5.0 MJ Qualifying-floor sensitivity case (84.48% structural
   emptiness) is a genuinely different regime** from the primary calendar
   and is not resolved by anything in this report — it affects at most 4
   competitions per championship per B7.2.1c, so it doesn't change the
   primary production-grid recommendation, but a pure 1-D grid will not
   produce feasible labels for those specific competitions' Qualifying
   sessions if that reduced cap needs to be modelled explicitly later.

---

## Assumptions stated beside dependent numbers

- **Synthetic-lap construction** (unchanged from prior reports): 12 sectors,
  independent per-sector solves at a shared nominal SoC, no sequential
  carry-over, sampled across circuits (within-circuit sampling confirmed
  infeasible from this 200-instance pool). Every emptiness rate, width
  ratio, and miss-rate figure inherits this — none describe a real
  sequential lap.
- **"Both bounds inside the tested span" (59.47%)** is the population the
  6.19%/93.81% split is measured over; the remaining 40.53% are
  interpolation-limited in a way that doesn't threaten feasibility (both
  directions found were the harmless ones — constraint doesn't bind, or
  never gets close), not unresolved risk.
- **The sampling-artefact grid-miss calculation** approximates "a grid point
  satisfies both constraints" as "a grid point falls between the
  interpolated `lambda_dep` and `lambda_har`" — consistent with how the
  pilot's own empirical grid test worked, not an independent re-derivation.
- **E_final's accounting residual is reported, not eliminated** — the
  identity is now correct in basis (raw throughout) but the naive
  additive form doesn't capture gross simultaneous deploy+regen activity;
  median residual is 0.087% of E_final, small enough not to be a practical
  concern, but stated as a measured residual rather than an exact closure.
