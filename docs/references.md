# References — Phase 2 Parameter Sources (Rev 2)

Bibliography for citations used in `vehicle_parameters.md`. Harvard-style
entries matching the project proposal §9. Web sources accessed 2026-06-10
unless noted.

---

## Regulatory / Tier 1

**FIA_2026_REG** — Fédération Internationale de l'Automobile. *2026 Formula 1
Technical Regulations.* FIA Document Centre. Primary regulatory source for
mass, power-unit limits, energy store capacity, harvest allowance, and
dimensional constraints. **Open action: cite exact article numbers for the
deployment-envelope and harvest-allowance clauses from the published PDF
before methods freeze (currently bridged by the secondary sources below).**

**F1COM_REFINEMENTS** — Formula1.com (Apr 2026). *Refinements to 2026 F1
regulations agreed by all stakeholders.* 350 kW deployment zones, 250 kW
out-of-zone limit. https://www.formula1.com/en/latest/article/refinements-to-2026-f1-regulations-agreed-by-all-stakeholders.1xA0TRau0DvyId6R7oZjFv

**F1COM_PU** — Formula1.com. *Explained: 2026 power unit regulations.*
Deployment taper 290 km/h → zero at 355 km/h; override envelope.
https://www.formula1.com/en/latest/article/explained-2026-power-unit-regulations-fia.68izKQ2tn1voQPWvgLVMXN

**MCLAREN_2026** — McLaren Racing. *Explaining F1's new 2026 regulations.*
Normal-mode taper begins 290 km/h; override 350 kW to 337 km/h.
https://www.mclaren.com/racing/formula-1/2026/explaining-f1s-new-2026-regulations/

**RACETEQ_2026** — Raceteq (May 2026). *F1's 2026 energy system explained.*
Harvest allowance range 5–9 MJ by circuit after May refinement.
https://www.raceteq.com/articles/2026/05/f1s-2026-energy-system-explained

**ESPN_2026** — ESPN. *2026 F1 rules: what's new.* 4 MJ usable store,
350 kW recovery rate, ICE ~400 kW.
https://www.espn.com/racing/f1/story/_/id/48090668/2026-f1-rules-whats-new-cars-how-changes-affect-racing

**F1CHRON** — F1 Chronicle. Fuel flow 3000 MJ/h ≈ 70 kg/h; 768 kg minimum.
https://f1chronicle.com/f1-fuel-flow-2026-explained/ ;
https://f1chronicle.com/f1-minimum-weigh-2026/

**GPFANS_DIM** — GPFans. Dimensions and tyre widths (3400 mm wheelbase,
1900 mm width, 275/375 mm tyres).
https://www.gpfans.com/en/f1-news/1077532/f1-car-size/

## Tier 2 anchors

**PACEJKA** — Pacejka, H. B. (2012). *Tire and Vehicle Dynamics* (3rd ed.).
Butterworth-Heinemann. Textbook anchor for peak longitudinal friction of
racing slicks (μ band 1.5–1.7 used in LTS practice).

**ISA** — ISO 2533:1975 — *Standard Atmosphere.* Sea-level air density
reference (1.225 kg/m³).

## Tier 3 derivation anchors

**MAXTAYLOR_LTS** — Taylor, M. (2023). *Estimating F1 Aero Coefficients
with Lap Simulation.* maxtayloraero.com. Establishes the A = 1 m²
normalisation convention; LTS-derived ground-effect-era ClA/CdA bands.
https://maxtayloraero.com/2023/02/27/estimating-f1-aero-coefficients-with-lap-simulation/

**GPFANS_DELTAS** — GPFans. *F1 2026 regulations explained.* Regulated 2026
aero deltas: downforce −15…−30%, drag −40…−55%.
https://www.gpfans.com/en/f1-news/1077929/f1-2026-regulations-explained/

**F1DICT_AERO** — formula1-dictionary.net. *F1 aerodynamics.* Published Cd
band 0.7–1.1 with unspecified reference areas — context for the Option A
unit-area defence.
https://www.formula1-dictionary.net/f1-aerodynamics/

## Proposal-cited literature (roles updated in Rev 2)

**BUCK_2023** — Buck, P. d., & Martins, J. R. (2023). *Minimum lap time
trajectory optimization of performance vehicles with four-wheel drive and
active aerodynamic control.* Friction-circle treatment underlying the
longitudinal OCP formulation. (No longer the aero-coefficient source.)

**ELBAL_2024** — Elbal, A. J., Conde, A. Z., & Siampis, E. (2024). World
Electric Vehicle Journal. Direct-collocation co-optimisation precedent.
(No longer the Z-mode aero source — superseded by the Rev 2 derivation.)

**KAJIWARA_2026** — Kajiwara, S., & Tom, C. (2026). Fluids. ML-surrogate
aero precedent. (No longer the X-mode aero source — superseded.)

**FIENI_2026** — Fieni, G., et al. (2026). IEEE Trans. Vehicular Technology.
Deployment-taper interaction with drag; battery-capacity context.

**ZHU_2024** — Zhu, Q., et al. (2024). IEEE Trans. Transportation
Electrification. Tree-based surrogates approximating NLP solvers; η_k
efficiency context.

---

## Notes for thesis writing

- Secondary web sources above bridge to the FIA primary text; replace with
  FIA article-number citations before the methods chapter freezes.
- Where the Rev 2 aero derivation departs from proposal-cited literature
  values, the methods chapter should state the derivation chain
  (ground-effect LTS baseline × regulated 2026 deltas) and reference the
  sweep ranges as the uncertainty statement.
