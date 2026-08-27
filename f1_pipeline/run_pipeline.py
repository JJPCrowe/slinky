"""Pipeline entry point.

Usage examples
--------------

Single session (sanity check before the long run):
    python run_pipeline.py --year 2025 --gp Silverstone --session Q

Full 2025 season (the production run):
    python run_pipeline.py --year 2025 --season

Override default tunables:
    python run_pipeline.py --year 2025 --season --curvature-threshold 0.004
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from f1_pipeline.config import OUTPUT_DIR, PipelineConfig
from f1_pipeline.pipeline import (
    init_cache,
    process_season,
    process_session,
    save_outputs,
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--gp", type=str, default=None,
                   help="GP name (omit if using --season)")
    p.add_argument("--session", type=str, default="Q",
                   choices=["FP1", "FP2", "FP3", "Q", "S", "SS", "R"])
    p.add_argument("--season", action="store_true",
                   help="Process the whole season instead of one GP")
    p.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    p.add_argument("--cache-dir", type=str, default="./fastf1_cache")
    p.add_argument("--tag", type=str, default=None,
                   help="Filename tag (defaults to year or year_gp)")
    p.add_argument("--curvature-threshold", type=float, default=None)
    p.add_argument("--resample-dx", type=float, default=None)
    p.add_argument("--verbose", "-v", action="count", default=0)
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    level = logging.WARNING - 10 * args.verbose
    logging.basicConfig(
        level=max(level, logging.DEBUG),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Build config with any CLI overrides
    overrides = {}
    if args.curvature_threshold is not None:
        overrides["curvature_threshold"] = args.curvature_threshold
    if args.resample_dx is not None:
        overrides["resample_dx"] = args.resample_dx
    config = PipelineConfig(**overrides) if overrides else PipelineConfig()

    init_cache(Path(args.cache_dir))

    if args.season:
        features, diagnostics = process_season(args.year, args.session, config)
        tag = args.tag or f"{args.year}_{args.session}"
    else:
        if args.gp is None:
            raise SystemExit("--gp required when not using --season")
        features, diags_list = process_session(args.year, args.gp, args.session, config)
        import pandas as pd
        diagnostics = pd.DataFrame(diags_list)
        tag = args.tag or f"{args.year}_{args.gp.replace(' ', '_')}_{args.session}"

    if features.empty:
        print("No features extracted - check logs for errors.")
        return

    feat_path, diag_path = save_outputs(
        features, diagnostics, Path(args.output_dir), tag
    )

    print(f"\nExtracted {len(features)} micro-sectors")
    print(f"  features    -> {feat_path}")
    print(f"  diagnostics -> {diag_path}\n")

    # Quick summary
    print("Feature DataFrame summary:")
    print(features.describe(include="all").T[["count", "mean", "min", "max"]].to_string())
    print()
    if not diagnostics.empty:
        print("Detector agreement (median per circuit):")
        agg = diagnostics.groupby("gp")["agreement_rate"].median().sort_values()
        print(agg.to_string())


if __name__ == "__main__":
    main()
