import pandas as pd

df = pd.read_parquet("output/microsectors_combined_Q_labels.parquet")

# Failure rate by SoC (does it cluster at low or high battery?)
print("Convergence by initial SoC:")
print(df.groupby("initial_SoC")["ocp_converged"].mean().round(3))

# What does the solver actually say about the failures?
print("\nFailure status breakdown:")
print(df[~df["ocp_converged"]]["ocp_status"].value_counts())

# Iteration counts of failed solves (did they hit max_iter, or fail fast?)
print("\nIterations on failed solves:")
print(df[~df["ocp_converged"]]["ocp_iterations"].describe())

# Sector geometry of the failures
print("\nFailing sectors:")
print(
    df[~df["ocp_converged"]][
        [
            "sector_id",
            "initial_SoC",
            "ocp_status",
            "ocp_iterations",
            "v_exit_kph",
            "v_entry_target_kph",
            "L_straight_m",
        ]
    ].to_string()
)
