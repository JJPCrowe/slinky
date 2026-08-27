import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")

labels = [
    "d_X_optimal",
    "v_taper_optimal",
    "P_deploy_mean_optimal",
    "E_deploy_optimal",
    "E_harvest_optimal",
    "E_final",
    "d_coast_optimal",
    "dt_optimal",
]
print(df[labels].describe().round(1).to_string())

print("\nNaN rates:")
print(df[labels].isna().mean().round(4))

print("\nP_deploy_mean > 350 kW:", (df["P_deploy_mean_optimal"] > 350e3).sum())
res = df["E_final"] - (
    df["E_initial"] - df["E_deploy_optimal"] + df["E_harvest_optimal"]
)
print("energy residual |max| (J):", res.abs().max())
print(
    "E_final outside [0, 4 MJ]:",
    ((df["E_final"] < -1) | (df["E_final"] > 4.0e6 + 1)).sum(),
)

# Phase 3 design input: which labels carry the SoC signal now
print("\nCorrelation with initial_SoC:")
print(
    df[
        [
            "P_deploy_mean_optimal",
            "E_deploy_optimal",
            "d_X_optimal",
            "d_coast_optimal",
            "initial_SoC",
        ]
    ]
    .corr()["initial_SoC"]
    .round(2)
)
