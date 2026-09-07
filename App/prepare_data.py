"""
Slice the full label set into one small parquet per circuit.

The deployed container has 2.7 GB of RAM and has to hold pandas, sklearn, plotly
and 24 model folds alongside your data. Loading an 800k-row table to display one
lap wastes nearly all of it, so cut once, offline, and commit the slices.

    python prepare_data.py \
        --source data/microsectors_combined_Q_labels_v4.parquet \
        --out app/data/circuits \
        --circuit-col circuit

Check the total afterwards. If it clears ~50 MB, drop columns rather than
reaching for Git LFS — Community Cloud clones the repo on every rebuild.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

# Only these reach the front end. Anything else is dead weight in the container.
KEEP = [
    "sector_id",
    "x",
    "y",
    "sector_length",
    "curvature_entry",
    "curvature_exit",
    "v_entry",
    "v_exit_target",
    "elevation_delta",
    "d_X_ocp",
    "d_coast_ocp",
    "P_deploy_ocp",
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--circuit-col", default="circuit")
    ap.add_argument(
        "--soc",
        type=float,
        default=None,
        help="If labels are keyed by starting SoC, pin one grid point per circuit. "
        "Without this you will ship every SoC sweep and blow the size budget.",
    )
    ap.add_argument("--soc-col", default="soc_start")
    args = ap.parse_args()

    df = pd.read_parquet(args.source)
    print(f"loaded {len(df):,} rows, {len(df.columns)} columns")

    if args.soc is not None and args.soc_col in df.columns:
        nearest = df[args.soc_col].unique()
        pick = min(nearest, key=lambda v: abs(v - args.soc))
        df = df[df[args.soc_col] == pick]
        print(f"pinned {args.soc_col}={pick} -> {len(df):,} rows")

    missing = [c for c in KEEP if c not in df.columns]
    if missing:
        print(f"warning: not in source, skipping: {', '.join(missing)}")
    cols = [c for c in KEEP if c in df.columns]

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for circuit, group in df.groupby(args.circuit_col):
        out = group[cols].copy()
        for c in out.select_dtypes("float64").columns:
            out[c] = out[c].astype("float32")
        path = args.out / f"{slugify(circuit)}.parquet"
        out.to_parquet(path, index=False, compression="zstd")
        size = path.stat().st_size / 1e6
        total += size
        print(f"  {path.name:<32} {len(out):>6,} rows  {size:>6.2f} MB")

    print(f"\ntotal {total:.1f} MB across {len(list(args.out.glob('*.parquet')))} circuits")
    if total > 50:
        print("that is too large to commit comfortably — drop columns or SoC points")


if __name__ == "__main__":
    main()
