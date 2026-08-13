remote root: /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
source of truth: GitHub

# ELM_Futu_landuseInput

Local mirror/workspace for future land-use input preparation. See the workspace
root `AGENTS.md` for Pathfinder safety, SSH, and Slurm rules, and
`pathfinder_slurm_p_q_mem.md` at the workspace root for partition, QoS, and
memory selection.

The remote root is on persistent project NFS. Keep durable code, Slurm scripts
under `jobs/`, and small configs in Git here; keep NetCDF, harmonization
products, and figures remote or in ignored local paths.

## Versioning model

GitHub is the authoritative version history for code, Slurm scripts,
documentation, and small configs. This local directory and the declared
Pathfinder remote root are mirrors/workspaces. Changes may originate locally or
on Pathfinder; after meaningful code/config/job/documentation changes, sync them
into this project Git repository, commit, and push to GitHub.

Use `scp` or `rsync` in either direction only after making the direction explicit:
`remote -> local` to refresh this mirror from Pathfinder, or `local -> remote` to
stage files on Pathfinder for a run. Do not use `rsync --delete` unless the user
explicitly requests that exact deletion behavior.

## Documents and code

The maintained ELM forcing path is
`scripts/02_harmonize_seus.py --build-timeseries`. Chen 1 km rasters are first
re-aggregated onto the target grid with
`scripts/01_chen2022_to_elm_landuse.py --like <target>`. Diagnostic and figure
scripts live in `scripts/analysis/`; Slurm drivers in `jobs/`. NetCDF products
stay on Pathfinder under `outputs/` (gitignored). `future_climate/` is a
separate climate-forcing check, not part of this land-use pipeline.

| File | Role |
|---|---|
| `REFERENCE.md` | Chen2022 → ELM mapping, aggregation, NLCD vs Chen comparison (§10–12) |
| `HARMONIZATION_SEUS_PILOT.md` | §13 method spec (formulas). Implemented; ELM forcing uses `--build-timeseries` |
| `FUTURE_LANDUSE_TIMESERIES.md` | Build and verify the SEUS `landuse.timeseries` 2024–2100 product |
