#!/usr/bin/env python
"""Real-data prototype of Cursor's Approach B (split into small per-year
files, then merge ROW-MAJOR into the final file) vs the current production
Approach A (year-batched strided write), using REAL ssp370 source data for
a small number of years -- before touching the full 78-year/28-combo
pipeline.

Reuses read_month/pack_month/process_month/load_grid_order/VARS/
OCEAN_SENTINEL_RAW from the production script unchanged, so packing
semantics are guaranteed identical to production; only the *write
strategy* differs between A and B. Also verifies A and B produce
byte-identical packed output on a sample of rows -- speed alone isn't
enough to adopt this.

Writes only under a dedicated test directory on /scratch -- does not
touch the real ssp370 production output path.
"""
import importlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import netCDF4 as nc
import numpy as np

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/scripts")
mod = importlib.import_module("10_build_future_cpl_bypass")

NCELL = mod.NCELL
STEPS_PER_YEAR = mod.STEPS_PER_YEAR
VARS = mod.VARS
OCEAN_SENTINEL_RAW = mod.OCEAN_SENTINEL_RAW
add_offset_scale = mod.add_offset_scale
process_month = mod.process_month

SCENARIO = "ssp370"
VAR = "PRECTmms"
TEST_Y0 = 2024
TEST_YEARS = 3
TEST_Y1 = TEST_Y0 + TEST_YEARS - 1
NWORKERS = 16

TEST_DIR = Path("/scratch/hpcl-cli185/zw5/future_clim/_test_approachB")
TEST_DIR.mkdir(parents=True, exist_ok=True)

_, _, _, (lo, hi) = VARS[VAR]
add_off, scale = add_offset_scale(lo, hi)
raw_sentinel = OCEAN_SENTINEL_RAW[VAR]


def log(msg, t0):
    print(f"[{time.time() - t0:7.1f}s] {msg}", flush=True)


def read_all_months():
    tasks = [(y, m) for y in range(TEST_Y0, TEST_Y1 + 1) for m in range(1, 13)]
    results = {}
    with ProcessPoolExecutor(max_workers=NWORKERS) as pool:
        futs = [pool.submit(process_month, SCENARIO, VAR, y, m, add_off, scale, raw_sentinel)
                for y, m in tasks]
        for fut in futs:
            y, m, start, packed = fut.result()
            results[(y, m)] = packed
    return results


def create_big_file(path, total_steps):
    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", total_steps)
    v = ds.createVariable(VAR, "i2", ("n", "DTIME"), fill_value=False)
    v.add_offset = np.float32(add_off)
    v.scale_factor = np.float32(scale)
    v.set_auto_scale(False)
    return ds, v


def year_block(month_data, y):
    """(2920, NCELL) int16 for one year, months concatenated in order."""
    return np.concatenate([month_data[(y, m)] for m in range(1, 13)], axis=0)


def main():
    print(f"Real-data test: {SCENARIO}/{VAR}, years {TEST_Y0}-{TEST_Y1} "
          f"({TEST_YEARS} years, {TEST_YEARS * 12} months), {NWORKERS} workers", flush=True)
    t0 = time.time()
    month_data = read_all_months()
    t_read = time.time() - t0
    print(f"Read+pack (shared cost for both approaches): {t_read:.1f}s\n", flush=True)

    total_steps = TEST_YEARS * STEPS_PER_YEAR
    years = list(range(TEST_Y0, TEST_Y1 + 1))

    # ---- Approach A: current production method ----
    print("=" * 60, flush=True)
    print("APPROACH A (current production: year-batched strided write)", flush=True)
    print("=" * 60, flush=True)
    path_a = TEST_DIR / f"A_{SCENARIO}_{VAR}.nc"
    if path_a.exists():
        path_a.unlink()
    t0 = time.time()
    ds_a, v_a = create_big_file(path_a, total_steps)
    log("file created", t0)
    for i, y in enumerate(years):
        block = year_block(month_data, y)
        start = i * STEPS_PER_YEAR
        v_a[:, start:start + block.shape[0]] = block.T
        log(f"year {y} written", t0)
    ds_a.close()
    t_a = time.time() - t0
    print(f"APPROACH A TOTAL: {t_a:.1f}s\n", flush=True)

    # ---- Approach B: split into small per-year files, then row-major merge ----
    print("=" * 60, flush=True)
    print("APPROACH B (split + row-major merge)", flush=True)
    print("=" * 60, flush=True)
    path_b_years = [TEST_DIR / f"B_{SCENARIO}_{VAR}_y{y}.nc" for y in years]
    path_b_final = TEST_DIR / f"B_{SCENARIO}_{VAR}_final.nc"
    for p in path_b_years + [path_b_final]:
        if p.exists():
            p.unlink()

    t0 = time.time()
    for y, p in zip(years, path_b_years):
        block = year_block(month_data, y)
        ds_y = nc.Dataset(p, "w", format="NETCDF3_64BIT_OFFSET")
        ds_y.createDimension("n", NCELL)
        ds_y.createDimension("DTIME", STEPS_PER_YEAR)
        v_y = ds_y.createVariable(VAR, "i2", ("n", "DTIME"), fill_value=False)
        v_y[:, :] = block.T
        ds_y.close()
        log(f"staged year {y}", t0)
    t_stage = time.time() - t0
    print(f"staging done: {t_stage:.1f}s", flush=True)

    ds_final, v_final = create_big_file(path_b_final, total_steps)
    log("final file created", t0)

    readers = [nc.Dataset(p) for p in path_b_years]
    for r in readers:
        r.set_auto_maskandscale(False)

    ROW_CHUNK = 20000
    n_chunks = (NCELL + ROW_CHUNK - 1) // ROW_CHUNK
    for c in range(n_chunks):
        r0 = c * ROW_CHUNK
        r1 = min(r0 + ROW_CHUNK, NCELL)
        chunk = np.concatenate([readers[i].variables[VAR][r0:r1, :] for i in range(TEST_YEARS)], axis=1)
        v_final[r0:r1, :] = chunk
        log(f"merge chunk {c + 1}/{n_chunks}", t0)
    for r in readers:
        r.close()
    ds_final.close()
    t_b = time.time() - t0
    print(f"APPROACH B TOTAL (stage+merge): {t_b:.1f}s\n", flush=True)

    # ---- Correctness check: A and B must produce identical packed data ----
    print("=" * 60, flush=True)
    print("CORRECTNESS CHECK: A vs B", flush=True)
    print("=" * 60, flush=True)
    dsa = nc.Dataset(path_a); dsa.set_auto_maskandscale(False)
    dsb = nc.Dataset(path_b_final); dsb.set_auto_maskandscale(False)
    N_SAMPLE = np.linspace(0, NCELL - 1, 1000).astype(int)
    va = dsa.variables[VAR][N_SAMPLE, :]
    vb = dsb.variables[VAR][N_SAMPLE, :]
    identical = np.array_equal(va, vb)
    print(f"A vs B identical on {len(N_SAMPLE)} sampled rows x {total_steps} steps: {identical}", flush=True)
    if not identical:
        n_diff = int(np.sum(va != vb))
        print(f"  MISMATCH: {n_diff} / {va.size} differing values -- DO NOT ADOPT until root-caused", flush=True)
    dsa.close()
    dsb.close()

    print("\n=== SUMMARY ===", flush=True)
    print(f"Read+pack (shared): {t_read:.1f}s", flush=True)
    print(f"Approach A write:   {t_a:.1f}s", flush=True)
    print(f"Approach B write:   {t_b:.1f}s  (stage={t_stage:.1f}s + merge={t_b - t_stage:.1f}s)", flush=True)
    print(f"Speedup (write only): {t_a / t_b:.2f}x", flush=True)
    print(f"Data correctness: {'PASS' if identical else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
