import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")
df_ok = df[df["ocp_converged"]]

print("d_X by sector_id:")
print(
    df_ok.groupby("sector_id")["d_X_optimal"]
    .agg(["mean", "std", "min", "max"])
    .round(2)
)

print("\nd_X by initial_SoC:")
print(df_ok.groupby("initial_SoC")["d_X_optimal"].agg(["mean", "std"]).round(2))

print("\nLabel-input correlation matrix:")
print(
    df_ok[
        [
            "d_X_optimal",
            "v_taper_optimal",
            "d_coast_optimal",
            "dt_optimal",
            "v_exit_kph",
            "v_entry_target_kph",
            "L_straight_m",
            "initial_SoC",
        ]
    ]
    .corr()
    .round(2)
)
