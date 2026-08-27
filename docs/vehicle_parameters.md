# Vehicle Parameter Worksheet — Phase 2 OCP (Rev 2 merged)

**Status:** Tier 1, Tier 2, and Tier 3 all locked (Rev 2, 2026-06-10). This file
is the canonical parameter record; values here match the defaults in
`f1_pipeline/ocp/vehicle.py`. The Rev 2 consolidation also identified one
previously-missing Tier 1 constraint (the regulatory deployment-speed
envelope), now implemented in `problem.py`.

- **Tier 1** — FIA-regulated, confirmed against the 2026 Technical
  Regulations (revisions through May 2026). Use directly.
- **Tier 2** — Not regulated; modelling choices defensible from standard
  lap-time-simulation (LTS) literature.
- **Tier 3** — Aerodynamics: locked central values, derived not measured.
  Designated sensitivity-sweep set.

---

## Resolved conventions

**Aero parameterisation (Option A — unit reference area).** The code carries
separate `cd`, `cl` with explicit `frontal_area`. Since aerodynamic forces
depend only on the products CdA and ClA, and no standardised reference area
exists for F1, coefficients are normalised to A = 1.0 m². Quoted Cd/Cl values
are numerically equal to the area-integrated CdA/ClA in m², matching the
public LTS estimates they derive from. `frontal_area = 1.0` is a
normalisation, not a physical area estimate.

**Lift sign.** Cl is negative for downforce. The friction-circle normal load
reads `N = m·g − F_lift`, so negative F_lift increases N.

**Aero state blending.** Cd(a), Cl(a) interpolate linearly between Z (a = 0)
and X (a = 1). Linearity in Cd/Cl ≡ linearity in CdA/ClA at fixed A, so the
convention does not interact with the sigmoid relaxation of the switch.

**SoC normalisation.** SoC scales against `e_batt_capacity` (4 MJ storage),
never against the per-lap harvest figure.

---

## Tier 1 — FIA-regulated (confirmed)

| ID    | Symbol / attribute  | Value        | Unit | Notes |
|-------|---------------------|--------------|------|-------|
| VP-01 | `mass_total`        | 768          | kg   | 2026 minimum incl. driver, dry. Qualifying fuel adds ~5–10 kg (≈1%); treated as a remark, not a parameter. |
| VP-03 | `wheelbase`         | 3.4          | m    | Context only; unused in longitudinal model. |
| VP-11 | `p_ice_max`         | 400 000      | W    | Consequence of 3000 MJ/h fuel-energy-flow cap (~70 kg/h). Modelled as a power bound, not fuel mass flow. Treated as wheel-equivalent (see caveat under §Envelope). |
| VP-12 | `p_mguk_max`        | 350 000      | W    | Deployment peak, corner-exit → braking point — the full span of an apex-to-apex micro-sector. 250 kW out-of-zone limit is outside scope. |
| VP-20 | `p_regen_max`       | 350 000      | W    | Regen (harvest-rate) peak, all speeds. Regen cap < braking-power demand on high-speed decel is the physical justification for the friction-brake actuator. |
| VP-21 | `v_env_full`        | 290/3.6 ≈ 80.56 | m/s | Deployment envelope knee: full 350 kW available at or below 290 km/h. |
| VP-22 | `v_env_zero`        | 355/3.6 ≈ 98.61 | m/s | Deployment envelope zero: deployment reaches 0 at 355 km/h. Linear taper assumed between endpoints — **verify exact piecewise clause against the FIA 2026 Technical Regulations (power-unit articles) before methods freeze.** Override mode (350 kW to 337 km/h) excluded: race-tactical, unavailable in qualifying. |
| VP-14 | `e_batt_capacity`   | 4 000 000    | J    | Usable storage; SoC normaliser. Stock, not flow. |
| VP-13 | `e_lap_harvest_max` | 8 500 000    | J    | Per-lap harvest allowance, baseline. May 2026 refinement: FIA-adjustable 5 MJ (Monza) … 9 MJ (Monaco/Hungary). **Documentation-only — not enforced** (see constraint registry). |
| VP-19 | `fuel_energy_flow_max` | 833 333   | W    | 3000 MJ/h energy-flow limit; documentation. |
| —     | width / tyre widths | 1900 / 275 / 375 | mm | Context only. |

---

## Tier 2 — Standard physics / LTS literature (confirmed)

| ID    | Attribute        | Value | Unit  | Basis |
|-------|------------------|-------|-------|-------|
| —     | `g`              | 9.81  | m/s²  | — |
| VP-08 | `air_density`    | 1.225 | kg/m³ | ISA sea level, 15 °C. Altitude correction (Mexico City class) deferred. |
| VP-09 | `mu_long`        | 1.50  | —     | LTS convention range 1.5–1.7. Reduced from 1.70 in prior revision — smoke test required. |
| VP-10 | `c_rolling`      | 0.012 | —     | Small vs aero; 0.01–0.02 range. |
| VP-17 | `eta_driveline`  | 0.95  | —     | Common LTS value. **Documented, not applied** — P_max values treated as wheel-equivalent. |
| VP-15/16 | `eta_motor` / `eta_regen` | 0.95 | — | Per-direction η_k; round-trip ≈ 0.90. **Documented, not applied** in `dynamics.dE_ds` (unity efficiency); piecewise sign-dependent application flagged as future work. |
| VP-18 | `wheel_radius`   | 0.36  | m     | Needed only if torque-based. |

---

## Tier 3 — Aerodynamics (LOCKED central values + sweep ranges)

Lowest-confidence tier: teams publish neither CdA/ClA nor frontal area, and
no public measurements of 2026 cars exist. Values are **derived, not
measured**. Derivation: ground-effect-era (2022–25) public LTS-derived
estimates (lap-average ClA ≈ 5.0–5.5 m², CdA ≈ 1.0–1.2 m²) with the
regulated 2026 deltas applied — downforce −15…−30% (Z config), drag up to
−40…−55% (headline figure, dominated by the X-mode straight-line case) —
noting X-mode flattens wing load while underfloor load persists.

| Mode | Attribute | Central | Sweep range | Unit (≡ CdA/ClA, m²) |
|------|-----------|---------|-------------|----------------------|
| Z drag | `cd_z` | 1.00  | 0.90 – 1.10   | m² |
| Z lift | `cl_z` | −4.00 | −3.50 – −4.50 | m² |
| X drag | `cd_x` | 0.65  | 0.55 – 0.70   | m² |
| X lift | `cl_x` | −2.00 | −1.50 – −2.50 | m² |
| Frontal area | `frontal_area` | 1.00 | fixed | m² (normalisation) |

**Revisions vs prior working figures** (cl_z: −3.5 → −4.0; cl_x: −1.5 →
−2.0): cl_z re-anchored to the ground-effect baseline minus the regulatory
cut (lands 3.9–4.7; 3.5 was a floor, not a central). cl_x raised because
X-mode disables wing load only; retained floor load makes ~50% of Z more
physical than ~40%. cd values unchanged.

**Sanity checks at central values (m = 768 kg, μ = 1.50), reproduced
against `vehicle.py`/`dynamics.py` 2026-06-11:**
- Peak braking from 320 km/h (Z): N = 26.9 kN → friction-only decel 5.35 g.
  Consistent with F1 peak braking (5–6 g).
- Corner-exit traction crossover (Z): grip-limited below ≈ 152 km/h,
  power-limited above. Realistic.
- ICE-only terminal velocity (X-mode, deployment = 0, wheel-equivalent
  400 kW): **357.8 km/h** — slightly above the 355 km/h envelope zero.
  See envelope caveat below.

**Treatment:** the four aero parameters are the designated
sensitivity-sweep set for the dissertation. If a tuning pass is performed,
tune CdA_x against observed 2026 terminal speeds first (best-conditioned),
then ClA_z against high-speed-corner minimum speeds.

---

## Constraint registry — enforced vs documented-only

| Constraint | Status |
|---|---|
| \|P_mguk\| instantaneous: deploy ≤ 350 kW, regen ≤ 350 kW | **Enforced** (split bounds; envelope on deploy side only) |
| Deployment-speed envelope (290 → 355 km/h linear taper) | **Enforced** (Rev 2) — intersection of two linear inequalities in `problem.py`; no fmin/fmax, IPOPT-safe |
| E_batt ∈ [0, 4 MJ] (storage) | **Enforced** |
| Per-lap harvest allowance (5–9 MJ) | **Documented-only — deferred to Phase 4.** Requires lap-context features absent from the Phase 1 matrix. Distance-pro-rated per-sector cap considered and rejected: harvest concentrates in braking zones, so a uniform cap binds heavy-braking sectors incorrectly and sits slack on straights, distorting labels worse than no cap. Consequence: aggregate per-lap harvest may exceed the circuit allowance, so regen-heavy labels are mildly optimistic on harvest-restricted circuits. `E_harvest_optimal` is now extracted per scenario so this can be quantified post-hoc. |
| 250 kW out-of-zone deployment limit | **Out of scope** — micro-sectors span the 350 kW zone. |

**Envelope caveat (corrected from Rev 2 §7).** Above `v_env_zero` the taper
bound goes negative, mandating a small forced harvest rather than merely
zero deployment. Rev 2 marked this region "unreachable in practice"
(ICE-only terminal ~354 km/h) — that figure assumes driveline efficiency on
the ICE. In our wheel-equivalent formulation (η_driveline not applied),
ICE-only terminal is **357.8 km/h > 355 km/h**, so the region IS reachable
at the end of the longest straights. Quantified effect: equilibrium settles
at ~356.1 km/h with ~5.8 kW forced harvest (≈1.5% of drag force there). The
artifact is conservative — it under-deploys, never over-deploys, and cannot
produce regulation-violating labels. Documented; no code guard added.

---

## Label extraction (Rev 2)

The slope-based `v_taper_optimal` produced pathological values (|slope| up
to ~5×10⁶ W·s/m) on short or narrow-velocity-range deployment phases in the
placeholder full batch. Revised label set extracted per scenario:

| Label | Definition | Notes |
|---|---|---|
| `d_X_optimal` | first 0.5-crossing of a(s) | unchanged; NaN = X never engaged (valid) |
| `v_taper_optimal` | linear dP/dv slope over deployment | **guarded**: NaN unless ≥5 deploying intervals AND ≥5 m/s velocity span |
| `P_deploy_mean_optimal` | mean MGU-K power over deployment time | robust primary replacement for the taper |
| `E_deploy_optimal` | total energy deployed (J) | additive; energy-budget friendly |
| `E_harvest_optimal` | total mechanical energy regenerated (J) | enables post-hoc harvest-allowance audit |
| `E_final` | terminal battery energy (J) | enables any post-hoc energy accounting |
| `d_coast_optimal` | trailing contiguous regen distance | unchanged |
| `dt_optimal` | sector traversal time | unchanged |

With the envelope enforced, deployment taper on >290 km/h sectors now
correctly separates into the economic taper (drag-wall) and the regulatory
envelope, rather than conflating them.

---

## Model extensions made during scaffold debugging

- **Friction brake actuator (F_brake).** Non-negative dissipative control
  alongside the MGU-K. Enters dv/ds and the friction circle; not dE/ds.
  Physically necessary, not numerical convenience: regen is capped at
  350 kW, so heavy-decel sectors exceed what the MGU-K can absorb
  regardless of battery state. Tie-break regularisation 1e-9·F_brake²
  prefers regen wherever feasible.

- **Aero coupling into the friction circle.** Traction limit
  μ·(m·g − F_lift(v, a)) rather than μ·m·g. Without it the OCP had no
  reason to hold Z-mode at corner exit and d_X collapsed to ≈0. Remains
  within longitudinal-only scope: only the longitudinal effect of aero on
  tyre normal load is modelled.

- **Aero starts in Z-mode (a(0) = 0).** Sector begins at the apex in
  high-downforce configuration, matching driver workflow.

- **Regulatory deployment-speed envelope (Rev 2).** Two linear upper
  bounds on P_mguk whose intersection reproduces the piecewise 290→355
  km/h taper without non-smooth operators.

---

## Sources

Tier 1 figures cross-checked across (accessed 2026-06-10): formula1.com
"Refinements to 2026 F1 regulations" (Apr 2026) and "Explained: 2026 power
unit regulations" (deployment taper 290→355 km/h, override envelope);
mclaren.com "Explaining F1's new 2026 regulations"; raceteq.com "F1's 2026
energy system explained" (May 2026 harvest range 5–9 MJ); ESPN "2026 F1
rules" (4 MJ store, 350 kW recovery, ~400 kW ICE); f1chronicle.com (3000
MJ/h fuel flow, 768 kg minimum); GPFans (dimensions, tyre widths). Full
URLs in `references.md`.

Tier 3 derivation anchors: maxtayloraero.com "Estimating F1 Aero
Coefficients with Lap Simulation" (A = 1 m² convention; LTS-derived ClA
bands); GPFans 2026 deltas (downforce −15…−30%, drag −40…−55%);
formula1-dictionary.net Cd band 0.7–1.1 (context for Option A defence).

**Primary-source action (open):** before the methods chapter freezes,
transcribe the exact deployment-envelope clause and harvest-allowance
clause from the published FIA 2026 Technical Regulations PDF and cite
article numbers directly rather than the secondary sources above.

---

## Workflow for any future parameter change

1. Update the value here AND in `vehicle.py` (they must match).
2. Re-run `python run_ocp.py --limit 200` and compare convergence rate and
   `dt_optimal` distribution against the previous revision.
3. Note any >5% shift in `dt_optimal` for the methods chapter.
4. Full batch re-run only after the smoke test is clean.
