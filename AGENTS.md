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
