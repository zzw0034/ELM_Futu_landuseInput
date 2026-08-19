#!/usr/bin/env python
"""Exact test of the proposed header-rewrite fix, at production scale.

Established so far (jobs 465258/465260, 2026-08-18):
  - Pre-fill is NOT the problem: set_fill_off() changed nothing (1.0x) and
    nc_enddef() itself is instantaneous with fill_value=False.
  - Setting attributes AFTER declaring the ~96GiB variable IS the problem.
    netCDF4-python's own setncatts docstring says nc_redef/nc_enddef is
    called between each individually-set attribute on a NETCDF3 file; in
    classic format the header lives at the front, so a header that grows
    shifts everything after it -- the whole ~96GiB variable region.
    Measured: a variant doing nothing but two setncatts() calls rewrote
    ~40GiB and was still climbing after 11 minutes, with zero data written.
  - Both builders set 8-9 attributes after declaring that variable.

Proposed fix: set every global attribute (and the small variables' own
attributes) BEFORE declaring the big variable, while the file is still a
few MB, then declare the big variable last and batch its two attributes
into a single setncatts().

OPEN QUESTION this script answers exactly: add_offset/scale_factor can only
be set after the big variable exists, so does that one remaining setncatts()
still force a full ~96GiB rewrite? Variant E times that single step in
isolation. Compare against the ~15s floor measured for a file with no
attributes at all.

Also runs variant F (identical, but the big variable's two attributes set
one at a time) to size the batching benefit separately from the ordering
benefit.
"""
import shutil
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np

NCELL = 225625
STEPS_PER_YEAR = 2920
N_YEARS = 78
TOTAL_STEPS = STEPS_PER_YEAR * N_YEARS
NOMINAL_GIB = NCELL * TOTAL_STEPS * 2 / 2**30

BENCH_DIR = Path("/scratch/hpcl-cli185/zw5/future_clim/_benchmark_attr_order")
if BENCH_DIR.exists():
    shutil.rmtree(BENCH_DIR)
BENCH_DIR.mkdir(parents=True, exist_ok=True)

GLOBAL_ATTRS = {
    "title": "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing",
    "source": "CanESM5 ssp245 r1i1p1f1, DBCCA bias-corrected/downscaled against Daymet",
    "build_method": "Approach B: staged per-year files, then row-major merge",
    "comment": "Record 1 is an UNUSED PLACEHOLDER YEAR, not real data. " * 8,
    "calendar_note": "Source data use a standard Gregorian calendar; Feb 29 removed. " * 3,
    "ocean_sentinel_note": "Raw packed value used for ocean/invalid gridcells. " * 3,
}
BIG_ATTRS = {"add_offset": np.float32(0.05), "scale_factor": np.float32(3.4e-06)}


def mib(path):
    return path.stat().st_blocks * 512 / 2**20


def run(label, batch_big_attrs):
    path = BENCH_DIR / f"{label}.nc"
    how = "batched setncatts()" if batch_big_attrs else "one at a time"
    print(f"\n=== {label}: global attrs BEFORE big var; big-var attrs {how} ===", flush=True)
    t0 = time.time()

    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", TOTAL_STEPS)

    # Small variables and every attribute we can set now, while the file is
    # only a few MB -- any header rewrite here is cheap.
    v_dtime = ds.createVariable("DTIME", "f8", ("DTIME",), fill_value=False)
    v_lon = ds.createVariable("LONGXY", "f4", ("n",), fill_value=False)
    v_lat = ds.createVariable("LATIXY", "f4", ("n",), fill_value=False)
    v_dtime.setncatts({"long_name": "Day of Year", "units": "Days since 2023-01-01 00:00"})
    ds.setncatts(GLOBAL_ATTRS)
    t_header = time.time()
    print(f"  small vars + ALL global attrs done: {t_header - t0:.1f}s "
          f"(file {mib(path):.0f} MiB)", flush=True)

    # Big variable declared LAST, so nothing sits after it in the file.
    v_big = ds.createVariable("VAR", "i2", ("n", "DTIME"), fill_value=False)
    v_big.set_auto_scale(False)
    t_big = time.time()
    print(f"  big variable declared: {t_big - t_header:.1f}s "
          f"(file {mib(path):.0f} MiB)", flush=True)

    # THE MEASUREMENT THAT MATTERS: these two attributes cannot be set any
    # earlier -- the variable has to exist first. Does this still rewrite
    # the whole ~96GiB?
    if batch_big_attrs:
        v_big.setncatts(BIG_ATTRS)
    else:
        for k, v in BIG_ATTRS.items():
            setattr(v_big, k, v)
    t_big_attrs = time.time()
    print(f"  >>> big-var attrs ({how}): {t_big_attrs - t_big:.1f}s "
          f"(file {mib(path):.0f} MiB) <<<", flush=True)

    v_lon[:] = np.arange(NCELL, dtype=np.float32)
    v_lat[:] = np.arange(NCELL, dtype=np.float32)
    v_dtime[:] = np.arange(TOTAL_STEPS, dtype=np.float64)
    t_small_data = time.time()
    print(f"  small-var data written: {t_small_data - t_big_attrs:.1f}s", flush=True)

    rows = 20000
    v_big[0:rows, :] = np.full((rows, TOTAL_STEPS), 123, dtype=np.int16)
    t_chunk = time.time()
    print(f"  one {rows}-row chunk written: {t_chunk - t_small_data:.1f}s", flush=True)

    ds.close()
    total = time.time() - t0
    print(f"  TOTAL: {total:.1f}s (file {mib(path):.0f} MiB)", flush=True)

    # Verify the attributes actually survived -- a fast result is worthless
    # if the header didn't end up correct.
    chk = nc.Dataset(path)
    ok = (abs(chk.variables["VAR"].add_offset - 0.05) < 1e-9
          and chk.title == GLOBAL_ATTRS["title"]
          and chk.variables["DTIME"].long_name == "Day of Year")
    print(f"  attributes verified present and correct: {ok}", flush=True)
    chk.close()
    return t_big_attrs - t_big, total


print(f"Attribute-ordering test: n={NCELL}, DTIME={TOTAL_STEPS} "
      f"({NOMINAL_GIB:.1f} GiB variable)", flush=True)
print("Reference floor (no attributes at all, job 465260): ~15s total\n", flush=True)

e_attrs, e_total = run("E_ordered_batched", True)
f_attrs, f_total = run("F_ordered_single", False)

print("\n=== RESULT ===", flush=True)
print(f"  E  global-attrs-first + big-var attrs batched: "
      f"big-var attr step {e_attrs:.1f}s, total {e_total:.1f}s", flush=True)
print(f"  F  global-attrs-first + big-var attrs one-by-one: "
      f"big-var attr step {f_attrs:.1f}s, total {f_total:.1f}s", flush=True)
print("\nIf E's big-var attr step is seconds, the fix removes the rewrite entirely.", flush=True)
print("If it is minutes, one ~96GiB rewrite remains -- still ~9x better than", flush=True)
print("the current 8-9 rewrites, but worth knowing before changing production.", flush=True)
