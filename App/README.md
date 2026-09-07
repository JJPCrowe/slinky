# Slinky front end

Select a circuit, run the trained surrogate over its micro-sectors, and compare
against the stored CasADi solution. Deployable to a public link.

## Layout

```
app/
├── app.py               entry point
├── prepare_data.py      slices the full label parquet into per-circuit files
├── requirements.txt
├── .streamlit/config.toml
└── data/
    ├── circuits/        one small parquet per circuit
    └── models/          one MLP per LOCO fold
```

## Wiring it to your data

1. **Cut the circuit files.** `prepare_data.py` groups the full label set by
   circuit and keeps only the columns the front end reads. If your labels sweep
   starting SoC, pin one grid point with `--soc`, otherwise you ship the whole
   sweep.

2. **Export the folds.** Name each `mlp_loco_<circuit>.joblib`, matching the
   parquet stem. The app loads the fold in which the selected circuit was held
   out, so every prediction on screen is out-of-sample. This is worth the
   twenty-four files: it turns "has the model seen this track" from an awkward
   viva question into a design feature.

3. **Fix the column names.** Everything the app reads is declared in the
   `Config` block at the top of `app.py`. Until the names match, it falls back to
   a synthetic circuit so you can still judge the layout.

## Deploying

Community Cloud, from the repo, entry point `app/app.py`. Points that will
actually bite:

- **Python version.** Set it in Advanced settings during deployment. Community
  Cloud supports 3.9–3.13 and does not read `runtime.txt` or `.python-version`.
  Your local 3.14 is ahead of that, so pin 3.12 or 3.13 and confirm your models
  unpickle on whichever you choose before you rely on the link.
- **Pin scikit-learn.** An unpinned install will refuse to load models trained on
  a different minor version, and the failure arrives as an unhelpful startup
  error with no logs.
- **Resource ceiling.** 2.7 GB RAM, 2 cores. `@st.cache_resource` keeps a single
  model in memory across interactions; don't remove it.
- **Paths are relative to the repo root,** not the entry point, even when the
  entry point sits in a subdirectory.
- **No FastF1 at runtime.** There is no writable cache directory you can rely on,
  and the first load would be slow enough to look broken.

## Live solving

Off by default. Set `enable_live_solve = True` in `Config` when running locally
and point the import at your Phase 2 entry point. One sector solving in seconds
next to a millisecond prediction is the demonstration; a lap of IPOPT on two
shared cores is just a timeout.
