import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")

print(
    df[
        [
            "d_X_optimal",
            "v_taper_optimal",
            "P_deploy_mean_optimal",
            "E_deploy_optimal",
            "E_harvest_optimal",
            "E_final",
            "d_coast_optimal",
            "dt_optimal",
        ]
    ]
    .describe()
    .round(1)
)

# Guard effectiveness: NaN rate should be nonzero (guards firing on short
# deployments — that's their job), and surviving slopes physically bounded
print("\nv_taper NaN rate:", round(df["v_taper_optimal"].isna().mean(), 3))
print("max |v_taper| surviving:", df["v_taper_optimal"].abs().max())

# Regulatory compliance: mean deployment power can never exceed 350 kW
print("P_deploy_mean > 350 kW rows:", (df["P_deploy_mean_optimal"] > 350e3).sum())

# Energy conservation (unity efficiency): E_final = E_init - E_deploy + E_harvest
res = df["E_final"] - (
    df["E_initial"] - df["E_deploy_optimal"] + df["E_harvest_optimal"]
)
print("energy residual |max| (J):", res.abs().max())

# Battery bounds integrity
print(
    "E_final outside [0, 4 MJ]:",
    ((df["E_final"] < -1) | (df["E_final"] > 4.0e6 + 1)).sum(),
)
