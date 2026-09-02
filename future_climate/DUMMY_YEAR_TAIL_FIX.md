# The dummy-year tail fix (2026-09-01/02)

One record, in every future CPL_BYPASS forcing file, was wrong. This is what
it was, why it mattered only for the first few timesteps of a cold start, and
what was done about it.

Related: `README_cpl_bypass_future.md` (how these files are built and why the
dummy year exists at all), auto-memory
`tessfa2-dummy-year-tail-interpolation-fix`.

---

## 1. Why there is a dummy year

Every future forcing file `DBCCA_Daymet_TESSFA2*_<VAR>_2023-2100_z01.nc`
starts with one full year of padding (nominal 2023, DTIME records 0-2919)
before the real 2024-2100 data begins at record 2920.

That padding is not data. It exists purely to satisfy a constraint in
`lnd_import_export.F90`: a shared, per-timestep bound check
(`if (const_climate_hist .or. yr .le. atm2lnd_vars%startyear_met)`) wraps
`tindex` back to record 1 whenever the model year is at or below
`startyear_met`. If `startyear_met` were 2024 — the future run's actual first
year — that check would stay true for all of 2024 and the run would silently
re-read 2024-01-01 forever instead of advancing.

Padding the file with one unused year lets `startyear_met = 2023` sit
strictly below the run's first real year, so the check is false from the
first timestep on. Cost: ~9 GB per 4 km variable, versus ~1 TB per variable
if the file had instead been made to start at 1980 like the historical
convention. See `README_cpl_bypass_future.md` §2.

## 2. Why only record 2919 needed fixing

The dummy year was originally filled with each variable's ocean/invalid
**sentinel** at every cell, deliberately: a value that decodes to something
obviously unphysical (TBOT's decodes to 396 K), so that if the padding were
ever read by mistake it would fail loudly rather than pass for real data.

The padding *is* read — by design, on the very first timestep. The reader
computes its starting index once, at cold-start initialization:

```fortran
tindex(g,v,1) = (yr - startyear_met) * 365 * nint(24./timeres(v))
tindex(g,v,1) = tindex(g,v,1) + (caldaym(mon)+day-2) * nint(24./timeres(v))
tindex(g,v,2) = tindex(g,v,1) + 1
```

For a 2024-01-01 cold start with 3-hourly forcing: `(2024-2023)*365*8 = 2920`,
and `caldaym(1)+1-2 = 0`, so `tindex(1) = 2920` and `tindex(2) = 2921`
(1-indexed) — the dummy year's **last** record paired with the **first real**
record. The `day-2` term is a deliberate one-day step back, so that a day's
first timestep interpolates between yesterday's last record and today's
first. Across continuous real data that is exactly right; across the
2023/2024 boundary it reaches into the padding.

From there the per-timestep branch only ever *increments* `tindex`. It never
decrements and never re-enters the initialization formula, because
CPL_BYPASS preloads each gridcell's whole time series rather than re-opening
files per day. So **record 2919 (0-indexed) is the only padding record any
cold start can ever read** — for every variable, at any timestep length.
Records 0-2918 remain unreachable and stay sentinel.

This was derived independently by transcribing the Fortran into a standalone
Python "tindex oracle" rather than by hand, and then confirmed against real
model output (§5).

## 3. The fix

```
record 2919  :=  record 2920
```

The dummy year's last record becomes a verbatim copy of the real first
record. Everything else is untouched.

**No land/ocean mask is needed, and none is used.** Ocean and invalid cells
already carry the same sentinel in the *real* data (the build scripts write
`raw_sentinel` wherever the source is NaN, in every year, not just the
padding). So copying record 2920 onto record 2919:

- at a land cell, writes real 2024-01-01 data — the intent;
- at an ocean cell, writes the sentinel over the sentinel — a no-op.

The masking is implicit in the data. This deliberately avoids introducing a
second, independent land/ocean determination that could disagree with the
pipeline's existing one.

Worst case the fix can produce is a first timestep that interpolates between
two identical values, which is exactly the constant it should be — zero
distortion, versus the sentinel contamination it replaces.

**Deliberately NOT changed**: `startyear_met` / `endyear_met_spinup` /
`endyear_met_trans`, the shared `yr .le. startyear_met` wraparound check, and
the historical 1980-2023 daymet files (they have no dummy year and never had
this problem). No Fortran was modified; this is a data-side fix only, so no
rebuild is required.

## 4. What was patched, and where

Build scripts were fixed so newly built files are correct from the start:

| Script | Repo |
|---|---|
| `future_climate/convertTESSFA2bypass/build_cpl_bypass_tessfa2.py` | ELM_Futu_landuseInput |
| `scripts/build_future_forcing_0p5deg.py` | SEUS_halfdeg |
| `scripts/build_future_flds_0p5deg.py` | SEUS_halfdeg |

The 0.5° builders needed their own fix: they do **not** copy the dummy year
from the 4 km source, they synthesize it independently as pure sentinel, so
fixing the 4 km source alone would not have propagated.

Files that already existed were patched in place by
`future_climate/ops/patch_dummy_year_tail.py` (one record rewritten; a full
rebuild would have taken hours per file). Wrappers:

| Wrapper | Target |
|---|---|
| `ops/patch_dummy_year_tail_scenario.sbatch` | `/scratch/hpcl-cli185/zw5/future_clim/<ssp>/` (4 km test copy) |
| `ops/patch_worldshared_future_clim.sbatch` | `/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/<ssp>/` (4 km canonical) |
| `ops/patch_halfdeg_future_clim.sbatch` | `/projects/hpcl-cli185/proj-shared/zw5/SEUS_halfdeg/data/processed/cpl_bypass_0p5deg_future/<ssp>/` (0.5° production) |

4 scenarios × 7 variables at each location. Each patched file gets a JSON
record under
`future_climate/outputs/patch_records/<tag>_<scenario>_<basename>.patch_record.json`
holding sha256 before/after, cells changed, and the patch script's commit.
The original `future_forcing_<ssp>_<var>_build.json` build records are left
untouched — they remain an accurate account of how each file was *built*,
which patching does not change.

The patch is **idempotent** (re-running finds 0 cells to change) and
**reversible** (the pre-patch state of record 2919 was a known per-variable
constant, so it can be restored exactly).

### Completion status (2026-09-02)

All 84 files — 4 scenarios x 7 variables x 3 locations — are patched.

| scenario | /scratch 4 km | world-shared 4 km | 0.5° production | canonical audit |
|---|---|---|---|---|
| ssp119 | done | done | done | 78 PASS / 0 FAIL |
| ssp245 | done | done | done | 78 PASS / 0 FAIL |
| ssp370 | done | done | done | 78 PASS / 0 FAIL |
| ssp585 | done | done | done | 78 PASS / 0 FAIL |

Cells changed per file: 117,964 of 225,625 at 4 km (52.3%, matching the
known land fraction), 571 of 1,134 at 0.5° (the land-bearing coarse cells).
One /scratch file reports 0 — ssp119/TBOT, re-patched by the batch run after
an earlier single-file test, which is the idempotence guarantee working.

**Cross-check across locations**: every one of the 28 world-shared files has
a post-patch sha256 **identical** to its /scratch counterpart (0 mismatches).
Since the /scratch copies passed the full four-scenario audit independently,
this proves the canonical files are byte-identical to audited-good data —
complete coverage without re-reading 2.7 TB.

The 0.5° files additionally passed 11 runs of the independent oracle
verifiers (`verify_future_forcing_0p5deg.py` / `verify_future_flds_0p5deg.py`):
full 7-variable coverage on ssp245, plus TBOT and FLDS on the other three
scenarios. Those verifiers rebuild the mapping by brute force and compare
with exact rational arithmetic, so they are a stronger check than comparing
one copy against another.

**Cost, for planning**: ~16-18 minutes per 96 GB file on /projects NFS with
`--sha256`, i.e. ~2 hours per scenario, ~8 hours for all 28 canonical files.
0.5° took 32 seconds per scenario. The gap is row count (225,625 vs 1,134),
not file size — see the note on IOPS below.

## 5. How to verify

**Data-side**, per scenario:

```bash
# 4 km (canonical, or any copy via --base-dir)
sbatch --export=NONE --mem=96g -t 6:00:00 --dependency=singleton \
  jobs/audit_future_alignment.sbatch --scenario ssp119
# 0.5 deg
sbatch jobs/verify_future_forcing_0p5deg.sbatch --scenario ssp119 --var TBOT
sbatch jobs/verify_future_flds_0p5deg.sbatch  --scenario ssp119
```

The audits were updated alongside the fix — they previously asserted the
whole dummy year was sentinel, which correctly-patched files now fail. They
now check the two halves separately:

- **head** (records 0-2918): still bitwise sentinel at every cell/row;
- **tail** (record 2919): equals that row's real first record; ocean cells
  unchanged (still sentinel).

A useful self-check appears in the tail result: exactly **137 rows report
"self-masked"** — rows whose real data is itself all-sentinel across the
entire real range, so their tail legitimately stays sentinel. That count
matches the independently locked 137-row reference in
`configs/future_sentinel_rows_locked.yaml`.

**Model-side**, the decisive test: a 12-step cold-start probe with
`hist_nhtfrq=1` (per-timestep output). The pre-fix baseline is saved at
`SEUS_halfdeg/data/intermediate/dummy_tail_smoke/prepatch_baseline_ssp245_t0probe.json`
and shows the bug unmistakably — land-cell values over the first steps:

| step | TBOT min | PBOT min | interpolation weight on the dummy record |
|---|---|---|---|
| 1 | **323 K** (clamp) | **40000 Pa** (clamp) | 0.500 |
| 2 | **323 K** (clamp) | **40000 Pa** (clamp) | 0.333 |
| 3 | 288.9 K | 73032 Pa | 0.167 |
| 4 | **323 K** (clamp) | **40000 Pa** (clamp) | **1.000** |
| 5+ | 267.3 K | 89630 Pa | past the dummy record |

Step 4 is the clearest signature: with full weight on the dummy record, all
571 land cells held *identical* values, and QBOT read exactly 0.0010156
kg/kg — the decoded QBOT sentinel. The affected steps and their severity
track the reader's own interpolation weights exactly, which independently
confirmed the tindex analysis in §2.

**Result after the fix** (same case, same executable, same configuration —
the forcing data is the only thing that changed; job 505775 vs the
pre-patch 503713), saved as `postpatch_baseline_ssp245_t0probe.json`:

| step | TBOT before | TBOT after | PBOT before | PBOT after |
|---|---|---|---|---|
| 1 | 323 / 323 (flat, clamp) | 267.49 / 294.08 | 40000 (clamp) | 89638 |
| 2 | 323 / 323 (flat, clamp) | 267.49 / 294.08 | 40000 (clamp) | 89638 |
| 3 | 288.91 / 311.07 | 267.49 / 294.08 | 73032 | 89638 |
| 4 | 323 / 323 (flat, clamp) | 267.49 / 294.08 | 40000 (flat, clamp) | 89638 |
| 5-12 | normal | **bit-identical to before** | normal | **bit-identical to before** |

(min / max over the 571 land cells.)

Three things worth noting:

1. **Steps 5-12 are unchanged, exactly.** The fix touches one record and
   nothing downstream of it, and the run confirms that literally — every
   later step reproduces its pre-patch value.
2. **Steps 1-4 now all read the same value**, and that value equals what
   step 10 reads. That is precisely the designed behaviour, not a
   coincidence: steps 1-4 interpolate between records 2919 and 2920, which
   the patch made identical, so the interpolation returns record 2920's
   value at any weight. Step 10 happens to sit at `wt1 = 1.0` on that same
   record. The "worst case is interpolating between two identical values —
   zero distortion" argument from §3 is therefore confirmed numerically,
   not just asserted.
3. QBOT's step-4 sentinel fingerprint (0.0010156 at every cell) is gone,
   replaced by normal spatial variation (0.001781 / 0.0075818).

## 6. Existing runs that were NOT rerun

`20260901_seus_halfdeg_future_ssp119` (job 504890) read the unpatched 0.5°
forcing and has **not** been rerun. The distortion is confined to roughly the
first 4 timesteps (~2 hours of model time) of a 77-year run, and its January
2024 monthly means were checked directly: TBOT max 306.96 K (vs 304.46 K in
2025-01 and 305.87 K in 2026-01 — ordinary interannual spread, 16 K clear of
the clamp) and PBOT min 89758 Pa (50 kPa clear of its clamp). The effect is
not measurable at monthly-mean resolution.

The fix matters for anything looking at sub-daily output near a run's start,
and for scenarios launched from here on — not retroactively for that run's
published monthly output.

The `/scratch/hpcl-cli185/zw5/future_clim/` copy has itself been patched, so
it is **no longer a pristine pre-fix backup**. Do not treat it as one.

## 7. Why this cost so much wall time

Worth recording, because the intuition is backwards: **modifying 441 KB took
longer than writing the whole 96 GB file would have.**

Record 2919 lives in every one of the 225,625 rows, and `DTIME` is the
fastest-varying dimension, so those 2-byte values sit 455,520 bytes apart.
Touching them means ~225,625 scattered accesses — an IOPS-bound workload —
whereas the original build wrote the same file in ~20 large contiguous
blocks at full bandwidth. That is also why 0.5° finished in 32 seconds per
scenario: 1,134 rows, not 1,134-times-smaller files.

Two measured consequences:

- **Copying the already-patched file instead is worse, not better.**
  /scratch → /projects ran at 27 MB/s, so 7 files (672 GB) would take ~6.9 h
  versus ~2 h to patch them in place — and a half-finished copy leaves a
  corrupt canonical file, where an interrupted patch is simply re-runnable.
- **`--sha256` partly pays for itself.** It doubles a full-file read, but
  that sequential pass warms the page cache, so the subsequent scattered
  column work and any follow-on audit run far faster (the sha256-warmed
  canonical audits took ~3 minutes; the cold /scratch ones took ~45).
