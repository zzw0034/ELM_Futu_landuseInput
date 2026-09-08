<!-- ARCHIVED 2026-09-08.
     This is the README that lived at /scratch/hpcl-cli185/zw5/future_clim/,
     preserved verbatim below before that directory was deleted.

     Why the directory was deleted: /scratch reached 191.2 TiB against the
     hpcl-cli185 project's 200 TiB soft quota, and the seven 77-year future
     runs need 10.6 TiB. This copy was 2.7 TiB of data that already exists,
     byte-identical, at the world-shared path the README itself names as
     canonical -- all 28 files matched on the sha256_after recorded when both
     copies were patched, and every file matched in size. None of the running
     jobs read it; all three batch-1 chains point at world-shared.

     Note the reversal it records: on 2026-08-19 the user asked for this copy
     to be KEPT as a backup after the sync. That instruction was superseded on
     2026-09-08. The copy removed was the one on the non-durable filesystem;
     the durable /projects copy, which this README calls the one to rely on,
     remains.
-->

# future_clim -- TESSFA2 future CPL_BYPASS forcing (backup copy)

This directory holds the full output of the TESSFA2 (Southeast US) future
climate forcing pipeline: 4 scenarios (ssp119/ssp245/ssp370/ssp585) x 7
variables (PRECTmms/FSDS/TBOT/QBOT/FLDS/PSRF/WIND) = 28 files, ~96 GiB each,
covering 2024-2100. Built by
`/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass/`
(see that directory's README for the pipeline itself).

## Status: backup copy, not the canonical location

The canonical copy that `metdata_bypass` should actually point at lives at:

```
/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/
```

This `/scratch` copy was synced there on 2026-08-19 (Slurm job 465730, via
`future_climate/ops/sync_to_worldshared.sh` in the same git repo) and is
being **kept here intentionally as a backup**, per the user's instruction
(2026-08-19) not to delete it after the sync.

## Important: /scratch is purged periodically

This is NOT a durable backup location by Pathfinder policy -- files here can
be deleted by the system on its own schedule, independent of anything in
this README. If this copy still matters when you read this, verify it still
exists, and do not treat its presence as guaranteed. The world-shared copy
above is the one that should be relied on.

## Verification already done (2026-08-19)

- New pipeline output verified byte-identical to the previous (slower)
  pipeline's output, for every variable spot-checked.
- All 28 files passed a structural ELM-readability check against the
  historical cpl_bypass files (format, dimensions, variable types,
  add_offset/scale_factor, grid ordering).
- Spot-checked months re-packed independently from source and compared
  value-for-value against the output -- exact match.

Not yet done: an actual ELM run reading these files at runtime (only the
files' bytes and structure have been verified, not a live model read).
