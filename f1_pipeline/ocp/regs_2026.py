"""
Regulatory constants and power envelopes — FIA 2026 Formula 1 Regulations,
Section C [Technical], Issue 20, published 05 August 2026.

Every constant carries its governing article. Do not edit values without
updating the article reference and re-checking against the source PDF.

Scope note: this project models a QUALIFYING lap. Qualifying is a Lap Time
Classified Session (Section B, Appendix B1). Under B7.2.2a Overtake is enabled
prior to any LTCS, and under B7.2.3b.i it is activated at all times whilst
enabled. The binding deployment envelope for qualifying is therefore
C5.2.8(ii), NOT the base curve C5.2.8(i). Curve (i) is retained here for
race-context work only.

Units are SI throughout (W, J, m/s, Nm). The regulations state kW and kph;
conversions are applied once, here, and nowhere else.
"""

from __future__ import annotations

# ----------------------------------------------------------------------------
# Scalar limits
# ----------------------------------------------------------------------------

P_ERS_ABS_MAX = 350_000.0
"""C5.2.7 — absolute electrical DC power of the ERS-K, W.

Stated as an absolute limit, so it bounds BOTH deployment and Recharge.
The speed-dependent taper of C5.2.8 applies only to power 'used to propel
the car'; harvest is therefore capped flat at this value with no taper.
"""

E_ES_WINDOW_MAX = 4.0e6
"""C5.2.9 — max minus min ES state of charge may not exceed 4 MJ on track, J.

This bounds the SoC EXCURSION over the lap, not the store's capacity. It is
also the regulatory ceiling on net depletion across a single lap.
"""

E_RECHARGE_LAP_MAX = 8.5e6
"""C5.2.10 — Recharge per lap at the CU-K HV DC bus, J.

Circuit-specific reductions exist and are NOT published in the regulations:
  C5.2.10(i)  -> 7.0 MJ where the FIA determines braking + partial-load
                 harvest cannot exceed that figure.
  C5.2.10(ii) -> no less than 5.0 MJ for Sprint Qualifying and Qualifying.
Per-competition values are issued under B7.2.1d. Model at 8.5 MJ and document
the reduction clauses; 5.0 MJ is the regulatory floor for a Q session and is
the natural sensitivity point.
"""

E_RECHARGE_LAP_REDUCED = 7.0e6   # C5.2.10(i)
E_RECHARGE_LAP_FLOOR_Q = 5.0e6   # C5.2.10(ii), Sprint Qualifying / Qualifying

TAU_MGUK_MAX = 500.0
"""C5.2.11 — MGU-K mechanical torque magnitude, Nm, referenced to crankshaft
speed.

Applying this requires a crankshaft-speed model (gear ratios + final drive).
If the vehicle model has no gearbox, this constraint CANNOT be enforced
directly and must be documented as not enforced, with P_ERS_ABS_MAX standing
as the binding powertrain limit. Do not silently omit it.
"""

V_MGUK_MIN_STANDING_START = 50.0 / 3.6
"""C5.2.12 — MGU-K may only be used above 50 kph from a standing start, m/s.

Not binding on a flying qualifying lap; included for completeness.
"""

# ----------------------------------------------------------------------------
# Deployment envelope breakpoints, C5.2.8
# ----------------------------------------------------------------------------
# Regulation form, v in kph, P in kW:
#   (i)  Overtake NOT active:  P = 1800 - 5*v      for v < 340
#                              P = 6900 - 20*v     for 340 <= v < 345
#                              P = 0               for v >= 345
#   (ii) Overtake active:      P = 7100 - 20*v     for v < 355
#                              P = 0               for v >= 355
#
# Converted to v in m/s, P in W (v_kph = 3.6 * v_ms):
#   (i)   P = 1.80e6 - 1.80e4 * v   |  P = 6.90e6 - 7.20e4 * v
#   (ii)  P = 7.10e6 - 7.20e4 * v

_OT_INTERCEPT, _OT_SLOPE = 7.10e6, 7.20e4          # C5.2.8(ii)
_BASE_A_INTERCEPT, _BASE_A_SLOPE = 1.80e6, 1.80e4  # C5.2.8(i), v < 340 kph
_BASE_B_INTERCEPT, _BASE_B_SLOPE = 6.90e6, 7.20e4  # C5.2.8(i), 340-345 kph

V_OT_CAP_KNEE = (_OT_INTERCEPT - P_ERS_ABS_MAX) / _OT_SLOPE   # 93.750 m/s
V_OT_ZERO = _OT_INTERCEPT / _OT_SLOPE                          # 98.611 m/s
V_BASE_CAP_KNEE = (_BASE_A_INTERCEPT - P_ERS_ABS_MAX) / _BASE_A_SLOPE  # 80.556
V_BASE_BREAK = 340.0 / 3.6                                     # 94.444 m/s
V_BASE_ZERO = _BASE_B_INTERCEPT / _BASE_B_SLOPE                # 95.833 m/s


def p_deploy_max(v, overtake: bool = True):
    """Maximum ERS-K deployment power [W] at longitudinal speed v [m/s].

    C5.2.7 combined with C5.2.8. Pure Python/NumPy — for post-processing,
    the projection layer and the forward simulator. Do NOT embed this in the
    OCP: the min/max operators are non-differentiable and will wreck IPOPT.
    Use `deployment_constraints` instead.

    Parameters
    ----------
    v : float or ndarray
        Longitudinal speed, m/s.
    overtake : bool
        True for the qualifying envelope C5.2.8(ii). False for the base
        envelope C5.2.8(i).
    """
    if overtake:
        taper = _OT_INTERCEPT - _OT_SLOPE * v
    else:
        # Two-segment base curve; the segments are continuous at 340 kph
        # (both give 100 kW), so an elementwise minimum reproduces it exactly
        # below 345 kph.
        try:
            import numpy as _np
            taper = _np.minimum(
                _BASE_A_INTERCEPT - _BASE_A_SLOPE * v,
                _BASE_B_INTERCEPT - _BASE_B_SLOPE * v,
            )
        except ImportError:
            taper = min(
                _BASE_A_INTERCEPT - _BASE_A_SLOPE * v,
                _BASE_B_INTERCEPT - _BASE_B_SLOPE * v,
            )

    try:
        import numpy as _np
        return _np.clip(_np.minimum(P_ERS_ABS_MAX, taper), 0.0, None)
    except ImportError:
        return max(0.0, min(P_ERS_ABS_MAX, taper))


def deployment_constraints(p_sym, v_sym, overtake: bool = True):
    """Deployment envelope as a list of smooth inequality expressions g <= 0.

    The envelope is a lower hull of straight lines, so it decomposes exactly
    into linear inequalities. This is preferable to any smoothed min(): it is
    exact, everywhere differentiable, and adds no tuning parameter.

    Returns expressions in whatever symbolic type `p_sym` and `v_sym` are —
    CasADi MX/SX, or floats for testing. Feed each to the NLP as g <= 0.

        for g in deployment_constraints(P_k, v_k):
            opti.subject_to(g <= 0)

    Non-negativity (P >= 0) is a separate variable bound, not included here.
    """
    cons = [p_sym - P_ERS_ABS_MAX]                       # C5.2.7
    if overtake:
        cons.append(p_sym - (_OT_INTERCEPT - _OT_SLOPE * v_sym))
    else:
        cons.append(p_sym - (_BASE_A_INTERCEPT - _BASE_A_SLOPE * v_sym))
        cons.append(p_sym - (_BASE_B_INTERCEPT - _BASE_B_SLOPE * v_sym))
    return cons


def p_recharge_max(v=None):
    """Maximum Recharge power [W]. Flat at 350 kW — C5.2.7.

    Takes `v` only so callers can be written symmetrically with
    p_deploy_max. The C5.2.8 taper does not apply to harvest: that article
    governs power 'used to propel the car'. This asymmetry is deliberate and
    should be stated explicitly in the methods chapter.
    """
    return P_ERS_ABS_MAX


# ----------------------------------------------------------------------------
# Self-check — run `python regs_2026.py`
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    def close(a, b, tol=1e-6):
        assert abs(a - b) < tol, f"{a} != {b}"

    # C5.2.8(ii): 350 kW held to 337.5 kph, zero at 355 kph.
    close(V_OT_CAP_KNEE * 3.6, 337.5)
    close(V_OT_ZERO * 3.6, 355.0)
    close(p_deploy_max(V_OT_CAP_KNEE), P_ERS_ABS_MAX)
    close(p_deploy_max(V_OT_ZERO), 0.0)
    close(p_deploy_max(50.0), P_ERS_ABS_MAX)
    close(p_deploy_max(120.0), 0.0)

    # C5.2.8(i): 350 kW to 290 kph, 100 kW at 340 kph, zero at 345 kph.
    close(V_BASE_CAP_KNEE * 3.6, 290.0)
    close(p_deploy_max(V_BASE_CAP_KNEE, overtake=False), P_ERS_ABS_MAX)
    close(p_deploy_max(V_BASE_BREAK, overtake=False), 100_000.0)
    close(p_deploy_max(V_BASE_ZERO, overtake=False), 0.0)

    # Constraint form must agree with the evaluated form at the knee.
    g = deployment_constraints(P_ERS_ABS_MAX, V_OT_CAP_KNEE)
    assert all(abs(x) < 1e-6 for x in g), g

    print("regs_2026.py self-check passed")
    print(f"  Qualifying envelope (C5.2.8ii): "
          f"350 kW to {V_OT_CAP_KNEE * 3.6:.1f} kph, "
          f"zero at {V_OT_ZERO * 3.6:.1f} kph")
    print(f"  Base envelope (C5.2.8i):        "
          f"350 kW to {V_BASE_CAP_KNEE * 3.6:.1f} kph, "
          f"zero at {V_BASE_ZERO * 3.6:.1f} kph")
    print(f"  SoC window (C5.2.9):            "
          f"{E_ES_WINDOW_MAX / 1e6:.1f} MJ")
    print(f"  Recharge cap (C5.2.10):         "
          f"{E_RECHARGE_LAP_MAX / 1e6:.1f} MJ/lap")
