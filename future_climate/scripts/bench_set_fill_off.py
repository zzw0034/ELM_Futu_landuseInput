#!/usr/bin/env python
"""Test whether Dataset.set_fill_off() is what actually disables pre-fill for
classic (NETCDF3_64BIT_OFFSET) files, at production scale.

Background: both builders declare their ~96GiB packed variable with
createVariable(..., fill_value=False), intending to skip nc_enddef()'s
pre-fill of the full declared extent. But fill_value=False maps to
nc_def_var_fill(), a netCDF-4 API -- in classic netCDF-3 the fill mode is a
DATASET-level setting (nc_set_fill(), exposed here as Dataset.set_fill_off()),
which neither builder ever calls. Observed on jobs 465246/465247
(2026-08-18): real disk blocks being allocated across the entire 96GiB at
~21MB/s during the "create final file" step -- i.e. zeros genuinely being
written, which is exactly what fill_value=False was supposed to prevent.

This times the first write into a full-size (n, DTIME) variable both ways.
If set_fill_off() is the real switch, variant B should finish in seconds
while variant A grinds through ~96GiB.

Writes to a dedicated benchmark dir; safe to delete afterwards. Runs one
variant at a time and reports incrementally, so a walltime kill still
leaves usable numbers in the log.
"""
import shutil
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np

NCELL = 225625
STEPS_PER_YEAR = 2920
N_YEARS = 78                      # dummy + 77 real, same as production
TOTAL_STEPS = STEPS_PER_YEAR * N_YEARS
NOMINAL_GIB = NCELL * TOTAL_STEPS * 2 / 2**30

BENCH_DIR = Path("/scratch/hpcl-cli185/zw5/future_clim/_benchmark_fill")
if BENCH_DIR.exists():
    shutil.rmtree(BENCH_DIR)
BENCH_DIR.mkdir(parents=True, exist_ok=True)


def run_variant(label, use_set_fill_off):
    path = BENCH_DIR / f"{label}.nc"
    print(f"\n=== {label}: set_fill_off()={'YES' if use_set_fill_off else 'NO'} "
          f"(declaring {NOMINAL_GIB:.1f} GiB) ===", flush=True)
    t0 = time.time()
    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    if use_set_fill_off:
        ds.set_fill_off()
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", TOTAL_STEPS)
    # Same declaration order as the fixed builders: small vars first, then
    # the big one, so this isolates fill behavior rather than layout order.
    v_small = ds.createVariable("LONGXY", "f4", ("n",), fill_value=False)
    v_big = ds.createVariable("VAR", "i2", ("n", "DTIME"), fill_value=False)
    v_big.set_auto_scale(False)
    t_define = time.time()
    print(f"  define mode done: {t_define - t0:.1f}s", flush=True)

    # First write -- this is what triggers nc_enddef() and, if pre-fill is
    # still on, writes across the whole declared extent.
    v_small[:] = np.arange(NCELL, dtype=np.float32)
    t_first = time.time()
    print(f"  FIRST WRITE (enddef) done: {t_first - t_define:.1f}s", flush=True)

    # One real chunk of packed data, to confirm normal writes still work.
    rows = 20000
    v_big[0:rows, :] = np.full((rows, TOTAL_STEPS), 123, dtype=np.int16)
    t_chunk = time.time()
    print(f"  one {rows}-row chunk written: {t_chunk - t_first:.1f}s", flush=True)

    ds.close()
    t_close = time.time()
    print(f"  close: {t_close - t_chunk:.1f}s", flush=True)
    real_mib = sum(f.stat().st_blocks for f in [path]) * 512 / 2**20
    print(f"  TOTAL: {t_close - t0:.1f}s | real disk usage: {real_mib:.0f} MiB "
          f"(apparent {path.stat().st_size / 2**30:.1f} GiB)", flush=True)
    return t_close - t0


print(f"Production-scale fill-mode test: n={NCELL}, DTIME={TOTAL_STEPS} "
      f"({NOMINAL_GIB:.1f} GiB variable)", flush=True)

t_with = run_variant("B_set_fill_off", True)
t_without = run_variant("A_default", False)

print("\n=== SUMMARY ===", flush=True)
print(f"  with set_fill_off():    {t_with:.1f}s", flush=True)
print(f"  without (current code): {t_without:.1f}s", flush=True)
if t_with > 0:
    print(f"  speedup: {t_without / t_with:.1f}x", flush=True)
