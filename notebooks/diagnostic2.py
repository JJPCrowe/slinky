import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")
df_ok = df[df["ocp_converged"]]

print("Label distributions on converged solves:")
print(
    df_ok[
        ["d_X_optimal", "v_taper_optimal", "d_coast_optimal", "dt_optimal"]
    ].describe()
)

# d_X should fall within [0, L_straight]
oob_dx = df_ok[
    (df_ok["d_X_optimal"] > df_ok["L_straight_m"]) | (df_ok["d_X_optimal"] < 0)
]
print(f"\nd_X out of bounds: {len(oob_dx)}/{len(df_ok)}")

# How often does the optimal solution actually use X-mode?
no_switch = df_ok["d_X_optimal"].isna()
print(
    f"No X-mode activation: {no_switch.sum()}/{len(df_ok)} ({100 * no_switch.mean():.1f}%)"
)

# d_coast should be in [0, L_straight]
oob_dc = df_ok[
    (df_ok["d_coast_optimal"] > df_ok["L_straight_m"]) | (df_ok["d_coast_optimal"] < 0)
]
print(f"d_coast out of bounds: {len(oob_dc)}/{len(df_ok)}")
