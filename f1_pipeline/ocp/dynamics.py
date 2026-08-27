"""
Longitudinal point-mass dynamics in the spatial domain — v3.

The state of the OCP is parameterised by distance s along the micro-sector
rather than by time, following the standard MLTP transcription in Kelly
(2017) and the project proposal Eq. 1. This makes the boundary conditions
geometric (sector length L_straight is known a priori) rather than free,
which is essential for direct collocation.

v3 CHANGES (supersede v2)
=========================

1. MGU-K CONTROL SPLIT.  The single signed control F_mguk is replaced by
   two non-negative controls F_dep (deployment) and F_reg (regeneration),
   with F_mguk = F_dep - F_reg recovered for the velocity equation.

   Motivation: FIA 2026 Article C5.2.10 caps *Recharge* — the harvest side
   alone, measured at the CU-K HV DC bus — at 8.5 MJ per lap. A net-energy
   state cannot express that constraint, because net energy conflates
   harvest with deployment. Phase 4 lap assembly requires the harvest
   integral in its own right, so it becomes a state.

2. THIRD STATE E_har.  Cumulative Recharge measured at the CU-K HV DC bus,
   J, monotone non-decreasing by construction (F_reg >= 0). This is the
   quantity that C5.2.10 limits. It is unconstrained at micro-sector level
   — the cap is a lap-level quantity — but must be carried through to the
   Phase 4 outer loop.

3. EFFICIENCIES APPLIED.  v2 used dE/ds = -F_mguk, i.e. unity efficiency
   in both directions, with eta_motor and eta_regen documented but unused.
   v3 applies them. This is not cosmetic: with the split above, applying
   the efficiencies is what makes the formulation well-posed.

   With unity efficiency, simultaneous F_dep > 0 and F_reg > 0 would be a
   free degeneracy — the solver could add matched deployment and regen
   without changing dynamics or energy. With eta_motor * eta_regen < 1 it
   is strictly wasteful. Substituting (F_dep, F_reg) for the equivalent
   (F_dep - F_reg, 0) at identical net wheel force changes the store drain
   per metre by

       F_reg * (1/eta_motor - eta_regen)  =  0.103 * F_reg  > 0

   so any objective placing positive value on stored energy strictly
   prefers the single-sided control. See problem.py on why the energy
   price lambda must therefore be strictly positive.

STATE / CONTROL VECTORS
=======================

State  x(s) = [v(s), E(s), E_har(s)]
    v      — longitudinal velocity (m/s)
    E      — energy in the Energy Store (J)
    E_har  — cumulative Recharge at the CU-K HV DC bus (J), C5.2.10

Control u(s) = [F_ice(s), F_dep(s), F_reg(s), F_brake(s), a(s)]
    F_ice   — ICE driving force at the wheels (N), >= 0
    F_dep   — MGU-K deployment force at the wheels (N), >= 0
    F_reg   — MGU-K regenerative force at the wheels (N), >= 0
    F_brake — friction-brake force (N), >= 0, dissipative
    a       — aero mode continuous variable in [0, 1]: 0 = full Z-mode
              (high downforce), 1 = full X-mode (low drag). The discrete
              driver-controlled switch is relaxed to a continuous variable
              per the proposal TR-1 mitigation; the post-processed switch
              distance d_X is recovered as the s where a(s) first crosses 0.5.

EFFICIENCY CONVENTION
=====================

eta_motor is the DC-bus-to-wheel efficiency on deployment; eta_regen is
the wheel-to-DC-bus efficiency on harvest. Both are lumped: they absorb
the MGU-K electromechanical loss, the inverter loss and (nominally) the
driveline. eta_driveline is therefore still NOT applied separately —
applying it as well would double-count. This preserves the v2 convention
that p_ice_max and the force variables are wheel-equivalent quantities,
whilst making the electrical-side bookkeeping explicit where the
regulations require it.

The Energy Store round-trip loss is not separately modelled: DC-bus energy
in equals store energy gained. Document this as a limitation.

All functions accept either NumPy floats (for synthetic testing) or CasADi
symbolic types (for the actual NLP).
"""

from __future__ import annotations

from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from f1_pipeline.ocp.vehicle import VehicleParams


# ----------------------------------------------------------------------
# Force terms
# ----------------------------------------------------------------------
def drag_force(v, a, p: "VehicleParams"):
    """
    Aerodynamic drag force (N). Positive value opposes motion.

    Drag coefficient linearly interpolates between Z and X modes according
    to the relaxed aero variable a in [0, 1]. The interpolation is linear
    in Cd; regularisation of a(s) to encourage one clean switch is handled
    in problem.py.
    """
    cd = p.cd_z + a * (p.cd_x - p.cd_z)
    return 0.5 * p.air_density * cd * p.frontal_area * v * v


def lift_force(v, a, p: "VehicleParams"):
    """
    Aerodynamic lift force (N). Negative value = downforce (presses car down).

    Used in the longitudinal friction-circle limit via the tyre normal
    load N = m*g - F_lift.
    """
    cl = p.cl_z + a * (p.cl_x - p.cl_z)
    return 0.5 * p.air_density * cl * p.frontal_area * v * v


def rolling_resistance(p: "VehicleParams"):
    """Rolling resistance force (N), constant in this simplified model."""
    return p.c_rolling * p.mass_total * p.g


# ----------------------------------------------------------------------
# Electrical power (DC bus) — the quantity the regulations constrain
# ----------------------------------------------------------------------
def p_deploy_dc(F_dep, v, p: "VehicleParams"):
    """
    Deployment power measured at the CU-K HV DC bus (W).

    Articles C5.2.7 and C5.2.8 both constrain "electrical DC power", not
    wheel power. Mechanical power at the wheels is F_dep * v; the DC bus
    must supply that divided by the deployment efficiency.

    NOTE the change from v2, which compared wheel power F_mguk * v
    directly against the 350 kW cap. Wheel power understates DC power by
    a factor 1/eta_motor, so the v2 constraint was roughly 5% permissive.
    """
    return F_dep * v / p.eta_motor


def p_regen_dc(F_reg, v, p: "VehicleParams"):
    """
    Recharge power measured at the CU-K HV DC bus (W), non-negative.

    Mechanical power absorbed at the wheels is F_reg * v; the DC bus
    receives that multiplied by the harvest efficiency. This is the
    quantity Article C5.2.10 integrates and caps per lap, and the quantity
    the absolute limit of C5.2.7 bounds on the harvest side.
    """
    return F_reg * v * p.eta_regen


# ----------------------------------------------------------------------
# State derivatives in spatial domain
# ----------------------------------------------------------------------
def dv_ds(v, F_ice, F_dep, F_reg, F_brake, a, p: "VehicleParams"):
    """
    Spatial-domain velocity derivative.

    Derivation: time-domain Newton's 2nd law m*dv/dt = F_net.
    With dv/dt = v*dv/ds (chain rule, s = integral of v dt):

        dv/ds = F_net / (m * v)

    F_net = F_ice + F_dep - F_reg - F_brake - F_drag - F_roll

    All five actuator terms are wheel forces. The grade term m*g*sin(theta)
    is omitted — straight micro-sectors are assumed flat, and the broadcast
    Z (elevation) channel was found unreliable across all circuits and
    dropped from the feature matrix.

    F_brake is the friction-brake force (>= 0), dissipative. It appears in
    the velocity equation but in neither energy equation: friction braking
    converts kinetic energy to heat rather than recovering it. Recovery is
    F_reg.
    """
    F_net = (
        F_ice + F_dep - F_reg - F_brake
        - drag_force(v, a, p) - rolling_resistance(p)
    )
    return F_net / (p.mass_total * v)


def dE_ds(F_dep, F_reg, p: "VehicleParams"):
    """
    Spatial-domain Energy Store derivative (J per m).

    Time domain:  dE/dt = -P_deploy_dc + P_regen_dc
                        = -F_dep*v/eta_motor + F_reg*v*eta_regen

    Converting via dE/ds = (dE/dt) / (ds/dt) = (dE/dt) / v, the velocity
    cancels exactly:

        dE/ds = -F_dep/eta_motor + F_reg*eta_regen

    The cancellation is the reason the spatial formulation is convenient
    here: the energy dynamics are velocity-free and linear in the controls.
    """
    return -F_dep / p.eta_motor + F_reg * p.eta_regen


def dE_har_ds(F_reg, p: "VehicleParams"):
    """
    Spatial-domain cumulative-Recharge derivative (J per m).

    Time domain:  dE_har/dt = P_regen_dc = F_reg * v * eta_regen
    Spatial:      dE_har/ds = F_reg * eta_regen

    Monotone non-decreasing since F_reg >= 0. This integral is what
    Article C5.2.10 caps at 8.5 MJ per lap (reducible to 7 MJ under
    C5.2.10(i), and to no less than 5 MJ for Qualifying under C5.2.10(ii)).
    The cap is NOT applied at micro-sector level — it is a lap-level
    quantity, enforced in the Phase 4 outer loop.
    """
    return F_reg * p.eta_regen


def state_derivatives(
    v, F_ice, F_dep, F_reg, F_brake, a, p: "VehicleParams"
) -> Tuple:
    """
    Combined state derivative tuple (dv/ds, dE/ds, dE_har/ds).

    Pure function, no side effects. Accepts CasADi symbolics or floats
    interchangeably.

    SIGNATURE CHANGE from v2: the state arguments E and the signed control
    F_mguk are gone. E never entered any derivative (the dynamics are
    energy-state-independent), and F_mguk is replaced by the non-negative
    pair (F_dep, F_reg). Call sites must be updated; there is no shim.
    """
    return (
        dv_ds(v, F_ice, F_dep, F_reg, F_brake, a, p),
        dE_ds(F_dep, F_reg, p),
        dE_har_ds(F_reg, p),
    )


# ----------------------------------------------------------------------
# Self-check — run `python dynamics.py`
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    try:
        from f1_pipeline.ocp.vehicle import default_params
    except ImportError:
        print("Run from the package root so f1_pipeline is importable.")
        sys.exit(1)

    p = default_params()
    v = 70.0

    # Deployment drains the store; harvest does not accumulate.
    dE = dE_ds(2000.0, 0.0, p)
    dH = dE_har_ds(0.0, p)
    assert dE < 0.0, dE
    assert dH == 0.0, dH

    # Harvest fills the store and accumulates Recharge at the same rate.
    dE = dE_ds(0.0, 2000.0, p)
    dH = dE_har_ds(2000.0, p)
    assert dE > 0.0, dE
    assert abs(dE - dH) < 1e-9, (dE, dH)

    # Simultaneous deploy+regen is strictly wasteful relative to the
    # equivalent single-sided control at identical net wheel force.
    both = dE_ds(3000.0, 1000.0, p)
    single = dE_ds(2000.0, 0.0, p)
    penalty = single - both          # J/m of store lost by doubling up
    per_newton = 1.0 / p.eta_motor - p.eta_regen   # J/m per N of F_reg
    expected = 1000.0 * per_newton                 # the test uses F_reg = 1 kN
    assert penalty > 0.0, penalty
    assert abs(penalty - expected) < 1e-9, (penalty, expected)

    # DC power exceeds wheel power on deployment, falls short on harvest.
    assert p_deploy_dc(2000.0, v, p) > 2000.0 * v
    assert p_regen_dc(2000.0, v, p) < 2000.0 * v

    print("dynamics.py v3 self-check passed")
    print(f"  eta_motor={p.eta_motor}  eta_regen={p.eta_regen}")
    print(f"  simultaneity penalty = {per_newton:.4f} J/m per N of F_reg"
          f"  ({expected:.1f} J/m per kN)")
    print(f"  round-trip efficiency = {p.eta_motor * p.eta_regen:.4f}")
