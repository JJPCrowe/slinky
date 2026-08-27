"""
Vehicle parameters for the 2026 F1 longitudinal OCP.

Every value here is a PLACEHOLDER drawn from public estimates and the
2026 FIA Technical Regulations skeleton. Each parameter is cross-referenced
to an entry in `vehicle_parameters.md` where the literature-sourced
confirmed value should be recorded as Phase 2 progresses.

Confirmed values should be copied directly into the defaults of this
dataclass once recorded in the worksheet. The placeholder values are
chosen to produce OCP solutions of plausible magnitude so that the
end-to-end pipeline can be tested before all parameters are confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, Any


# Worksheet IDs reference rows in vehicle_parameters.md
# Format: VP-NN where NN is a stable numeric ID.


@dataclass(frozen=True)
class VehicleParams:
    """
    Longitudinal point-mass F1 2026 vehicle parameter set.

    Units are SI throughout: kg, m, m^2, kg/m^3, N, W, J, dimensionless.
    Sign convention: positive longitudinal force accelerates the car;
    negative force decelerates (regenerative or friction braking).

    Confidence tiers (see vehicle_parameters.md):
        Tier 1 — FIA-regulated, confirmed (2026 regs through May 2026)
        Tier 2 — standard physics / LTS literature, defensible
        Tier 3 — aerodynamics, LOCKED central values (Rev 2, 2026-06-10);
                 derived not measured — designated sensitivity-sweep set
    """

    # ------------------------------------------------------------------
    # Mass & geometry
    # ------------------------------------------------------------------
    mass_total: float = 768.0          # VP-01  FIA 2026 min mass + driver (no fuel) — CONFIRMED (Tier 1)
    frontal_area: float = 1.0          # VP-02  Unit reference area (Option A normalisation) — LOCKED (Tier 3)
    # NOT a physical area estimate. With A = 1.0 m², cd/cl below are
    # numerically equal to the area-integrated CdA/ClA in m², matching the
    # convention of the public LTS estimates they derive from.
    wheelbase: float = 3.4             # VP-03  FIA 2026 max wheelbase — CONFIRMED (Tier 1)
    # Wheelbase is not used in the pure longitudinal model but is reserved
    # for future extension to a load-transfer-aware bicycle model.

    # ------------------------------------------------------------------
    # Aerodynamics — TIER 3 LOCKED (Rev 2, 2026-06-10)
    # Convention (Option A): with frontal_area = 1.0 m², cd/cl are
    # numerically the area-integrated CdA/ClA values (m²). Cl is signed
    # NEGATIVE for downforce: friction-circle normal load N = m·g − F_lift.
    # Derived (not measured): ground-effect-era LTS baselines with the
    # regulated 2026 deltas applied (downforce −15…−30%, drag −40…−55%);
    # X-mode flattens wing load while underfloor load persists.
    # Designated sensitivity-sweep set — ranges in vehicle_parameters.md.
    # ------------------------------------------------------------------
    cd_z: float = 1.00                 # VP-04  CdA Z-mode — LOCKED (sweep 0.90–1.10)
    cd_x: float = 0.65                 # VP-05  CdA X-mode — LOCKED (sweep 0.55–0.70)
    cl_z: float = -4.00                # VP-06  ClA Z-mode — LOCKED (sweep −3.50…−4.50)
    cl_x: float = -2.00                # VP-07  ClA X-mode — LOCKED (sweep −1.50…−2.50)
    air_density: float = 1.225         # VP-08  ISA sea-level, 15°C — CONFIRMED (Tier 2)

    # ------------------------------------------------------------------
    # Tyre / friction (longitudinal-only — friction circle approximation)
    # ------------------------------------------------------------------
    mu_long: float = 1.50              # VP-09  Standard LTS value for F1 slick — CONFIRMED (Tier 2)
    c_rolling: float = 0.012           # VP-10  Standard LTS value — CONFIRMED (Tier 2)

    # ------------------------------------------------------------------
    # Powertrain — 2026 hybrid (~50/50 split)
    # ------------------------------------------------------------------
    p_ice_max: float = 400.0e3         # VP-11  FIA 2026 (fuel-energy-flow capped) — CONFIRMED (Tier 1)
    p_mguk_max: float = 350.0e3        # VP-12  FIA 2026 deployment peak — CONFIRMED (Tier 1)
    # NB: a 250 kW figure also appears in the regulations (C5.2.8(iii)), but
    # that clause applies only in Race or Sprint, on specified sectors,
    # during a power-limited period — it is not applicable to qualifying,
    # which is the scope of this model. 350 kW (C5.2.7) is correct here.

    p_regen_max: float = 350.0e3       # VP-20  FIA 2026 regen (harvest-rate) peak — CONFIRMED (Tier 1)
    # Regen cap applies at ALL speeds; the deployment-speed envelope below
    # constrains the deployment side only.

    e_lap_harvest_max: float = 8.5e6   # VP-13  FIA 2026 per-lap HARVEST budget — CONFIRMED (Tier 1)
    # C5.2.10 caps cumulative Recharge at the CU-K HV DC bus at 8.5 MJ per
    # lap, reducible to 7.0 MJ under C5.2.10(i) where the FIA determines
    # braking + partial-load harvest cannot exceed that figure, and to no
    # less than 5.0 MJ for Sprint Qualifying/Qualifying under C5.2.10(ii).
    # The "9 MJ Monaco/Hungary" figure previously here has no basis in the
    # regulations and has been withdrawn. Enforced at the Phase 4 outer
    # loop as the E_har[N] state produced by the v3 OCP (regs_2026.py,
    # dynamics.py); not enforced per-micro-sector.

    e_batt_capacity: float = 4.0e6     # VP-14  FIA 2026 usable storage — CONFIRMED (Tier 1)
    # NB: the regulatory figure this value is drawn from (C5.2.9) is a
    # max-minus-min EXCURSION limit on the state of charge whilst the car
    # is on track, not a storage capacity. It is used here as a defensible
    # proxy for capacity within a single micro-sector — see problem.py.
    eta_motor: float = 0.95            # VP-15  Standard LTS η_k — CONFIRMED (Tier 2)
    eta_regen: float = 0.95            # VP-16  Standard LTS η_k (per-direction) — CONFIRMED (Tier 2)
    # Efficiencies are documented but NOT currently applied in dynamics.dE_ds
    # which uses dE/ds = -F_mguk (unity efficiency). Applying η piecewise
    # requires a smooth sign-dependent formulation; flagged as future work.

    eta_driveline: float = 0.95        # VP-17  Standard LTS η_dt — CONFIRMED (Tier 2)
    # Driveline efficiency between engine output and wheels. Not applied
    # in the current power-based formulation (p_ice_max / p_mguk_max are
    # treated as wheel-equivalent powers); stored for documentation.

    wheel_radius: float = 0.36         # VP-18  18" rim + tyre — CONFIRMED (Tier 2)
    # Not needed in the power-based formulation; required only if the
    # model is ever rewritten as torque-based.

    fuel_energy_flow_max: float = 833.3e3  # VP-19  FIA 2026: 3000 MJ/h = 833 kW peak fuel energy flow
    # Reduced from mass-flow (~100 kg/h) to energy-flow (~3000 MJ/h or
    # ~70 kg/h equivalent). This is what caps p_ice_max at ~400 kW after
    # accounting for ICE thermal efficiency (~48%). Stored as documentation.

    # ------------------------------------------------------------------
    # Environmental
    # ------------------------------------------------------------------
    g: float = 9.81                    # gravitational acceleration (m/s^2)

    # ------------------------------------------------------------------
    # Numerical / OCP solver settings (not vehicle physics but convenient here)
    # ------------------------------------------------------------------
    aero_switch_steepness: float = 0.05  # sigmoid scaling factor for X/Z transition
                                         # (per proposal TR-1 mitigation strategy)
    # Larger value -> sharper switch; too sharp causes IPOPT non-convergence.

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_params() -> VehicleParams:
    """Convenience constructor returning the default parameter set."""
    return VehicleParams()
