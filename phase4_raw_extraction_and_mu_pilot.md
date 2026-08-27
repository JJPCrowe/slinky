# Raw-basis extraction and the 2-D (lambda, mu) pilot

Answers the five questions in order. Step 1 is production code (already
landed in `solver.py`/`batch.py`, verified end-to-end). Step 2 is a 24,000-solve
pilot for decision support — not production labels. Production batch (the
7-point lambda-only grid, 800,380 solves) was **not** run.

---

## 1. Was the Step 0 formula correct in code? **Yes — the code was right; only the write-up prose had a typo.**

Read `p4_02_steps012.py` (the script that actually generated the Step 0
numbers in `phase4_energy_price_decision.md`) directly, not the markdown:

```python
tlo, thi = laps[dt_cols[i]], laps[dt_cols[i + 1]]
dE = dlo - dhi  # additional energy spent going from hi-price to lo-price
dT = thi - tlo  # extra time cost of the higher price
```

`dT = thi - tlo` is `lap_time(hi) − lap_time(lo)` — the correct, non-degenerate
form, matching the ORIGINAL formula from the task that requested Step 0 two
turns ago. The markdown write-up's prose restated it as
`lap_time(hi) - lap_time(hi)` — a copy-paste duplication of "hi" where "lo"
belonged, introduced only in the documentation sentence, not in the code that
produced the numbers. **The reported dt/dE results, and everything downstream
of them (the ~1e-7 s/J marginal-value finding, the bracket extension to
[1e-8, 1e-6]), stand.** Corrected the sentence in
`phase4_energy_price_decision.md` to match the code (a documentation fix, not
a logic change) — flagging it here rather than leaving it silently altered.

---

## 2. Magnitude of the raw-vs-canonical label shift, and whether Phase 3 must be re-run

### Correction to the task's framing, verified from code

`d_coast_optimal` was **already raw** before this change — confirmed by
reading `solve_ocp`: `d_coast = _extract_coast_distance(s_mid, F_mguk_traj, handle.L)`
is called with the raw net force (`F_mguk_traj = F_dep_traj - F_reg_traj`,
built from the raw decision variables), never with `F_canon`. The module
docstring said as much even before this change ("d_coast deliberately stays
RAW"). **d_coast required no change and none was made.** Only
`P_deploy_mean_optimal`, `E_deploy_optimal`, and `E_harvest_optimal` — all
three sourced from the single call
`_extract_deployment_aggregates(v_traj, F_canon, handle.L)` — were
canonical-derived and needed the fix.

### What changed (production code, already landed)

In `f1_pipeline/ocp/solver.py`:
- `_extract_deployment_aggregates` is now called **twice** per solve: once
  on the raw `F_mguk_traj` (primary), once on the canonical `F_canon`
  (diagnostic).
- `P_deploy_mean_optimal`, `E_deploy_optimal`, `E_harvest_optimal` are now
  **raw** — same column names, so downstream code doesn't need to change
  which column it reads, only what's in it.
- Three new diagnostic columns added: `P_deploy_mean_canonical`,
  `E_deploy_canonical`, `E_harvest_canonical` — the old canonical values,
  preserved and unambiguously named, for one transition period.
- `E_final` is **unchanged**, still canonical — Step 1's instructions named
  "P_deploy, d_coast, E_deploy and E_harvest" and did not include E_final;
  leaving it out of scope rather than silently also changing it. **This
  creates a bookkeeping inconsistency worth flagging**: E_final (canonical)
  and E_deploy/E_harvest (now raw) are computed from different force splits,
  so `E_final ≠ E_initial − E_deploy_optimal + E_harvest_optimal` exactly
  going forward. Not resolved here — out of this task's stated scope.
- `_canonical_energy_reallocation` is **not deleted** — retained with a
  docstring explaining exactly why it was retired from the primary path (the
  v2-unity-efficiency vs v3-priced-efficiency argument), per instruction.
- `_extract_deployment_aggregates`'s docstring now states the wheel-vs-DC-bus
  convention explicitly (332.5 kW ceiling), so it can't be misread again.
- Verified end-to-end: a fresh solve and a small `run_batch` call both
  produce all seven columns correctly; `E_harvest_canonical < E_harvest_optimal`
  (raw) on the smoke check, consistent with the diagnosed direction.

### Magnitude of the shift — what could and couldn't be measured without re-solving

**E_harvest: measured directly, large.** Already established (previous
report, `smoke_v3_bracket_revalidation_realloc_diag.parquet`, 10,000 solves):
on a common DC-bus basis, canonical harvest is **less than** raw in 99.15% of
solves, median **−36 kJ** per solve. This is a real, material, already-verified
shift.

**P_deploy_mean / E_deploy: could NOT be empirically measured from the
existing 10,000-solve pool.** Checked directly — no parquet on disk retains
raw `F_dep_traj`/`F_brake_traj` trajectories (only in-memory during a solve,
never persisted), so a raw-vs-canonical P_deploy comparison for the already-
solved pool cannot be computed without re-solving, which this step explicitly
disallows. Rather than fabricate a number, here is what CAN be established
without re-solving — a direct proof from `_canonical_energy_reallocation`'s
own logic:

> For any interval, `net = F_mguk_raw − F_brake_raw`. Since `F_brake_raw ≥ 0`
> always (a variable bound), `net ≤ F_mguk_raw` on every interval. Where
> `net ≥ 0` (canonical's "deploy" bucket), canonical assigns `F_canon = net`,
> which is `≤ F_mguk_raw`. So **canonical E_deploy can never exceed raw
> E_deploy** — the only way they diverge is via intervals where raw
> simultaneously has `F_dep_raw > 0` AND `F_brake_raw > 0` (deploying and
> friction-braking at once), which a price-aware, non-wasteful v3 solve has
> no reason to produce (deploying against your own brake is pure economic
> waste with no benefit, unlike the v2-era regen/brake case where the two
> were genuinely interchangeable). This structurally bounds the P_deploy/
> E_deploy shift to be small, consistent with the module docstring's
> historical v2-era measurement (≤ 0.8 kJ) — but that number is v2-era and
> not independently re-verified for v3 here. Treat "small" as
> mathematically-argued, not measured.

For reference, the STORED (pre-fix, canonical-basis) `P_deploy_mean_optimal`
distribution on the 10,000-solve pool:

| percentile | value | % of 332.5 kW ceiling |
|---|---|---|
| p10 | 213,227 W | 64.1% |
| p50 | 303,004 W | 91.1% |
| p75 | 320,270 W | 96.3% |
| p90 | 326,327 W | 98.1% |
| p95 | 327,975 W | 98.6% |

If the raw distribution is close to this (as the proof above suggests), the
percentile-spread compression finding from the prior reports stands either
way — this was never contingent on which basis was used.

### Should Phase 3 be re-run? **Yes — confirm, but on a different basis than "the shift is large."**

The task asked to "confirm from the magnitude of the shift" — the honest
answer splits by label: **E_harvest's shift is measured and large**, a clear
confirmation. **P_deploy/E_deploy's shift is not measured and is
mathematically argued to be small.** Recommend re-running Phase 3 regardless,
for a different, still-sufficient reason: the labels' *definitional basis*
changed (not merely their numeric values by some amount) — Phase 3's reported
10.05 kW RMSE and 24/24-fold, MLP-vs-XGBoost comparison were measured against
labels sourced from a process now diagnosed as defective (Step 1 of the prior
report: canonical undershoots raw's own price-aware choice in 99% of cases).
Even if the numeric P_deploy shift turns out to be near-zero on re-solve, the
methodological claim "the model predicts P_deploy_mean_optimal" only holds
against whichever basis is actually correct, and that basis changed here.
E_deploy and E_harvest, if used as auxiliary targets or features, need the
same re-run for the same reason, with E_harvest additionally carrying a
confirmed large numeric shift.

---

## 3. Does mu change the harvest/deployment mix at fixed net energy?

**Yes, dominantly — mu is not a weak lever.** At every one of the 4 tested
lambda values, raising mu from 1e-8 to 1e-6 suppressed E_har by **99.6–99.9%**:

| lambda | E_har at mu=1e-8 | E_har at mu=1e-6 | net depletion at mu=1e-8 | net depletion at mu=1e-6 |
|---|---|---|---|---|
| 1.00e-8 | 198,628 J | 779 J (−99.6%) | 542,908 J | 547,750 J (+0.9%) |
| 3.11e-8 | 318,269 J | 787 J (−99.8%) | 498,109 J | 529,265 J (+6.3%) |
| 9.65e-8 | 439,014 J | 821 J (−99.8%) | 342,645 J | 463,023 J (+35.1%) |
| 3.00e-7 | 720,798 J | 933 J (−99.9%) | 0 J | 248,909 J |

**At low-to-moderate lambda, net depletion is roughly preserved while
harvest is nearly eliminated** — exactly the "shift toward friction braking"
mu is meant to produce; the missing retard duty must go somewhere given the
motion (and hence F_long) is largely unchanged, and friction brake is the
only other sink. **"Approximately fixed net energy" breaks down at the top
of the lambda range** (9.65e-8, 3e-7): net depletion itself shifts
substantially (+35% and +0→249kJ respectively) when mu is raised, because at
high lambda the raw solve was already leaning heavily on harvest to hold
depletion low — suppressing that harvest forces a real change in the energy
balance, not just a mix change. Flagging this rather than glossing over it:
lambda and mu are not fully orthogonal controls; their interaction strengthens
at high lambda.

**Range check:** [1e-8, 1e-6] brackets the useful transition well. By mu=1e-7
(the middle grid point) harvest has already dropped by ~85–90% at most
lambda values; by mu=1e-6 it's suppressed to near-zero (700–900 J, a floor
that further mu increases would not meaningfully reduce) — the effect
**saturates before the top of the tested range**, not beyond it.

**Chaining order:** on a matched 40-pair (480-solve) subset, the specified
mu-outer/lambda-inner scheme and the alternative lambda-outer/mu-inner scheme
both converged 100%. The specified scheme was marginally more efficient
(mean 37.4 vs 39.4 iterations, 0.822s vs 0.838s mean solve time) — consistent
with the intuition that consecutive lambda values (a finer, more continuous
sweep) warm-start better than consecutive mu values. **Recommend keeping the
specified order**; the difference is real but small, not a robustness concern
either way.

---

## 4. What fraction of 1-D-infeasible laps does mu recover, and at what lap-time cost?

**Built 1,000 synthetic 12-sector laps** (same construction as prior reports:
sampled without replacement across circuits — no GP in the 200-instance pool
has ≥20 instances, so within-circuit sampling remains infeasible, same
limitation restated; each of the 12 sectors solved independently at the same
nominal initial SoC, no sector-to-sector carry-over) × 10 SoC = 9,938 usable
(lap, SoC) combos (62 dropped for missing/non-converged sector data across the
12-solve grid).

**1-D feasibility, at mu=1e-8** (the lowest tested mu — the closest available
proxy to the pure 1-D family, since mu=0 itself was not solved in this
pilot):

- **Feasible** (some lambda satisfies both net depletion ≤ 4 MJ and harvest ≤ 8.5 MJ): 6,375/9,938 = **64.15%**
- **Infeasible** (no lambda satisfies both): 3,563/9,938 = **35.85%**

**This contradicts the task's own background framing of "~4.3% empty," and
that discrepancy is worth resolving rather than picking a number silently.**
The 4.3% figure traces to the previous report's Step 2 — "frac over 8.5 MJ
cap" evaluated *at the interpolated 4MJ-window crossing point specifically*
(4.25%), a different and narrower quantity than "does any lambda in the
tested grid satisfy both constraints simultaneously," which is what
1-D-interval-emptiness actually means and what's measured here. **35.85% is
the correct operationalization of the pilot's own stated question**; treat
4.3% as measuring something else, not as a discrepant re-measurement of the
same thing. Also: mu=1e-8 (not true mu=0) as the 1-D proxy means this 35.85%
is if anything an *underestimate* of the true zero-price infeasibility rate —
any positive mu, even a small one, can only suppress harvest and make the cap
easier to satisfy, never harder, so the genuine 1-D (mu=0) family should be
infeasible at least as often.

**Recovery: for the 3,563 1-D-infeasible combos, does any (lambda, mu) pair
in the full 2-D grid satisfy both constraints?**

- **Recovered: 3,052/3,563 = 85.66%**
- **Not recovered by any tested (lambda, mu): 511/3,563 = 14.34%** — these
  laps are infeasible even with the second price; either the useful (lambda,
  mu) region extends beyond what's tested here, or (for at least some of
  them) the 12-sector random draw is intrinsically too demanding regardless
  of price.

**Lap-time cost of recovery** — best feasible 2-D dt vs. the best (fastest,
though constraint-violating) dt achievable at mu=1e-8 across lambda (the
closest available notion of "the 1-D infeasible optimum"):

| | value |
|---|---|
| median cost | **0.825 s** |
| p95 cost | 1.119 s |
| max cost | 1.636 s |

A ~0.8s median lap-time cost to satisfy both constraints, on a lap that
couldn't satisfy them at all on the 1-D family, is a real and non-trivial
penalty in F1 terms, but the recovery itself — turning an infeasible result
into a feasible, quantifiable one for 86% of otherwise-stuck laps — is the
substantive finding.

---

## 5. Recommendation: proceed with the 1-D production grid, or reconsider?

**Reconsider — the pilot data does not support keeping the 1-D grid as the
sole production mechanism.** Stated plainly, as instructed, because this
contradicts the standing architecture decision:

- **35.85%** of synthetic (lap, SoC) combos have **no feasible lambda at all**
  on the 1-D family (measured directly, not the 4.3% figure previously cited
  for a different quantity) — over a third of the exhaustive-search
  population would return no valid production label under 1-D alone.
- mu recovers **85.66%** of those at a **median 0.8s** lap-time cost — a
  substantial, usable recovery, not a marginal one.
- mu's effect on harvest is dominant (−99.6% to −99.9% across the tested
  lambda range) and the tested [1e-8, 1e-6] range brackets the useful
  transition (saturates near the top, not beyond it) — the pilot's own grid
  choice was sound.
- The chaining-order and convergence checks raise no concerns: 99.99–100%
  converged throughout, the specified mu-outer/lambda-inner scheme performs
  marginally better than the alternative.

**This is exactly what the pilot was built to test, and it comes back
positive for a 2-D grid.** The pilot's own scale (24,000 solves, 73 min at 8
workers) doesn't itself justify committing to the full 2-D production
grid (11,434 × 10 × N_lambda × N_mu, potentially several hundred core-hours)
without a wider (lambda, mu) sweep to confirm the 511 still-unrecovered
combos genuinely need a wider range rather than a bug or an edge case in this
particular 4×3 pilot grid — but the 1-D-only production plan, as currently
scoped, would silently drop labels for roughly a third of the exhaustive
search space. Recommend: before committing to either the pure 1-D production
grid or a full 2-D production grid, run one more small, targeted probe on
just the 511 still-unrecovered combos with a modestly widened (lambda, mu)
range to establish whether they're recoverable at all, then size the
production 2-D grid (or confirm 1-D is acceptable with those combos
documented as a known gap) from that.

---

## Assumptions stated beside dependent numbers

- **Synthetic-lap construction** (Steps 2b/3/4 of prior reports, unchanged
  here): 12 sectors, independent per-sector solves at a shared nominal SoC,
  no sequential carry-over, sampled across circuits (within-circuit sampling
  confirmed infeasible from this 200-instance pool). Every crossing,
  recovery fraction, and lap-time-cost figure inherits this — none describe
  a real sequential lap.
- **mu=1e-8 as the 1-D-family proxy**: true mu=0 was not solved in this
  pilot; the 35.85% infeasibility figure is likely a slight underestimate of
  the genuine zero-price rate, stated directionally above.
- **Recovery lap-time cost** compares against the *fastest infeasible*
  1-D result (best dt at mu=1e-8 across lambda), not a well-defined "the 1-D
  optimum" (which doesn't exist for an infeasible lap by definition) — this
  is the closest available reference point, not a claim that a real car
  would have run that lap time.
- **P_deploy/E_deploy raw-vs-canonical magnitude** is proven small by
  construction (see Step 2 above) but not empirically re-measured for v3;
  flagged explicitly rather than presented as measured.
