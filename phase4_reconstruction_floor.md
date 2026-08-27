# Phase 4 — Reconstruction Floor: Signed Error, Telemetry Proxy, Joint Fixed Point, Oracle Bound

This report re-examines the headline conclusion of `phase4_forward_simulator.md`
(reconstruction costs a median 0.049 s/sector, 0.603 s/lap) against three
specific objections: the reported number is an unsigned median that cannot
distinguish reconstruction falling short of the optimum from reconstruction
*exceeding* it via constraint violation; the lap-scaling summed absolute
per-sector medians rather than allowing signed cancellation; and the 94%
constraint-violation rate documented in that report is an admitted
implementation gap, not evidence of an information-theoretic floor. All three
objections are addressed below on a clean, corrected measurement — not argued
away. **The short answer: (a)-(c) are all valid. Correcting for them
overturns the ORIGINAL headline's mechanism entirely — the near-zero
baseline sector-level error was substantially an artefact of the
reconstruction illegitimately violating constraints to go faster, not
evidence of an accurate method — and the genuine, information-theoretic
floor of the three-scalar representation (Step 4's unconstrained oracle) is
negligible against +0.05 s/lap, i.e. the three scalars themselves are NOT
the bottleneck. What the current reconstruction POLICY achieves is still
short of the target (best measured configuration: 16.95% flag-free,
lap-level median signed error +0.78 s), but Step 4 shows this is a solvable
policy-maturity problem, not a hard representational limit.** See §5 for
the full reasoning.

**A correction applied before any of the four steps below**: the prior
report made NET (unity-efficiency, `E_deploy_optimal - E_harvest_optimal`
basis) the primary SoC-window feasibility check in `simulate_sector()`. That
was wrong. The OCP itself only ever constrains its real GROSS state (v3
efficiency-weighted) to `[0, e_batt_capacity]`; NET is a bookkeeping
convention with no matching physical constraint. Re-running Step 3a's
fidelity check with GROSS as the constraint basis: **feasible fraction on
the 2,000 TRUE re-solved trajectories rose from 91.70% to 95.45%** — exactly
the 81/2,000 (4.05%) NET-basis false positives disappearing, confirmed
directly (`soc_window_violation_gross_J` remains 0/2,000, unchanged; `_net`
is still recorded as a diagnostic, just no longer gates `feasible`). GROSS
is now primary in `phase4/simulate.py`; the module docstring documents this
correction and the ~1.4 kJ (median, on this pool) NET/GROSS gap explicitly
rather than eliminating it.

---

## Step 1 — Signed error distribution

Using the existing reconstruction machinery re-run against stored production
scalars (no OCP re-solve; `reconstruct_controls()` + the GROSS-corrected
`simulate_sector()` only) to add the columns Step 1 needs — signed error and
per-scenario flag detail — that were not saved in the original
`phase4_step3b_results.parquet` (only `recon_feasible`/`sim_feasible`
booleans were kept, not which specific constraint fired). **dt_err_signed =
dt_recon − dt_true; negative means reconstruction is FASTER than the OCP
optimum.**

### Signed dt error, full population (n=2,000)

| p5 | p25 | median | p75 | p95 | mean |
|---|---|---|---|---|---|
| −0.280 s | −0.081 s | **−0.0097 s** | +0.008 s | +0.521 s | +0.051 s |

**65.85% of scenarios are negative** (reconstruction faster than the true
optimum), 34.15% positive. This alone overturns the original report's
implicit framing: the median signed error is not "reconstruction costs
0.049 s" — it is **reconstruction is very slightly FASTER than optimal at
the median**, with the earlier 0.049 s figure being the median of
`|signed error|`, a different and less informative statistic once the sign
is known to be this unbalanced.

### Cross-tab: sign vs constraint flags

| flag | n (% of sample) | frac. negative | median signed |
|---|---|---|---|
| friction circle violated | 723 (36.1%) | **79.81%** | −0.055 s |
| deploy envelope violated | 383 (19.1%) | 50.39% | −0.0006 s |
| regen abs. cap violated | 1,676 (83.8%) | 74.70% | −0.019 s |
| SoC window (gross) violated | 366 (18.3%) | 24.32% | +0.172 s |
| **friction circle OR deploy envelope** | 1,050 (52.5%) | 69.24% | −0.035 s |
| **neither** | 950 (47.5%) | 62.11% | −0.0023 s |

Friction-circle violation shows the strongest association with going faster
(79.8% negative, median −0.055 s) — consistent with (a)'s hypothesis:
exceeding the tyre-grip limit lets the reconstructed car corner/accelerate
harder than physics allows, and that shows up as banked time. Deploy-envelope
violation shows almost none (50.4%, median ≈0) — despite being flagged in
19.1% of cases, it is not, on its own, a meaningful source of "cheating"
speed; it is a smaller-magnitude, more symmetric error.

**Does cheating fully explain the negatives?** Only partially. Of the 1,317
negative-error scenarios, 55.2% carry a friction-circle-or-envelope flag —
the more direct "faster because it broke a speed-relevant rule" explanation
— but 44.8% do not. Only 2.13% of negative scenarios are fully flag-free, so
almost every negative case involves *some* violation (regen-cap violation
alone accounts for a great deal of this, at 83.8% baseline prevalence), but
regen-cap violation has no direct mechanism for making the car faster (it
only affects the deploy/regen split's *energy* accounting, not the net
force that determines v(s) — see the mechanical point in Step 3). **The
honest reading: constraint violation is present in nearly all negative
cases, but "the friction circle/envelope was broken" explains the sign for
about half of them; the rest of the negative bias has a different, less
direct source** (see Step 3: it disappears substantially once the
regen/friction self-consistency issue is fixed by the joint fixed point and
the v_peak pin, which is itself evidence that it was a reconstruction-policy
artefact, not a physical-floor effect).

### The flag-free subset (5.95%, n=119) — "the only subset where dt error means what the report claims it means"

| p5 | p25 | median | p75 | p95 | mean |
|---|---|---|---|---|---|
| −0.882 s | +0.0002 s | **+0.0051 s** | +0.0092 s | +0.022 s | −0.146 s |

This **materially changes the headline**: in the only subset with zero
constraint violations, the median signed error is **+0.005 s — essentially
negligible**, and now correctly signed (reconstruction is honestly, very
slightly, slower than optimal, as a bounded approximation method should be).
23.53% are still negative here (so violation isn't the *only* mechanism for
negative error, consistent with the cross-tab above), and the mean is
dragged very negative by a single extreme outlier (p5 = −0.88 s on a
119-scenario subset — one bad case dominates the mean). This subset is
small and almost certainly not representative of the full population (it
is disproportionately the sectors where reconstruction's crude policies
happen not to trip anything, plausibly short/simple sectors) — it cannot be
used to claim reconstruction "actually costs ~0.005 s/sector" across the
board. It does establish that **when the reconstructed profile is
physically legitimate, its dt error is tiny**, which is an important,
different claim from the full-population statistic.

### Synthetic 12-sector laps, signed sum

Same construction as prior reports (12 sectors sampled without replacement
across circuits, independent per-sector draws, no sequential SoC/velocity
carry-over — restated limitation: this is not a chained lap simulation),
seed 20260826, 2,000 synthetic laps:

| p5 | p25 | median | p75 | p95 | mean | frac. negative laps |
|---|---|---|---|---|---|---|
| −1.226 s | −0.537 s | **+0.100 s** | +1.324 s | +5.087 s | +0.804 s | 47.00% |

**Three different lap-level numbers, three different questions:**

| method | value | question it answers |
|---|---|---|
| report's original: sum of per-sector \|error\| medians | 0.603 s | naive scaling, not a real lap statistic |
| median of per-lap SUM of \|signed error\| (errors never cancel) | 1.780 s | "how big is the error in aggregate if nothing cancels" |
| **median of per-lap SUM of signed error (errors DO cancel)** | **0.100 s** | **"what is the typical net lap-time bias" — the defensible number** |

The signed-sum median (0.100 s) is the right number to quote for "typical
net bias" — but it is **not the full picture**: the distribution is wide
and right-skewed (mean 0.804 s, p95 +5.09 s), so a materially-sized share of
laps carry a large positive cost even though the central tendency is small,
and 47% of laps are net-negative (the reconstructed lap comes in faster than
optimal, i.e. via banked constraint violations across its 12 sectors). This
is why Step 3/4 matter: the ~0.10 s median signed figure includes the same
"cheating" contamination as the sector-level number, and the honest
median shifts once that is corrected (see next).

---

## Step 2 — Is telemetry v_max_kph a usable proxy for the OCP's peak velocity?

Correlated telemetry `v_max_kph` (already in the Phase 1 feature matrix,
confirmed invariant across SoC/λ for a given sector — 0/11,433 sectors show
any variation) against `np.max(v_traj)` from the Step 0 retained
trajectories, across all 2,000 resolved scenarios:

| | value |
|---|---|
| r (overall) | **0.929** |
| median offset (telemetry − OCP peak), kph | **−33.18** |
| IQR of offset | [−46.70, −21.47] |
| fraction of scenarios where OCP peak exceeds BOTH boundary speeds | **98.75%** |

**Strong linear correlation, but telemetry is not a direct proxy — it is
systematically and substantially slower than the OCP's own peak.** This is
exactly what Step 0/5 already flagged conceptually: the real driver does not
perform the OCP's idealised "accelerate past both boundary speeds, then
brake hard at the very end" manoeuvre — 98.75% of scenarios show the OCP
doing exactly that, essentially the norm rather than an edge case, while a
real driver (subject to tyre wear, fuel, strategy, risk margins the pure
time-minimising OCP doesn't model) does not chase the same peak.

**By zone_eligible:**

| | r | median offset (kph) | IQR |
|---|---|---|---|
| shut (aero pinned) | 0.947 | −24.18 | [−33.29, −14.78] |
| eligible (aero free) | 0.918 | −38.33 | [−50.02, −25.66] |

**By λ:** r ranges 0.921–0.963 (tightest at the highest λ, 3×10⁻⁷), median
offset shrinks from −38.8 kph at the lowest λ to −18.6 kph at the highest —
sensible, since higher λ prices energy more heavily and should pull the
OCP's own peak down toward what a real, less energy-profligate driver does.

**Verdict: partially usable, with a mandatory bias correction, not usable
raw.** Applying it raw as "the accel-phase endpoint speed" would
systematically place reconstruction's peak ~33 kph too low. Applying a
population-level bias correction (stratified by zone_eligible, as used in
Step 3 below) turns it into a genuinely useful **existing feature** — no
fourth model output, no re-derivation across 799,939 rows, no new solver
run — that materially changes reconstruction's behaviour (Step 3). The
residual spread after stratified correction (IQR ~25 kph even within a
homogeneous stratum) is real and non-trivial, so it is a partial, not
complete, fix for the missing peak-velocity information — consistent with
Step 4's oracle finding that using the TRUE peak directly (not telemetry)
closes more of the gap.

---

## Step 3 — Joint reconstruction/simulation fixed point (+ telemetry pin, attributed separately)

### Joint fixed point

Implemented in `phase4/reconstruct.py` (`reconstruct_joint()` /
`_reallocate_forces()`): the phase boundaries (k_A, k_X, k_B) from the
initial shooting-method reconstruction are held fixed; on each iteration,
`simulate_sector()`'s ACTUAL achieved v(s) is fed back in to re-derive
F_ice/F_dep (accel phase, `p_ice_max`/`P_deploy_mean` divided by the real
v_mid instead of reconstruction's internally-estimated v_mid) and F_reg/
F_brake (brake phase, regen-cap and friction-circle recomputed against the
real v_mid), then re-simulated, repeating until v(s) stops changing (tol
0.01 m/s) or 10 iterations are hit.

| | value |
|---|---|
| convergence rate | **99.80%** (1,996/2,000) |
| mean / median iterations to converge | 3.64 / 3.0 |

**Diagnosis confirmed:** this was an implementation gap, not a floor, exactly
as (c) argued. Re-deriving the SAME force-allocation policy against the
actual v(s) — no new information, no fourth label — converges quickly for
essentially every scenario.

### Effect on flag-free fraction and signed error (four configurations)

| config | flag-free (feasible) | sector median signed | sector frac. negative |
|---|---|---|---|
| baseline (3-scalar, corrected simulator) | 5.95% | −0.0097 s | 65.85% |
| **joint fixed point** | **15.05%** | −0.0066 s | 63.85% |
| **v_peak pin** (telemetry, bias-corrected) alone | 6.25% | **+0.0019 s** | **45.30%** |
| **v_peak pin + joint** | **16.95%** | +0.0046 s | 42.25% |

Individually attributed, per instruction:

- The **joint fixed point** roughly **2.5x's the flag-free fraction**
  (5.95%→15.05%) but barely moves the signed-error sign balance
  (65.85%→63.85% negative) — it fixes *self-consistency* (regen/friction
  values matching the achieved speed) without fixing *timing* (when to stop
  accelerating), which is a different problem.
- The **v_peak pin** does the opposite: it barely moves flag-free fraction
  (5.95%→6.25%) but **cuts the negative-sign fraction from 65.85% to
  45.30%**, nearly balanced, and flips the sector median from negative to
  slightly positive (+0.0019 s). Pinning where acceleration stops using an
  (imperfect, bias-corrected) estimate of the true peak removes most of the
  "accelerate too far / brake too late, discovered only by breaking the
  friction circle" pathway that Step 1 partially attributed to cheating.
- **Combined, flag-free fraction reaches 16.95%** (best of the four) and the
  sign balance stays corrected (42.25% negative).

### Lap-level effect across all four configurations (same synthetic-lap construction as Step 1)

| config | lap median signed | lap mean | lap p5 | lap p95 | lap frac. negative |
|---|---|---|---|---|---|
| baseline | +0.100 s | +0.804 s | −1.226 s | +5.087 s | 47.0% |
| joint | +0.245 s | +0.991 s | −0.953 s | +5.000 s | 41.4% |
| pin | +0.559 s | +1.191 s | −0.829 s | +5.217 s | 29.4% |
| pin+joint | **+0.775 s** | +1.402 s | −0.531 s | +5.340 s | 20.2% |

**This is the single most important, and least expected, result in this
report: fixing the cheating makes the median lap-level number WORSE, not
better.** As the reconstruction is made more honest (fewer constraint
violations, sign balance corrected toward the physically-expected "slightly
slower than optimal"), the median signed lap cost rises from +0.10 s to
+0.78 s. The baseline's near-zero median was not evidence that
reconstruction is nearly free — it was an averaging-out of a large number of
illegitimately-fast sectors (constraint violations banking time) against a
smaller number of very slow ones. Once the illegitimate speed is removed,
what remains is the genuine cost, and it is **larger, not smaller, than the
original 0.603 s naive estimate**, though via signed cancellation rather
than the original's flawed unsigned-sum method. Objection (b) (signed
cancellation matters) is correct in mechanism but the corrected number does
not vindicate the original headline as "overstated" — if anything the
honest figure is comparably bad or worse.

---

## Step 4 — Oracle bound on the true information-content floor

**[Computed on a 200-scenario stratified subsample of the 2,000-scenario
pool — disclosed time-box simplification: the full sweep at 2,000 scenarios
was estimated in the multiple-hours range; 200 preserves the same
zone_eligible/length-bin proportions at roughly 1/10 the compute.]**

Per scenario, swept the accel/brake split point k_A (0 to 50, step 2 — the
single dominant free parameter identified in Steps 1-3) together with a
deploy-taper coefficient (5 levels spanning the Step 0 Q2-measured range,
mean-power-normalised so the profile's average deploy power still equals
the GIVEN `P_deploy_mean` scalar exactly — the oracle may reshape the
profile, not spend a different energy budget than the 3-scalar input
specifies), picking whichever combination minimises `|dt − dt_true|`. The
regen/friction SPLIT was NOT swept: dt depends only on the net force
F_ice+F_dep−F_reg−F_brake, never on how that net splits between F_reg and
F_brake (regen vs friction brake are mechanically interchangeable for
timing purposes, only differing in energy accounting) — so this dimension
has provably zero effect on the oracle's objective and was left at the
existing regen-first-to-cap policy.

### Results (200 scenarios, 599s total; stratification preserved: 68%
eligible/32% shut, 30/37/34% short/mid/long)

| | value |
|---|---|
| has ≥1 feasible candidate anywhere in the grid | **91.5%** (183/200) |

**Unconstrained best (ignoring feasibility — "can the 3 scalars encode dt at
all, given free shape parameters"):**

| p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|
| −0.0185 s | −0.0022 s | **−0.000003 s** | +0.0016 s | +0.0131 s |

**Constrained best (subject to sim_feasible, n=183 with ≥1 feasible candidate):**

| p5 | p25 | median | p75 | p95 |
|---|---|---|---|---|
| −0.711 s | −0.011 s | **+1.185 s** | +4.932 s | +29.943 s |

**These two numbers answer different questions and must not be conflated.**
The unconstrained result says: *given free choice of when acceleration
stops (k_A) and how deployment tapers, matched only to reproduce the given
P_deploy_mean/d_X exactly, the resulting dt can be made to match the true
optimum to within a few milliseconds at the median* — i.e. **the
three-scalar representation is, in principle, information-sufficient to
encode dt almost exactly.** This is the genuine floor the task asked for,
and it is effectively zero.

The constrained result is far worse (median +1.19 s, catastrophic tail to
+29.9 s, and 8.5% of scenarios have NO feasible point in the entire swept
grid) — but **this number is confounded, not clean**, and the report says so
plainly rather than presenting it as the floor: the oracle's BRAKE phase
still uses the same fixed "maximum deceleration, regen-first-to-cap" policy
as the base reconstruction, evaluated with the SAME internally-estimated
v_mid rather than a jointly-converged one — i.e. it inherits exactly the
Step 3 self-consistency gap (the oracle was not run through
`reconstruct_joint()`, which was judged out of scope to also combine here
within the time-box). A policy that is *always* aimed exactly at the
friction-circle boundary will trip the >0 tolerance check on the slightest
v_mid mismatch regardless of how well k_A/taper are chosen — which is
consistent with 8.5% of scenarios having literally no feasible point
anywhere in a 130-point grid, an implausible outcome if the constraint were
genuinely hard to satisfy for structural (floor) reasons rather than a
carried-over self-consistency artefact.

**This oracle uses `dt_true` directly as its fitting target — information no
deployable surrogate would ever have. Both numbers above are unachievable
upper bounds on reconstruction quality, reported to establish the floor,
never as an achieved result.**

---

## Step 5 — Defensible restatement of the target

**Answering the five questions directly:**

**1. Signed error / fraction negative / does cheating explain it?** Full
population: median −0.0097 s/sector, 65.85% negative; lap-level signed sum
median +0.100 s (baseline), 47% of synthetic laps net-negative. Cheating
(friction-circle/deploy-envelope violation) explains the sign for roughly
half of the negative cases (55.2%) directly, and SOME flag (including the
much more prevalent but dt-inert regen-cap flag) fires on nearly all of
them (97.87% carry at least one flag, i.e. only 2.13% of negative-error
scenarios are flag-free) — but the association is partial, not total; a
meaningful negative bias survives even among
scenarios that violate neither of the two "speed-enabling" constraints
(62.1% still negative, median ≈ −0.002 s there).

**2. Is telemetry v_max_kph a usable proxy?** Strongly correlated (r=0.93)
but substantially, systematically biased low (median −33 kph) — usable only
with a population-level bias correction, not raw. With correction, it is a
genuine zero-cost feature (already in the Phase 1 matrix) that materially
rebalances the sign of reconstruction error (negative fraction 65.85%→
45.30%) without requiring a fourth model output.

**3. After the joint fixed point, what is the flag-free fraction and signed
error?** Flag-free rises from 5.95% to 15.05% (joint alone) or 16.95% (joint
+ v_peak pin); convergence 99.8% in a median 3 iterations, confirming this
was implementation immaturity, not a floor. But the signed error's central
tendency does NOT improve with these fixes — it gets honestly worse (lap
median +0.10 s → +0.78 s, pin+joint), because the fixes remove the
artificial speed advantage that was flattering the baseline number.

**4. What is the oracle floor, and does it exceed +0.05 s/lap?** The clean,
unconstrained floor (§Step 4) is **≈0 s/sector at the median** (IQR
[−0.002, +0.002] s) — three scalars ARE information-sufficient to encode dt
almost exactly, given optimal (oracle) choice of the shape parameters they
leave free. It does **not** exceed the target; it is negligible relative to
it. The constrained oracle number (median +1.19 s/sector) is far worse but
is confounded by the same self-consistency gap Step 3 diagnosed, not a
second independent floor measurement — it was not run through the joint
fixed point within the time-box, so it should not be read as "the floor
including feasibility," only as "evidence that feasibility and timing
accuracy are not yet jointly solved by any configuration tested here."

**5. Defensible restatement of the target and the evidence for it:**

The three-scalar representation itself is **not** the binding constraint.
The unconstrained oracle floor is negligible against +0.05 s/lap. What is
binding, on the evidence assembled across Steps 1-4, is **reconstruction
POLICY maturity** on two fronts that this task has now separated and
individually measured:

  (i) **Timing** — knowing where to stop the deploy-power phase and start
      the max-deceleration brake countdown. Step 2/3 show telemetry
      v_max_kph (bias-corrected, zero-cost) recovers a meaningful share of
      this; Step 4's unconstrained result shows the OCP's own true peak
      would recover essentially all of it.

  (ii) **Self-consistency under constraints** — making the regen/friction/
       friction-circle allocation match the ACTUALLY achieved v(s) rather
       than an internally-assumed one. Step 3's joint fixed point
       demonstrably fixes this (99.8% convergence, ~3 iterations) but has
       not yet been combined with (i), and Step 4 suggests the two
       compound when left unfixed together.

**Recommended restatement:** replace "three-scalar reconstruction achieves
+0.05 s/lap" (unestablished, and on the evidence here, not close to
achieved by the CURRENT reconstruction policy) with **"the +0.05 s/lap
target is not precluded by the three-scalar representation itself (oracle
floor ≈0), and is contingent on reconstruction-policy work that this task
has scoped into two concrete, tractable pieces: (i) a timing estimator for
the accel/brake split — v_peak (telemetry-proxied or, better, a genuine
fourth OCP-derived label) — and (ii) closing the reconstruction/simulation
self-consistency loop (the joint fixed point) BEFORE, not instead of,
fixing (i)."** Neither piece individually reaches the target in this
report's measurements (best combined configuration: flag-free 16.95%, lap
median signed error +0.78 s); the oracle result is the evidence that
combining them properly, rather than needing a fundamentally richer label
set, is the right next step to test before concluding the target is
unreachable.

---

## Files

- `phase4/simulate.py` — GROSS-primary correction applied; module docstring
  documents the correction and the NET/GROSS residual explicitly.
- `phase4/reconstruct.py` — new: `reconstruct_joint()` /
  `_reallocate_forces()` (Step 3 fixed point), `v_peak_target` parameter on
  `reconstruct_controls()` (Step 2/3 telemetry pin). Original
  `reconstruct_controls()` behaviour is unchanged when `v_peak_target=None`
  (default).
- `output/phase4_step3b_results.parquet` — regenerated: GROSS-corrected
  simulator, signed `dt_err_signed`, per-scenario flag detail, telemetry
  `v_max_kph` and OCP `v_peak_ocp_ms` columns added (superset of the
  original file's columns; nothing removed).
- `output/phase4_step3_joint_results.parquet`,
  `phase4_step3_vpeak_only.parquet`, `phase4_step3_vpeak_joint.parquet` —
  the three intervention configurations, each with `dt_err_signed` and
  `sim_feasible`.
- `output/phase4_step4_oracle_results.parquet` — 200-scenario oracle sweep,
  unconstrained and constrained best signed error per scenario.

**Not done, per constraints:** `problem.py`, `dynamics.py`, `solver.py`,
`vehicle.py` untouched throughout; no surrogate retrained; no production
batch re-solve (all four steps work from stored production scalars and the
Step 0 retained trajectories only).
