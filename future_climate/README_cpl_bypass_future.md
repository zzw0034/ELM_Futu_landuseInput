# Future (2024-2100) CPL_BYPASS climate forcing — design and pipeline

How the SEUS 4km ELM case reads CanESM5-DBCCA-TESSFA2 SSP forcing past 2023,
and how the forcing files themselves are built. Written 2026-08-17 alongside
the implementation; see git log in both this repo and the E3SM checkout for
the current state if this drifts.

Related: `README.md` in this directory (the historical/future splice and bias
work this builds on), [[tessfa2_future_climate_cpl_bypass_patch]] and
[[tessfa2_cpl_bypass_zone_mapping_mystery]] in the auto-memory system.

---

## 0. The question this answers

The finished historical case (`20260723_Southeast_hires_s7P_s8hdmfix_harvfix_
ICB20TRCNPRDCTCBC`) has a restart file at 2024-01-01. Can a future run just
pick up from there and read `CanESM5_<scenario>_r1i1p1f1_DBCCA_Daymet_
TESSFA2` forcing (already produced, sitting in `/projects/hpcl-cli185/
proj-shared/TESSFA/CanESM5/`) directly? **Not as-is.** The CPL_BYPASS met
reader in `lnd_import_export.F90` has two hardcoded assumptions that block a
naive "just start reading in 2024" approach — see §1.

## 1. Why the historical CPL_BYPASS reader can't just start at 2024

Source: `components/elm/src/cpl/lnd_import_export.F90` (E3SM checkout at
`/projects/hpcl-cli185/proj-shared/zw5/E3SM`), the `metsource == 6`
(`era5`-in-`metdata_type`) branch, ~line 240-460.

1. **The filename is built from a literal string, not a config value.** For
   `metdata_type` containing `daymet`, the code constructs
   `'Daymet_ERA5_TESSFA.4km_' // VAR // '_1980-2023_z01.nc'` — the year range
   is baked into the source, not read from a namelist.
2. **The time index is an absolute offset from a hardcoded `startyear_met`.**
   For the daymet branch, `startyear_met = 1980`. Once a run's model year
   exceeds `endyear_met_spinup` (1999), the reader computes
   `tindex = (yr - startyear_met) * 365 * 8` and reads that as an absolute
   record position in the currently-open file — for `yr=2024` that's index
   `128480`, exactly the length of the existing 1980-2023 file. **Any file
   this branch opens must behave as if it starts at 1980**, even if a run
   only ever asks for years >= 2024.

Two ways to satisfy that: duplicate the full 1980-2023 record inside every
scenario's future file (no code change, ~4TB across 4 scenarios — the
`/projects/hpcl-cli185` filesystem was 98% full with 46TB free when this was
scoped, so that was rejected), or **give the future branch its own
`startyear_met`** so it doesn't need to carry 44 redundant years. We took the
second path — see §2.

## 2. The source patch

E3SM commit `f07c14d429`, "Add a future (2024-2100) branch to the cpl_bypass
era5-daymet met reader". Adds `metdata_type='era5-daymet-fut'`:

- `startyear_met = 2023`, `endyear_met_spinup = 2023`, `endyear_met_trans = 2100`
- filename: `DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc`

Everything else (the `zone_mappings.txt` nearest-neighbor grid lookup, int16
packing/decoding, the per-timestep read loop) is unchanged — the new branch
is a thin variant of the existing `use_daymet` path, not a new mechanism.

### Why `startyear_met = 2023`, one year *before* the real data (2024)

There's a second, separate hardcoded check further down the same subroutine,
shared by every met source, that runs on every timestep *after* the first:

```fortran
if (const_climate_hist .or. yr .le. atm2lnd_vars%startyear_met) then
   if (tindex(g,v,1) .gt. timelen_spinup(v)) tindex(g,v,1) = 1   ! wraps back to record 1
```

If `startyear_met` were set to 2024 (the future run's actual first model
year), `yr .le. startyear_met` stays **true for the entire first year**, and
the model would keep wrapping back to 2024-01-01 instead of advancing —
silently, no crash, just a run that never gets past day 1 of the real
forcing. Existing met sources never hit this because they always start their
run well before their own `startyear_met` (the historical run starts in 1850,
130 years before its `startyear_met=1980`), so this edge case had never come
up before a run whose very first model year is also the forcing's first
record.

The fix: pad the file with **one unused year** (nominal 2023) so
`startyear_met` sits strictly below the future run's real first year (2024).
`yr .le. startyear_met` (`2024 .le. 2023`) is then false from day 1 onward,
and the run takes the same code path every other post-spinup year already
takes. Cost: ~9GB/variable for the padding, instead of ~44 years'
(~1TB/variable) worth if we'd had to match the historical branch's own
`startyear_met=1980` convention. The padding year is never actually read by
a run that starts at 2024 — it exists only to move the boundary condition.

This was **not** fixed by editing the shared bound-check itself, to avoid any
risk of changing behavior for other met sources or the historical branch,
which are known-working and depended on by finished/running cases.

## 3. Ocean/invalid-cell fill value

User instruction: keep it consistent with the historical convention, not a
new fill value. The historical cpl_bypass files don't use NaN for invalid
cells — each variable has a fixed **raw packed sentinel** (an artifact of how
the original production Fortran script casts a NaN source value to a 16-bit
integer, not a deliberately chosen fill value), verified 2026-08-17 to be
constant across 200 random ocean indices x 4 time slices per variable:

| var | raw sentinel | add_offset | scale_factor | decoded value |
|---|---|---|---|---|
| TBOT | 22725 | 262.5 | 0.005874634 | 396.0 K |
| PSRF | -23831 | 70000.0 | 3.356933594 | -9999.1 Pa |
| QBOT | -14592 | 0.05 | 0.000003357 | 0.0010 kg/kg |
| FSDS | -30984 | 990.0 | 0.067810059 | -1111.0 W/m² |
| PRECTmms | -32768 | 0.0 | 0.000002686 | -0.0880 mm/s |
| WIND | -14600 | 49.5 | 0.003390503 | -0.0013 m/s |
| FLDS | 14924 | 500.0 | 0.033569336 | 1000.99 W/m² |

The future files reuse these exact raw values (not the decoded ones — the
packing is a plain scale/offset, so the raw short is what actually gets
written) for every ocean/invalid gridcell, and for **every cell** of the
dummy 2023 year (real ocean cells and would-be-land cells alike, since none
of that year is real data). This makes the dummy year fail loud if it's ever
read by mistake — it decodes to an obviously unphysical value rather than
something that could pass for real data.

`add_offset`/`scale_factor` per variable match the historical production
script's fixed physical ranges (`makezones_reanalysis.f90`, `data_ranges`
array) — same packing convention both sides of the 2023/2024 splice.

## 4. Grid ordering

The flattened `n=225625` dimension in every cpl_bypass file — historical and
future — is ordered `n = ilon*361 + ilat` (longitude outer loop, latitude
inner loop, both ascending). The future files' own `lon`/`lat` coordinate
arrays are already in this same ascending order, so building the merged
`n`-ordered array is a transpose + reshape, not a real remap.

**There are two different files both named `zone_mappings.txt`** — this
tripped up an earlier version of this pipeline, worth being explicit about:

- `Daymet_ERA5_TESSFA2/zone_mappings.txt` (parent dir): the *original*
  7-zone table (zone column 2-7 across most of the domain, `grid_map` resets
  to 1 at the start of each zone). Matches `cpl_bypass_full/7zone/`, the
  never-merged per-zone files.
- `Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt`: what
  `metdata_bypass` (which points at `cpl_bypass_full/`) + `'/zone_mappings.txt'`
  actually resolves to in the Fortran reader. **Every row's zone is
  flattened to 1**, and `grid_map` is a single **global** 1..225,625 index,
  not a per-zone one.

Confirmed via `md5sum` (different) and a full-file diff: identical row
count and identical `lon`/`lat` columns line-for-line, but the zone/grid_map
columns differ from line 34,657 onward (i.e. everywhere outside the
original zone 1).

This is the actual mechanism behind an earlier open question (why a
zone-2+ gridcell doesn't crash trying to open a nonexistent `z02.nc`, see
[[tessfa2_cpl_bypass_zone_mapping_mystery]] for the full trail including the
model-output cross-check that first confirmed reads were landing on the
right gridcell before this was found): the reader always computes zone=1 for
every point using the `cpl_bypass_full/` copy, so it always builds a `z01`
filename and always finds it — it never has a reason to look for
`z02`..`z07`. And since `grid_map` in that copy is already the global index,
reading position `gtoget` directly out of the merged `z01.nc` lands on the
right row with no offset arithmetic needed.

**The bug this uncovered**: this pipeline's `ZONE_MAPPINGS` constant, and
the `zone_mappings.txt` copied into each scenario's output directory, were
both reading the wrong (parent-dir, 7-zone) file. Grid order itself was
unaffected (lon/lat columns are identical), but a future case launched with
that copy would have computed zone 2-7 for most of the SEUS domain and
crashed trying to open `DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z02.nc` etc.,
which don't exist (only `z01` is generated). Fixed to source from
`cpl_bypass_full/zone_mappings.txt` in both the Python script and the sbatch
copy step.

## 5. Calendar

Source CanESM5-DBCCA-TESSFA2 data use a standard (Gregorian) calendar — Feb
2024's `TPHWL3Hrly` file has 232 3-hourly steps (29 days), not 224. The model
case (`CALENDAR=NO_LEAP` in `env_build.xml`) needs a fixed 365 days/year,
2920 steps/year. The converter strips every Feb 29 (checked by reconstructing
each timestep's date from the source file's `time` variable, not by
assuming a fixed day count) before packing.

## 6. Processing pipeline and files

- `scripts/10_build_future_cpl_bypass.py` — builds one
  `DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc` for one (scenario, variable)
  pair.
- `jobs/submit_future_cpl_bypass.sbatch` — one Slurm job per (scenario,
  variable); set `SCENARIO`/`VARNAME` via `--export`. `-c 16 --mem=96g`.

**How the conversion actually runs**: 924 months (77 years x 12) of source
data need reading, packing, and writing per variable per scenario. The
per-month unit of work (`process_month`: read one source `clmforc.*.nc`
file, strip Feb 29 if present, transpose/flatten to the `n=225625` grid
order, pack to int16) is CPU/IO-bound and embarrassingly parallel across
months — the position each month writes to (`month_start_step`) is pure
arithmetic (dummy-year offset + fixed NOLEAP month lengths), independent of
processing order, so workers can finish in any order without a running
counter.

Runs via `concurrent.futures.ProcessPoolExecutor`, one process per
`SLURM_CPUS_PER_TASK` (16), with a **bounded sliding window**: at most
`2 x nworkers` months are ever in flight (submitted-but-unwritten) at once.
Only the main process ever touches the output file — workers return
`(year, month, start_index, packed_array)` and the main process writes each
directly to its known position, so out-of-order completion is safe by
construction. The bound matters (see §6.1): workers can finish faster than
the main process drains results, and an unbounded submit lets that backlog
grow without limit.

`DTIME` is pure arithmetic too (doesn't depend on any source data), so it's
written in one vectorized call instead of one per timestep.

### 6.1 Bug history (2026-08-17, same session as the initial patch)

Four real bugs surfaced while scaling this up from a smoke test to the full
77-year run, in order:

1. **CPU-bound compression.** First version wrote NetCDF4 with
   `zlib, complevel=4`. Measured 94.6% single-core CPU on the writer process
   — compression, not disk/network I/O, was the bottleneck (confirmed before
   assuming a faster filesystem would help: it wouldn't have). Fix: dropped
   compression — the uncompressed storage budget (~2.9TiB for all 7 vars x 4
   scenarios) fits comfortably in the ~46TB free on `/projects/hpcl-cli185`,
   so there was nothing to trade for.
2. **OOM #1: unbounded backlog.** First parallel version submitted all 924
   months to the pool up front. Workers (16, without compression) completed
   faster than the main process's netCDF writes could drain them; completed-
   but-unconsumed results (each a full packed month, 100+MB) piled up in
   memory — killed at `--mem=48g` in ~90s. Fix: the bounded sliding window
   described above.
3. **OOM #2: per-worker temporaries.** Even with the window fix, still
   OOM-killed. Root cause: `read_month` upcast the (already float32) source
   to float64, and `pack_month`'s `(arr - add_off) / scale` chain allocated a
   fresh float64-sized temporary at every step — measured peak ~2-3GB/worker
   against source data that's only ~223MB/month. Fix: stayed in float32
   throughout, did the offset/scale/round/clip chain in place on one buffer.
   Peak dropped to ~700MB/worker.
4. **Silent data corruption (not a crash — the dangerous kind).** With the
   OOM fixed, first two full-scale attempts wrote successfully but read back
   wrong: `pack_month`/`process_month` were proven bit-reproducible in
   isolation, but small-scale windowed tests (24, then 48 months) started
   failing spot-checks. Root cause: output was NetCDF4 with
   `chunksizes=(NCELL, STEPS_PER_YEAR)` — one chunk = one full year, ~1.3GB —
   and HDF5's default per-variable chunk cache is a few MB. Scattered,
   out-of-order, partial (one month at a time) writes into the same
   1.3GB chunk could evict/reload it between writes and silently lose an
   earlier month's data with **no error at all**. Enlarging the chunk cache
   to fit one full chunk (`set_var_chunk_cache`) fixed it at small scale
   (0/24, then 0/48 months verified correct across multiple year-chunk
   boundaries) — but **broke again at the real 78-year/924-month scale**,
   almost certainly because enough out-of-order year-chunks were in flight
   to thrash a cache sized for only one. Real fix: stopped using NetCDF4
   chunking altogether. Switched output format to **NETCDF3_64BIT_OFFSET**
   (`ncdump -k` confirms this is exactly what the *historical*
   `Daymet_ERA5_TESSFA.4km_*_1980-2023_z01.nc` files already are — this
   script had been using NetCDF4 for no real reason). Classic format has no
   chunking at all: writes are direct positional I/O, same as the Fortran
   production script (`makezones_reanalysis.f90`) that built the historical
   files, so this whole bug class doesn't apply.
5. **Variable creation itself hung.** First classic-format attempt: a
   120-month windowed test timed out at 20 minutes with *zero* output, not
   even the first print statement after `createVariable`. Root cause:
   classic NetCDF's `nc_enddef()` pre-writes a fill value across a
   variable's *entire declared extent* (here, ~96GiB) before any real data
   can be written, unless fill is explicitly disabled. Fix:
   `createVariable(..., fill_value=False)` — safe here because every DTIME
   index gets written (dummy year + all 924 months, contiguous, no gaps), so
   there's nothing for a fill value to ever be read back.
6. **Strided-write throughput.** With the fill-value hang fixed, timed
   individual month-writes directly: **76-99 seconds each**, sequential or
   out-of-order alike (~1.4MB/s effective for a ~108MB write — far below any
   plausible storage bandwidth on either `/projects` or `/scratch`, i.e.
   latency/overhead-bound, not bandwidth-bound). At that rate, 924
   months/variable would be ~20 hours. Cause: the file's dimension order is
   `(n, DTIME)` with `DTIME` fastest-varying (required — matches the
   historical files and what the Fortran reader expects for its per-column
   full-time-series reads), so a write covering a time range but all `n`
   touches all 225,625 rows non-contiguously, once per write call. Fix:
   batch writes per **year** instead of per-month — buffer a year's 12
   completed months (in memory, keyed by year; task submission order plus
   the sliding window means only a few years are ever partially buffered at
   once) and issue one write per year instead of twelve. Each row then gets
   touched once per year instead of twelve times. Measured a clean **~12x**
   speedup (80s for one full year vs. ~920-1190s for 12 separate
   month-writes covering the same data).

Also added, same session, lower-severity robustness fixes from a code
review: `set_auto_scale(False)` on the output variable (writes are already
packed int16, not physical values — belt-and-suspenders against
implicit/version-dependent auto-pack-on-write behavior, even though it
wasn't observed to actually be corrupting output here); write under a
`.partial` suffix and only rename to the real filename after every year is
confirmed written and the file closed cleanly, so an interrupted run can
never leave something at the expected path that looks complete but isn't;
`zone_mappings.txt` row-count validated against `NCELL` instead of assumed.

**Verified** (2026-08-17): first the actual production `main()` end-to-end
with `Y1` monkey-patched to a 3-year range for speed (all 3 years written,
dummy year all-sentinel, 9 spot-checked months matched independent
recomputation, temp-file rename happened only on success), then the real
77-year job itself (job 464556, TBOT/ssp245, `sbatch ... --mem=96g`):
**completed in 4h32m**, no errors. Post-hoc verification against the actual
output file (reading a 300-point sample of `n` rather than all 225,625 --
even *reads* spanning a time-slice across all `n` hit the same
strided-access slowness as the writes did, see above): dummy year
confirmed all-sentinel at 3 positions, 7 months spread across the entire
2024-2100 range matched independent recomputation exactly, decoded
temperatures at 3 widely-spaced timesteps all fell in the expected
~230-320K physical range, land/ocean split (160/300 sampled) matched the
historical ~52% land fraction. File: `/scratch/hpcl-cli185/zw5/future_clim/
ssp245/DBCCA_Daymet_TESSFA2_TBOT_2023-2100_z01.nc`, 102,780,328,956 bytes.

**Lesson for future variables/scenarios**: match the historical file format
exactly (`NETCDF3_64BIT_OFFSET`, no chunking, no compression, fill disabled)
rather than reaching for NetCDF4 features that aren't needed here, and batch
writes at whatever granularity keeps per-call row-touches low given the
fixed `(n, DTIME)` layout the reader requires.

```bash
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
sbatch --export=ALL,SCENARIO=ssp245,VARNAME=TBOT jobs/submit_future_cpl_bypass.sbatch
# repeat for the other 6 variables and 3 remaining scenarios (28 jobs total)
```

Output lands in `/scratch/hpcl-cli185/zw5/future_clim/<scenario>/`, one file
per variable plus a copied `zone_mappings.txt`. **Deliberately on `/scratch`,
not `/projects`** — user's call, since `/scratch` is Lustre-backed and
faster for this write pattern than the NFS-mounted `/projects`, and
`/projects/hpcl-cli185` was already 98% full (§1). `/scratch` is subject to
periodic purging, unlike `/projects` — fine for generating/validating output
now, but before an actual 2024-2100 case run, confirm these files still
exist or move them to a durable location under `/projects` and update
`metdata_bypass` (and the `future_clim` path referenced below) accordingly.

To use it in a future case's `user_nl_elm`:

```
metdata_type   = 'era5-daymet-fut'
metdata_bypass = '/scratch/hpcl-cli185/zw5/future_clim/<scenario>'
```

(requires the patched E3SM build — see §7.)

## 7. Rebuilding E3SM after the source patch

The case family under `/projects/hpcl-cli185/proj-shared/zw5/e3sm_cases/`
built from `20260712_Southeast_hires_s7P_s8hdm_ICB1850CNRDCTCBC_ad_spinup`
shares one build directory (`EXEROOT`) across the whole 1850/20TR family.
Rebuild it (picks up the source patch for every case that shares it) with:

```bash
sbatch /projects/hpcl-cli185/proj-shared/zw5/E3SM/jobs/build_future_climate_fix.slurm
```

Same pattern as the earlier Ndep/HDM fix rebuild (`build_ndep_fix.slurm`,
`verify_casebuild_fix.slurm`) — `parallel` partition, `--constraint=BL`, 32
cpus, 120G, 30 min, just runs `./case.build` in the case root.

## 8. Storage

Per-variable file size = `225,625 cells x 227,760 steps (1 dummy + 77 real
years x 2920) x 2 bytes` ~ 96 GiB (classic format, no compression — see
§6.1 for why compression was dropped), plus a small amount of header/DTIME/
LONGXY/LATIXY overhead. 7 variables x 4 scenarios ~ **2.6 TiB** total (vs.
~4.1 TiB for the no-code-change alternative that would have had to
duplicate 1980-2023 in every scenario file — see §1). Output as of this
writing lives on `/scratch` (§6, has its own ~134TB free, separate from
`/projects/hpcl-cli185`'s ~46TB), not counted against the `/projects` budget
that originally motivated avoiding the no-code-change alternative — but the
2.6TiB comparison itself is unaffected by which filesystem ends up holding
it.

## 9. What this does *not* cover

- The future case's `flanduse_timeseries` only covers 1850-2023 — extending
  it to 2100 is a separate, not-yet-started task (see
  `seus_task_backlog.md`, item 2).
- N-deposition and CO2 forcing for the SSP scenarios past 2023 — same
  backlog item, still blocked on source data as of the last check
  ([[elm_cpl_bypass_forcing_constraints]]).
- Actually configuring and submitting a future production case (RUN_TYPE,
  STOP_N, `finidat`, etc.) — this document only covers the *forcing data*
  and the *reader* for it.
