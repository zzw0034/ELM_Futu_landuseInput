#!/usr/bin/env python
"""Small-scale (3-year) benchmark comparing two write strategies for the
future cpl_bypass files, BEFORE touching the production 78-year pipeline:

  A. current production method: create the full-size target file once,
     then write year-batches (each touching all 225,625 rows, small
     DTIME slice) -- this is what 10_build_future_cpl_bypass.py does.

  B. Cursor's split-then-merge proposal, merge done ROW-MAJOR: write
     N_TEST_YEARS small per-year files first, then reassemble by reading
     each row's full multi-year series (contiguous within each small
     file) and writing it as ONE contiguous block per row-chunk into the
     final file.

Also isolates the file-creation ("enddef") cost by itself, and does it
at two different total sizes (1 year vs N_TEST_YEARS years) with the same
row count (225,625) to see whether that cost scales with total bytes or
is dominated purely by touching every row once, regardless of size.

Runs entirely in a dedicated benchmark directory -- does not touch any
production output path. Safe to delete afterward.
"""
import shutil
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np

NLON, NLAT = 625, 361
NCELL = NLON * NLAT
STEPS_PER_YEAR = 2920
N_TEST_YEARS = 3
TOTAL_STEPS = STEPS_PER_YEAR * N_TEST_YEARS

BENCH_DIR = Path("/scratch/hpcl-cli185/zw5/future_clim/_benchmark")
if BENCH_DIR.exists():
    shutil.rmtree(BENCH_DIR)
BENCH_DIR.mkdir(parents=True, exist_ok=True)


def log(msg, t0):
    print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


def make_year_data(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(-32768, 32767, size=(NCELL, STEPS_PER_YEAR), dtype=np.int16)


def create_big_file(path, total_steps):
    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", total_steps)
    v = ds.createVariable("VAR", "i2", ("n", "DTIME"), fill_value=False)
    return ds, v


print("=" * 70, flush=True)
print("DIAGNOSTIC: does file-creation (enddef) cost scale with total bytes,", flush=True)
print("or is it dominated by touching all 225,625 rows regardless of size?", flush=True)
print("=" * 70, flush=True)

# ---- Diagnostic 1: create+first-touch a 1-year file ----
t0 = time.time()
p_diag1 = BENCH_DIR / "diag_1year.nc"
ds, v = create_big_file(p_diag1, STEPS_PER_YEAR)
t_create = time.time()
log(f"DIAG[1yr] file created (enddef done): {t_create - t0:.1f}s", t0)
v[:, :] = make_year_data(999)
t_write = time.time()
log(f"DIAG[1yr] first full write done: {t_write - t_create:.1f}s (create+write total: {t_write - t0:.1f}s)", t0)
ds.close()
diag1_create_s = t_create - t0
diag1_total_s = t_write - t0

# ---- Diagnostic 2: create+first-touch a N_TEST_YEARS-year file (same row count, more bytes) ----
t0 = time.time()
p_diag2 = BENCH_DIR / "diag_Nyear.nc"
ds, v = create_big_file(p_diag2, TOTAL_STEPS)
t_create = time.time()
log(f"DIAG[{N_TEST_YEARS}yr] file created (enddef done): {t_create - t0:.1f}s", t0)
v[:, 0:STEPS_PER_YEAR] = make_year_data(998)
t_write = time.time()
log(f"DIAG[{N_TEST_YEARS}yr] first year-slice write done: {t_write - t_create:.1f}s (create+write total: {t_write - t0:.1f}s)", t0)
ds.close()
diag2_create_s = t_create - t0
diag2_total_s = t_write - t0

print(flush=True)
print(f"SUMMARY diag: 1yr file create={diag1_create_s:.1f}s vs {N_TEST_YEARS}yr file create={diag2_create_s:.1f}s", flush=True)
print(f"  -> if these are close: cost is per-row-touch, size-independent (bad news for approach B)", flush=True)
print(f"  -> if {N_TEST_YEARS}yr is ~{N_TEST_YEARS}x the 1yr cost: cost scales with bytes (good news for approach B)", flush=True)
print(flush=True)

# ---- Approach A: current production method ----
print("=" * 70, flush=True)
print("APPROACH A: current method (year-batched writes into one fresh big file)", flush=True)
print("=" * 70, flush=True)
path_a = BENCH_DIR / "approach_A.nc"
t0 = time.time()
ds_a, v_a = create_big_file(path_a, TOTAL_STEPS)
log("file created (enddef done)", t0)
year_data = [make_year_data(i) for i in range(N_TEST_YEARS)]
log("synthetic year data generated in memory", t0)
for y in range(N_TEST_YEARS):
    start = y * STEPS_PER_YEAR
    v_a[:, start:start + STEPS_PER_YEAR] = year_data[y]
    log(f"year {y} written", t0)
ds_a.close()
t_a_total = time.time() - t0
log(f"APPROACH A TOTAL", t0)

# ---- Approach B: split into small per-year files, then row-major merge ----
print("=" * 70, flush=True)
print("APPROACH B: split into small per-year files, then ROW-MAJOR merge", flush=True)
print("=" * 70, flush=True)
path_b_years = [BENCH_DIR / f"approach_B_year{y}.nc" for y in range(N_TEST_YEARS)]
path_b_final = BENCH_DIR / "approach_B_final.nc"

t0 = time.time()
for y, p in enumerate(path_b_years):
    ds_y = nc.Dataset(p, "w", format="NETCDF3_64BIT_OFFSET")
    ds_y.createDimension("n", NCELL)
    ds_y.createDimension("DTIME", STEPS_PER_YEAR)
    v_y = ds_y.createVariable("VAR", "i2", ("n", "DTIME"), fill_value=False)
    v_y[:, :] = year_data[y]
    ds_y.close()
    log(f"staged small file for year {y}", t0)
t_stage = time.time()
log("STAGING done", t0)

ds_final, v_final = create_big_file(path_b_final, TOTAL_STEPS)
t_final_create = time.time()
log("final big file created (enddef done)", t0)

readers = [nc.Dataset(p) for p in path_b_years]
for r in readers:
    r.set_auto_maskandscale(False)

ROW_CHUNK = 20000
n_chunks = (NCELL + ROW_CHUNK - 1) // ROW_CHUNK
for c in range(n_chunks):
    r0 = c * ROW_CHUNK
    r1 = min(r0 + ROW_CHUNK, NCELL)
    chunk = np.concatenate(
        [readers[y].variables["VAR"][r0:r1, :] for y in range(N_TEST_YEARS)],
        axis=1,
    )
    v_final[r0:r1, :] = chunk
    log(f"merge chunk {c + 1}/{n_chunks} (rows {r0}:{r1}) written", t0)
for r in readers:
    r.close()
ds_final.close()
t_b_total = time.time() - t0
merge_only_s = time.time() - t_final_create
log("APPROACH B TOTAL (stage+create+merge)", t0)

print(flush=True)
print("=" * 70, flush=True)
print("FINAL SUMMARY", flush=True)
print("=" * 70, flush=True)
print(f"Diagnostic: 1-year file create(enddef)  = {diag1_create_s:.1f}s", flush=True)
print(f"Diagnostic: {N_TEST_YEARS}-year file create(enddef) = {diag2_create_s:.1f}s", flush=True)
print(f"Approach A (current, {N_TEST_YEARS}yr): {t_a_total:.1f}s total", flush=True)
print(f"Approach B (split+row-major merge, {N_TEST_YEARS}yr): {t_b_total:.1f}s total "
      f"(staging={t_stage - (t0):.1f}s is wrong ref, see per-line log; "
      f"merge-only={merge_only_s:.1f}s)", flush=True)
print(flush=True)
print("Extrapolation note: production is 78 years (26x this test's 3 years).", flush=True)
print("If per-row-touch cost dominates (diag1 ~= diag2), approach B pays that", flush=True)
print(f"cost {N_TEST_YEARS + 1} times (once per small file + once for final file) instead of", flush=True)
print("1 time -- would make things WORSE, not better, at full scale.", flush=True)
