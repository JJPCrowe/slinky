import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")
fails = df[~df["ocp_converged"]]
df_ok = df[df["ocp_converged"]]
print(
    df_ok[
        ["d_X_optimal", "v_taper_optimal", "d_coast_optimal", "dt_optimal"]
    ].describe()
)
print(f"Total: {len(df):,} | Failed: {len(fails)} ({100 * len(fails) / len(df):.3f}%)")
print(
    f"\nFailures concentrate in {fails['sector_id'].nunique()} unique sector(s) "
    f"out of {df['sector_id'].nunique():,} total\n"
)

print("Exit codes:")
print(fails["ocp_status"].value_counts())

print("\nBy SoC:")
print(fails.groupby("initial_SoC").size())

print("\nTop failing sectors:")
print(fails.groupby("sector_id").size().sort_values(ascending=False).head(10))

print("\nGeometry of failing sectors:")
print(
    fails[
        [
            "sector_id",
            "v_exit_kph",
            "v_entry_target_kph",
            "L_straight_m",
            "initial_SoC",
            "ocp_status",
        ]
    ]
    .drop_duplicates(subset=["sector_id"])
    .to_string()
)
