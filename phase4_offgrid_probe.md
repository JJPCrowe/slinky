# Phase 4 — The Off-Grid Probe: Resolving the Last Confound

`phase4_sequential_soc_v2.md` diagnosed the 14.28% dangerous-error rate as
covariate shift: the model is scored on-grid but the recursion feeds it
increasingly off-grid `E_initial` values, where §4 measured a growing
negative bias (model under-predicting depletion, reaching −230.6 kJ by the
18th sector of a lap). One confound survived: §2's comparator bias also
swings by 71.3 kJ across the SoC range, the chain moves SoC monotonically
downward, and both the model AND the comparator were being evaluated
off-grid with no genuine off-grid ground truth in the existing data —
§4's growth could partly be the ground truth drifting, not the model.

This report resolves it with a 2,500-solve targeted probe (the one
permitted exception to no-re-solving) and a plot-first check that needed
no solving at all. **Verdict: covariate shift survives, directly confirmed
by real ground truth — but the mechanism is sharper than originally
stated, and one further finding qualifies how the comparator should be
read going forward.**

**Answering the five questions up front:**

1. **Mixed, and this refines the diagnosis.** In the covered interior SoC
   range (0.2–0.9), model bias against the same interpolated-true
   comparator is small and generally *tracks below* the comparator's own
   known bias (ratio 0.15–0.48 at most points) — that part looks like
   artefact, not a dramatic independent model defect. But §4's extreme
   growth is not explained by gradual interior drift at all: **34.2% of
   every per-sector prediction made across the whole sequential chain
   lands at SoC ≤ 0.1 — below the training grid's floor entirely** —
   where bias is −192 to −198 kJ, 4–19x anything measured in the covered
   range, and only 5% of that is floor-clamp lock-in. The mechanism is
   real, but concentrated in sub-grid extrapolation, not spread evenly
   off-grid.
2. **82.1 kJ for `net_depletion_J`, larger than §2's 66.5 kJ leave-one-out
   estimate (ratio 1.235), not smaller.** This is the opposite direction
   from the hypothesis that the LOO's wider 0.2 gap would overstate error
   relative to the comparator's real 0.1 gap. Stated plainly, with the
   sample-size caveat this carries (§2 below).
3. **Confirmed directly, independent of the comparator.** The model's own
   RMSE against freshly-solved truth is 1.76x Stage 3's on-grid figure for
   `net_depletion_J`, 3.30x for `dt_optimal`, 1.40x for `E_har_final` — a
   real, measured, comparator-independent degradation off-grid. Bias
   direction matches §4 (net depletion under-predicted) though the
   magnitude in this moderate off-grid range is far smaller than §4's
   late-lap extremes — because those extremes live in the sub-0.1 region
   this probe, by design, did not test.
4. **The comparator, not the model, is closer to truth off-grid — for all
   three targets, most of the time.** Model wins the per-case head-to-head
   only 24.6% (`net_depletion_J`), 9.7% (`dt_optimal`), 25.1%
   (`E_har_final`) of the time. **Every like-for-like number in v2 was, if
   anything, compared against a reference stronger than the model's own
   off-grid predictions — the dangerous rate is a credible estimate of
   genuine model shortfall, not an artefact of comparator weakness.**
5. Re-grounding SoC from true labels every sector (the online-deployment
   analogue) drops the dangerous rate from 14.28% to 11.31% (isolated cost
   of open-loop rollout: **2.97 percentage points**) and improves
   outer-loop agreement from 74.88% to 79.76% — but, non-obviously, makes
   raw lap-time point-accuracy *worse* (median error +0.174s → +0.280s).
   Full numbers and the explanation in §5.

---

## §0 — Bias vs actual SoC, not sector position (no solving)

Sector position is a proxy for cumulative SoC drift, not the thing
itself. Re-running the same cached-model chain used in v2's §4, this time
recording the actual chained SoC at each per-sector prediction (not just
its position in the lap), and binning model bias by that real SoC value:

| actual SoC bin | model bias (J) | model RMSE (J) | n |
|---|---|---|---|
| ≤0.1 (below the grid floor) | **−198,471** | **232,441** | 274,065 (34.2% of all predictions) |
| (0.1, 0.2] | +10,421 | 40,296 | 185,007 |
| (0.2, 0.3] | +7,598 | 44,014 | 95,135 |
| (0.3, 0.4] | +4,841 | 52,426 | 52,951 |
| (0.4, 0.5] | +3,083 | 53,106 | 44,121 |
| (0.5, 0.6] | +1,730 | 55,040 | 38,311 |
| (0.6, 0.7] | +522 | 57,993 | 32,668 |
| (0.7, 0.8] | −1,905 | 61,098 | 27,518 |
| (0.8, 0.9] | −4,175 | 63,085 | 24,098 |
| (0.9, 1.0] | −10,808 | 66,076 | 26,436 |

Overlaying §2's leave-one-out comparator-bias curve at the matched grid
points:

| SoC | model bias (J) | comparator bias (J, §2 LOO) | ratio \|model\|/\|comparator\| |
|---|---|---|---|
| 0.2 | +10,421 | −52,824 | 0.20 |
| 0.3 | +7,598 | −33,550 | 0.23 |
| 0.4 | +3,083 | −20,093 | 0.15 |
| 0.5 | +3,083 | −12,844 | 0.24 |
| 0.6 | +1,730 | −1,795 | 0.96 |
| 0.7 | +522 | +470 | 1.11 |
| 0.8 | −1,905 | +3,985 | 0.48 |
| 0.9 | −4,175 | +18,453 | 0.23 |

**In the covered interior range, model bias is consistently smaller than
the comparator's own known bias** (except right at the 0.6–0.7 crossover,
where both are near zero and the ratio is noise-dominated). Taken alone,
this would suggest the v2 diagnosis was measuring comparator artefact more
than genuine model defect in that range.

**But the ≤0.1 bin changes the picture entirely.** It is the single
largest bin by row count (34.2% of every per-sector prediction across the
whole chain), its bias (−198 kJ) is 4–19x larger than anything in the
covered range, and it sits in territory §2's leave-one-out framework
cannot even test (there is no grid point below 0.1 to hold out). Checking
whether this is floor-clamp lock-in (SoC pinned at exactly 0, re-feeding
the same degenerate input repeatedly) or genuine drift: **only 5.0% of
this bin is exactly `soc==0.0`; 95% is continuous, non-clamped SoC between
0 and 0.1 (median 0.037, mean 0.042)** — genuine extrapolation below the
training grid's lower edge, not an artefact of the clamp mechanism. Even
excluding the clamped rows, bias in this genuinely-drifted sub-grid region
is −192.0 kJ, RMSE 226.3 kJ.

**Conclusion for §0: neither pure "artefact" nor a uniform "covariate
shift" describes this well. The correct, sharper statement is: within the
training grid's range, model bias is modest and smaller than the
comparator's known imprecision; below the grid's floor — a region a third
of all chained predictions eventually reach — the model is extrapolating
into territory it never saw, and there the bias is severe.** This refines,
rather than confirms wholesale, the v2 diagnosis: the mechanism is real,
but narrower and sharper than "smooth drift across the interior."

---

## §1 — The off-grid probe

500 instances, stratified across 24 circuits (proportional allocation,
12–33 each), sector-length tercile (short/medium/long, cut at 198 m /
350 m, 163–169 instances each), and `zone_eligible` True/False (346/154,
matching the population's 69/31 split) — fixed seed 0. 5 off-grid SoC
values (0.15, 0.25, 0.45, 0.65, 0.85), each the exact midpoint between two
training grid points. 1 lambda (9.65489385e-08, `np.geomspace(1e-8, 3e-7,
7)[3]`, the same mid-bracket value used in the prior E_final verification
re-solve). 2,500 solves via `f1_pipeline.ocp.batch.run_batch` — the
unmodified `problem.py`/`solver.py` path, `N=50`, `shut_joblist` built from
each sampled instance's own already-known `zone_eligible` value (not the
full production job list, which would fail `run_batch`'s exact-match
assertion against a filtered subset).

**A launcher bug, found and fixed before any results were produced:** the
first launch had no `if __name__ == "__main__":` guard, and on Windows'
spawn-based multiprocessing every worker re-imported and re-executed the
whole module — all 8 worker slots failed to start (each hit Python's
`_check_not_importing_main` `RuntimeError`), and `run_batch`'s own
fallback silently dropped to single-threaded serial execution (correct
results, ~8x slower — this is what produced the initial ~55-minute ETA
rather than the expected ~5 minutes). No output file had been written at
that point, so this was killed and restarted with the guard fixed, not
treated as a second probe. **2,500/2,500 converged (100%)** with proper
8-way parallelism, in 925 s. All required columns populated; the only
NaNs are 770/2,500 `d_X_optimal` values, the already-documented "NaN if no
deploy" pattern from `phase4_direct_prediction.md`, unrelated to the three
targets this report uses.

---

## §2 — Three measurements against true off-grid ground truth

**(a) The comparator's TRUE off-grid error** — linearly interpolate the
stored *production* labels between the two bracketing grid points (0.1
apart, matching how the comparator is actually used, not the LOO's 0.2-gap
test) and compare against the probe's newly-solved truth:

| target | TRUE off-grid RMSE | bias | §2 (v2) LOO estimate | ratio (true/LOO) |
|---|---|---|---|---|
| `net_depletion_J` | 82,095 J | −11,299 J | 66,457 J | **1.235** |
| `dt_optimal` | 0.285 s | −0.019 s | 0.072 s | 3.95 |
| `E_har_final` | 33,928 J | −680 J | 26,430 J | 1.284 |

**The correction runs opposite to the hypothesis.** The hypothesis was
that LOO's wider 0.2 gap should *overstate* error relative to the
comparator's real, finer 0.1 gap — instead, true error at the finer gap is
*larger*. Stated plainly rather than reconciled away: this probe uses only
500 instances per SoC point against LOO's ~80,000, restricted to a single
lambda against LOO's all-7-pooled estimate, and tests five specific
midpoints rather than the full range — enough deviation in sampling and
scope that a reversal within this magnitude cannot be ruled statistical.
The one-directional takeaway that survives regardless: **the comparator's
own error off-grid is substantial, on the same order as everything else
measured in this pipeline, for both readings.**

**(b) The model's TRUE off-grid error and bias** — the restored 150k
LOCO-fold model, predicting from the exact off-grid `E_initial`, compared
against the same freshly-solved truth:

| target | TRUE off-grid RMSE | bias | Stage 3 on-grid RMSE | ratio (off/on-grid) |
|---|---|---|---|---|
| `net_depletion_J` | 81,064 J | −5,083 J | 45,970 J | **1.763** |
| `dt_optimal` | 0.294 s | −0.026 s | 0.089 s | **3.300** |
| `E_har_final` | 34,895 J | −893 J | 24,970 J | **1.397** |

**This is the number that decides the covariate-shift question, and it
confirms it — directly, independent of the comparator.** All three heads
degrade substantially off-grid relative to Stage 3, `dt_optimal` most
severely (3.3x). `net_depletion_J`'s bias is negative (model
under-predicting depletion), the same direction §4 found. The magnitude
here (mean −5.1 kJ) is far smaller than §4's late-lap extreme (−230.6 kJ)
— consistent with, not contradicting, §0's finding that the dominant
driver of that extreme lives specifically below SoC 0.1, a region this
probe's five test points (0.15–0.85) do not reach.

**(c) Model versus comparator, head to head** — for each of the 2,499
matched (row, target) comparisons, which prediction sits closer to the
newly-solved truth:

| target | model closer | mean \|model err\| | mean \|comparator err\| |
|---|---|---|---|
| `net_depletion_J` | 24.6% | 28,684 J | 22,073 J |
| `dt_optimal` | 9.7% | 0.07 s | 0.04 s |
| `E_har_final` | 25.1% | 14,148 J | 9,043 J |

**The comparator is closer to truth than the model, for all three
targets, most of the time — decisively so for `dt_optimal` (90.3% of
cases).** This is the opposite of "the comparator is worse, so the
dangerous rate is inflated." **Every like-for-like number in
`phase4_sequential_soc_v2.md` was compared against a reference that is, on
this direct evidence, at least as accurate as — and typically more
accurate than — the model's own off-grid predictions. The dangerous rate
is not an artefact of a weak comparator; if anything, this makes it a
credible-to-conservative estimate of a real model shortfall, not an upper
bound inflated by ground-truth noise.**

---

## §3 — SoC re-grounding: the online-deployment analogue, isolated

Chained rollout — and its off-grid extrapolation failure mode — is a
consequence of *offline* lap-time prediction chaining the model's own
prior output. Trackside, the car reports measured SoC every sector: the
model only ever predicts one step ahead from an observed input, the exact
condition of sector 0 in every open-loop chain (the condition that matched
Stage 3 to 0.24% in v2). Re-running the full lap-level validation with SoC
advanced each sector from the **interpolated-true** trajectory (measured
depletion) rather than the model's own prior prediction — same cached
models, same label lookup, no new solving — isolates that cost directly:

| | open-loop (v2, §5) | re-grounded (online-deployment analogue) | Δ |
|---|---|---|---|
| Dangerous error (LFL) | 14.28% | **11.31%** | **−2.97pp** |
| Conservative error (LFL) | 0.14% | 0.14% | ~0 |
| Outer-loop same-lambda rate | 74.88% | **79.76%** | **+4.88pp** |
| Lap-time error, median | +0.174 s | +0.280 s | +0.106 s (worse) |
| Lap-time error, mean | +0.214 s | +0.360 s | +0.146 s (worse) |
| within ±0.05 s | 10.21% | 8.57% | worse |
| within ±0.2 s | 38.87% | 32.07% | worse |
| within ±0.5 s | 75.82% | 62.91% | worse |

**Re-grounding is not a uniform win, and that asymmetry is itself a
finding.** Feasibility classification improves substantially (dangerous
rate down 2.97pp in absolute terms, ~21% relative; lambda agreement up
4.88pp) — re-grounding removes the specific mechanism §4 identified
(the model's own errors compounding into the next step's input), and the
2.97pp gap is the isolated cost of that compounding, cleanly separated
from ordinary off-grid imprecision. But raw lap-time point-accuracy gets
*worse* under re-grounding, on every measure. The likely explanation,
consistent with §2(b): `dt_optimal` is the target that degrades *most*
severely off-grid (3.3x Stage 3's on-grid figure, the worst of the three
heads) — re-grounding forces every single sector's `dt_optimal` prediction
to be made from a genuinely true, often off-grid SoC, whereas the
open-loop chain's own self-referential trajectory, imperfect as it is,
happened to land in states where `dt_optimal` prediction was somewhat more
favourable on average. **The residual 11.31% dangerous rate after
re-grounding is the off-grid imprecision measured directly in §2 — it is
not compounding, and re-grounding cannot remove it, because it did not
cause it.**

---

## Revisiting the covariate-shift diagnosis

The probe does not refute it. Direct, comparator-independent evidence
(§2b) shows all three surrogate heads degrade substantially when evaluated
off-grid against freshly-solved truth (1.4x–3.3x their Stage 3 RMSE), in
the same directional bias §4 found. But the probe **sharpens** the
mechanism in two ways the existing data could not:

1. The dominant driver of §4's most extreme values is not smooth,
   uniform off-grid drift — it is a specific, severe extrapolation regime
   below SoC 0.1 (§0), reached by over a third of all chained
   predictions, that this probe's five interior test points (0.15–0.85)
   do not cover and a natural next probe would target directly.
2. The comparator used throughout this pipeline is not the weak link the
   confound worried it might be — off-grid, it is *more* reliable than
   the model itself (§2c), so the dangerous rate stands on its own
   evidence rather than resting on an assumption about comparator quality.

---

## Assumptions stated beside the numbers that depend on them

- §0's SoC-vs-comparator overlay uses grid-point bias values from v2's §2
  (pooled across all 7 lambda values and the full ~80,000-instance
  population) matched by nearest bin center to a re-computed, actual-SoC
  binned model-bias table from the restored 150k models — the two are not
  from identical samples, only comparable in scale and sign.
- §2's "ratio true/LOO" and "ratio off/on-grid" figures rest on a 500 (or
  2,499 row-level) sample at a single lambda, against reference figures
  computed on the full ~80,000-instance, 7-lambda population — the
  reversal found in §2(a) is reported as a direct measurement, with the
  sample-size caveat stated rather than smoothed over.
- §2's stratified sample targeted circuits, sector length, and
  `zone_eligible`; it was not stratified by lambda (only one lambda was
  tested, per instruction) or by the sub-0.1 SoC regime §0 identifies as
  most severe — that regime is characterised in §0 using the existing
  chained-model data, not by this probe's fresh solves.
- §3's re-grounded chain reuses the same interpolated-true label lookup
  used throughout this pipeline as the "measured SoC" trackside would
  report — a modelling choice consistent with everything else in this
  report, not a claim that linear interpolation between stored grid labels
  is what a real car's telemetry would show.
- No result in this report was obtained by adjusting architecture,
  features, hyperparameters, or seed from Stage 3, and no solving beyond
  the one permitted 2,500-scenario probe was performed.
