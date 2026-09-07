"""
Slinky — real-time setup inference for 2026 F1 regulations.

Front end for the MSc dissertation surrogate framework. Select a circuit, run the
trained MLP over its micro-sectors, and compare the prediction against the stored
CasADi/IPOPT ground truth.

Design intent: this reads as a pit-wall timing screen, not a dashboard template.
Aero mode is encoded in colour throughout (Z-Mode cool, X-Mode amber) so the same
two colours mean the same two things on the map, the traces and the table.

--------------------------------------------------------------------------------
WIRING: everything you need to change lives in the CONFIG block below. Until the
paths resolve, the app runs on a synthetic circuit so you can see the layout.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =============================================================================
# CONFIG — edit to match your repo
# =============================================================================

ROOT = Path(__file__).parent


@dataclass
class Config:
    # --- Data -----------------------------------------------------------
    # One small parquet per circuit, pre-sliced from the full label set.
    # Do NOT ship microsectors_combined_Q_labels_v4.parquet whole; 800k rows
    # will not survive a 2.7 GB container alongside 24 models.
    circuit_dir: Path = ROOT / "data" / "circuits"

    # One model per LOCO fold, named for the circuit it was held out of.
    # This is what makes every prediction on screen genuinely out-of-sample.
    model_dir: Path = ROOT / "data" / "models"
    model_pattern: str = "mlp_loco_{circuit}.joblib"

    # --- Feature contract -------------------------------------------------
    # The 6-feature geometry-only contract used for P_deploy and d_X.
    geometry_features: list[str] = field(
        default_factory=lambda: [
            "sector_length",
            "curvature_entry",
            "curvature_exit",
            "v_entry",
            "v_exit_target",
            "elevation_delta",
        ]
    )
    # State features appended at inference time from the sidebar controls.
    state_features: list[str] = field(
        default_factory=lambda: ["soc_start", "energy_budget"]
    )

    # --- Prediction heads -------------------------------------------------
    # label -> (predicted column, ground-truth column, unit, decimals)
    heads: dict = field(
        default_factory=lambda: {
            "Aero switch point": ("d_X", "d_X_ocp", "m", 1),
            "Coast distance": ("d_coast", "d_coast_ocp", "m", 1),
            "Deployment power": ("P_deploy", "P_deploy_ocp", "kW", 1),
        }
    )

    # --- Geometry columns for the map -------------------------------------
    x_col: str = "x"
    y_col: str = "y"
    sector_col: str = "sector_id"

    # --- Live solve -------------------------------------------------------
    # Off by default. IPOPT on a shared free-tier container is a bad idea and
    # it undercuts the point the app exists to make.
    enable_live_solve: bool = False


CFG = Config()

# Aero mode colours. These carry information, so they are used consistently
# everywhere a mode is shown and nowhere it is not.
Z_MODE = "#4CA6E8"   # high downforce
X_MODE = "#F5A524"   # low drag
TRUTH = "#8C99AB"    # CasADi ground truth, deliberately quiet
GRID = "#22303F"
INK = "#E3E8EF"

st.set_page_config(
    page_title="Slinky — 2026 setup inference",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      /* Tabular figures for anything that behaves like a timing readout. */
      [data-testid="stMetricValue"] {
          font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
          font-variant-numeric: tabular-nums;
          letter-spacing: -0.01em;
      }
      [data-testid="stMetricLabel"] { color: #8C99AB; }
      .stDataFrame { font-variant-numeric: tabular-nums; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Data layer
# =============================================================================


@st.cache_data(show_spinner=False)
def list_circuits() -> tuple[list[str], bool]:
    """Return available circuits and whether they came from real data."""
    if CFG.circuit_dir.exists():
        found = sorted(p.stem for p in CFG.circuit_dir.glob("*.parquet"))
        if found:
            return found, True
    return ["Demo Circuit"], False


@st.cache_data(show_spinner=False)
def load_circuit(name: str, is_real: bool) -> pd.DataFrame:
    if is_real:
        return pd.read_parquet(CFG.circuit_dir / f"{name}.parquet")
    return synthesise_circuit()


def synthesise_circuit(n: int = 220, seed: int = 7) -> pd.DataFrame:
    """A closed loop with plausible curvature, so the layout can be judged
    before the real pipeline is wired in. Not physics."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 1000 + 250 * np.sin(3 * t) + 210 * np.cos(7 * t) + 95 * np.sin(11 * t)
    x, y = r * np.cos(t), r * np.sin(t)

    dx, dy = np.gradient(x), np.gradient(y)
    ddx, ddy = np.gradient(dx), np.gradient(dy)
    kappa = np.abs(dx * ddy - dy * ddx) / np.power(dx**2 + dy**2, 1.5)
    kappa = np.clip(kappa, 0, 0.5)  # the ALB British GP spike guard

    seg = np.hypot(np.diff(x, append=x[0]), np.diff(y, append=y[0]))
    v = 85 + 200 * np.exp(-kappa / 0.006)

    df = pd.DataFrame(
        {
            CFG.sector_col: np.arange(n),
            CFG.x_col: x,
            CFG.y_col: y,
            "sector_length": seg,
            "curvature_entry": kappa,
            "curvature_exit": np.roll(kappa, -1),
            "v_entry": v,
            "v_exit_target": np.roll(v, -1),
            "elevation_delta": rng.normal(0, 1.4, n),
        }
    )

    straightness = np.exp(-kappa / 0.0012)
    df["d_X_ocp"] = np.clip(df.sector_length * straightness * 0.62, 0, None)
    df["d_coast_ocp"] = np.clip(df.sector_length * (1 - straightness) * 0.28, 0, None)
    df["P_deploy_ocp"] = np.clip(350 * straightness - 18 * rng.random(n), 0, 350)
    return df


@st.cache_resource(show_spinner=False)
def load_model(circuit: str):
    """Load the LOCO fold in which this circuit was held out."""
    path = CFG.model_dir / CFG.model_pattern.format(circuit=circuit)
    if not path.exists():
        return None
    import joblib

    return joblib.load(path)


def predict(model, X: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Run inference and return the wall time. The timing is the point, so it
    brackets only the forward pass — no I/O, no dataframe construction."""
    if model is None:
        # Stand-in so the layout is judgeable. Replace by shipping the folds.
        straightness = np.exp(-X["curvature_entry"].to_numpy() / 0.0012)
        soc = X["soc_start"].to_numpy() if "soc_start" in X else np.ones(len(X))
        t0 = time.perf_counter()
        out = np.column_stack(
            [
                X["sector_length"].to_numpy() * straightness * 0.60 * soc,
                X["sector_length"].to_numpy() * (1 - straightness) * 0.30,
                np.clip(350 * straightness * soc, 0, 350),
            ]
        )
        return out, (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    out = model.predict(X.to_numpy())
    return np.asarray(out), (time.perf_counter() - t0) * 1000


# =============================================================================
# Sidebar
# =============================================================================

circuits, real_data = list_circuits()

with st.sidebar:
    st.markdown("### Circuit")
    circuit = st.selectbox("Select a circuit", circuits, label_visibility="collapsed")

    st.markdown("### Initial state")
    soc_start = st.slider("State of charge at sector 1", 0.0, 1.0, 0.72, 0.01)
    energy_budget = st.slider("Harvest budget (MJ)", 0.0, 8.5, 8.5, 0.1)
    st.caption(
        "Recharge is capped at 8.5 MJ per lap under C5.2.10. The 4 MJ excursion "
        "limit in C5.2.9 constrains the usable window, not this budget."
    )

    run = st.button("Run inference", type="primary", width="stretch")

    st.divider()
    model_obj = load_model(circuit)
    if model_obj is None:
        st.warning(
            f"No held-out fold found for **{circuit}**. Running on a placeholder "
            "so the layout is visible. Predictions are not from your model."
        )
    else:
        st.success(f"Loaded the fold with **{circuit}** held out.")

if not real_data:
    st.info(
        "Running on a synthetic circuit. Drop per-circuit parquet files into "
        f"`{CFG.circuit_dir.relative_to(ROOT)}` to switch to your own data.",
        icon=":material/database:",
    )


# =============================================================================
# Run
# =============================================================================

if run or "result" not in st.session_state:
    df = load_circuit(circuit, real_data).copy()

    missing = [c for c in CFG.geometry_features if c not in df.columns]
    if missing:
        st.error(
            "Circuit file is missing feature columns: "
            + ", ".join(f"`{c}`" for c in missing)
            + ". Update `Config.geometry_features` to match your schema."
        )
        st.stop()

    X = df[CFG.geometry_features].copy()
    X["soc_start"] = soc_start
    X["energy_budget"] = energy_budget

    y_pred, elapsed_ms = predict(model_obj, X)

    for i, (_, (pred_col, _, _, _)) in enumerate(CFG.heads.items()):
        if i < y_pred.shape[1]:
            df[pred_col] = y_pred[:, i]

    st.session_state.result = dict(
        df=df, elapsed_ms=elapsed_ms, circuit=circuit, model=model_obj is not None
    )

res = st.session_state.result
df, elapsed_ms = res["df"], res["elapsed_ms"]

# Predicted aero mode: X-Mode wherever the model asks for a switch inside the sector.
d_x_col = CFG.heads["Aero switch point"][0]
df["mode"] = np.where(df.get(d_x_col, pd.Series(0, index=df.index)) > 1.0, "X", "Z")


# =============================================================================
# Header — the claim, stated in numbers
# =============================================================================

st.markdown(f"## {res['circuit']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Inference", f"{elapsed_ms:.1f} ms", help="Forward pass over the full lap.")
c2.metric("Micro-sectors", f"{len(df):,}")
c3.metric("Per sector", f"{elapsed_ms / max(len(df), 1) * 1000:.0f} µs")
c4.metric(
    "X-Mode sectors",
    f"{(df['mode'] == 'X').mean() * 100:.0f}%",
    help="Bang-bang OCP structure engages straightline mode at every "
    "power-limited opportunity, not only on FIA-designated straights.",
)


# =============================================================================
# Track map — the hero
# =============================================================================

st.markdown("#### Predicted aero mode around the lap")

fig = go.Figure()
for mode, colour, label in (("Z", Z_MODE, "Z-Mode"), ("X", X_MODE, "X-Mode")):
    sub = df[df["mode"] == mode]
    fig.add_trace(
        go.Scattergl(
            x=sub[CFG.x_col],
            y=sub[CFG.y_col],
            mode="markers",
            marker=dict(size=7, color=colour),
            name=label,
            hovertemplate=(
                "Sector %{customdata[0]}<br>"
                "Switch at %{customdata[1]:.0f} m<br>"
                "Deploy %{customdata[2]:.0f} kW<extra></extra>"
            ),
            customdata=np.column_stack(
                [
                    sub[CFG.sector_col],
                    sub.get(d_x_col, pd.Series(0, index=sub.index)),
                    sub.get("P_deploy", pd.Series(0, index=sub.index)),
                ]
            ),
        )
    )

fig.update_layout(
    height=560,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK),
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
    yaxis=dict(visible=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
)
st.plotly_chart(fig, width="stretch")


# =============================================================================
# Prediction against ground truth
# =============================================================================

st.markdown("#### Prediction against the CasADi solution")

tabs = st.tabs(list(CFG.heads.keys()))
for tab, (label, (pred_col, truth_col, unit, dp)) in zip(tabs, CFG.heads.items()):
    with tab:
        if pred_col not in df.columns or truth_col not in df.columns:
            st.warning(
                f"Need both `{pred_col}` and `{truth_col}` in the circuit file "
                "to draw this comparison."
            )
            continue

        err = df[pred_col] - df[truth_col]
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Median absolute error", f"{err.abs().median():.{dp}f} {unit}")
        m2.metric("95th percentile", f"{err.abs().quantile(0.95):.{dp}f} {unit}")
        m3.metric(
            "Signed bias",
            f"{err.mean():+.{dp}f} {unit}",
            help="One-directional bias here is the known systematic effect, "
            "not boundary noise.",
        )

        trace = go.Figure()
        trace.add_trace(
            go.Scattergl(
                x=df[CFG.sector_col],
                y=df[truth_col],
                mode="lines",
                line=dict(color=TRUTH, width=2),
                name="CasADi / IPOPT",
            )
        )
        trace.add_trace(
            go.Scattergl(
                x=df[CFG.sector_col],
                y=df[pred_col],
                mode="markers",
                marker=dict(size=5, color=Z_MODE),
                name="Surrogate",
            )
        )
        trace.update_layout(
            height=380,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=INK),
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title="Micro-sector", gridcolor=GRID, zeroline=False),
            yaxis=dict(title=f"{label} ({unit})", gridcolor=GRID, zeroline=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        )
        st.plotly_chart(trace, width="stretch")


# =============================================================================
# Live solve — local only
# =============================================================================

with st.expander("Solve one sector with CasADi"):
    if not CFG.enable_live_solve:
        st.write(
            "Disabled on the deployed build. IPOPT batches are what this "
            "framework exists to avoid running trackside, and the free tier "
            "gives two cores. Set `enable_live_solve = True` to arm it locally."
        )
    else:
        sector = st.number_input(
            "Sector", 0, int(df[CFG.sector_col].max()), 0, key="solve_sector"
        )
        if st.button("Solve"):
            try:
                from solver import solve_sector  # your Phase 2 entry point

                t0 = time.perf_counter()
                truth = solve_sector(
                    df[df[CFG.sector_col] == sector].iloc[0].to_dict(),
                    soc_start=soc_start,
                )
                solve_ms = (time.perf_counter() - t0) * 1000

                a, b = st.columns(2)
                a.metric("Solver", f"{solve_ms / 1000:.2f} s")
                b.metric(
                    "Surrogate",
                    f"{elapsed_ms / max(len(df), 1):.2f} ms",
                    f"{solve_ms / max(elapsed_ms / len(df), 1e-9):,.0f}× faster",
                )
                st.json(truth)
            except ImportError:
                st.error(
                    "`solver.solve_sector` not importable. Point the import at "
                    "your Phase 2 entry point."
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Solve failed: {exc}")


# =============================================================================
# Table
# =============================================================================

with st.expander("Per-sector values"):
    cols = [CFG.sector_col, "mode", "sector_length"] + [
        c for pair in CFG.heads.values() for c in pair[:2] if c in df.columns
    ]
    st.dataframe(df[cols], width="stretch", height=420)
    st.download_button(
        "Download as CSV",
        df[cols].to_csv(index=False).encode(),
        file_name=f"{res['circuit'].lower().replace(' ', '_')}_setup.csv",
        mime="text/csv",
    )
