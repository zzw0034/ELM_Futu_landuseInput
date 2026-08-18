#!/usr/bin/env python
"""Test building the file header with ncgen instead of netCDF4-python, to
eliminate the last ~96GiB header rewrite.

Where this sits in the investigation (all 2026-08-18):
  - Pre-fill ruled out (job 465258): set_fill_off() changed nothing, and
    nc_enddef() with fill_value=False is instantaneous.
  - Cause confirmed (job 465260): setting attributes AFTER declaring the
    ~96GiB variable rewrites the whole file, because classic netCDF keeps
    its header at the front and netCDF4-python issues nc_redef/nc_enddef
    per attribute on NETCDF3 files (its own setncatts docstring says so).
  - Ordering fix measured (job 465262): moving every global attribute ahead
    of the big variable's declaration is free (0.0s, file stays 0 MiB), but
    add_offset/scale_factor cannot be set until the variable exists, and
    that single setncatts() still forces one full rewrite (~44MB/s, ~37min).
    So the ordering fix alone gets 8-9 rewrites down to 1, not 0.

ncgen writes the entire header -- dimensions, variables, and every
attribute -- in a single define session and one nc_enddef(), the same way
Dan's Fortran makezones_reanalysis.f90 does, so no rewrite can occur. This
script generates the exact header our builders produce, times ncgen -x
(no-fill), then opens the result with netCDF4-python in append mode and
writes data. Writing data never touches the header, so the rewrite should
not reappear.

Verifies format kind, attribute values, and that packed data round-trips
byte-identically -- a fast header is worthless if the file is wrong.
"""
import shutil
import subprocess
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np

NCELL = 225625
STEPS_PER_YEAR = 2920
N_YEARS = 78
TOTAL_STEPS = STEPS_PER_YEAR * N_YEARS
NOMINAL_GIB = NCELL * TOTAL_STEPS * 2 / 2**30
VAR = "QBOT"
ADD_OFFSET = np.float32(0.05)
SCALE_FACTOR = np.float32(3.3569335937500004e-06)

NCGEN = "/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/ncgen"
NCDUMP = "/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/ncdump"

BENCH_DIR = Path("/scratch/hpcl-cli185/zw5/future_clim/_benchmark_ncgen")
if BENCH_DIR.exists():
    shutil.rmtree(BENCH_DIR)
BENCH_DIR.mkdir(parents=True, exist_ok=True)

GLOBAL_ATTRS = {
    "title": "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing",
    "source": "CanESM5 ssp245 r1i1p1f1, DBCCA bias-corrected/downscaled against Daymet, "
              "TESSFA2 (SEUS) 4km grid",
    "build_method": "Approach B: staged per-year files, then row-major merge; header via ncgen",
    "comment": "Record 1 (DTIME index 0-2919, nominal year 2023) is an UNUSED PLACEHOLDER "
               "YEAR, not real data. Real forcing begins at DTIME index 2920.",
    "calendar_note": "Source CanESM5-DBCCA-TESSFA2 data use a standard (Gregorian, leap-year) "
                     "calendar; Feb 29 was removed from every leap year to match CALENDAR=NO_LEAP.",
    "ocean_sentinel_note": "Raw packed value used for ocean/invalid gridcells, taken unchanged "
                           "from the historical file so decoded sentinel behavior is identical.",
}


def cdl_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_cdl(dataset_name):
    lines = [f"netcdf {dataset_name} {{", "dimensions:",
             f"\tn = {NCELL} ;", f"\tDTIME = {TOTAL_STEPS} ;", "variables:",
             "\tdouble DTIME(DTIME) ;",
             '\t\tDTIME:long_name = "Day of Year" ;',
             '\t\tDTIME:units = "Days since 2023-01-01 00:00" ;',
             "\tfloat LONGXY(n) ;", "\tfloat LATIXY(n) ;",
             f"\tshort {VAR}(n, DTIME) ;",
             f"\t\t{VAR}:add_offset = {float(ADD_OFFSET)!r}f ;",
             f"\t\t{VAR}:scale_factor = {float(SCALE_FACTOR)!r}f ;",
             "", "// global attributes:"]
    for k, v in GLOBAL_ATTRS.items():
        lines.append(f'\t\t:{k} = "{cdl_escape(v)}" ;')
    lines.append("\t\t:ocean_sentinel_raw = -14592s ;")
    lines.append("}")
    return "\n".join(lines) + "\n"


print(f"ncgen header test: n={NCELL}, DTIME={TOTAL_STEPS} ({NOMINAL_GIB:.1f} GiB variable)",
      flush=True)
print("Reference: netCDF4-python ordering fix leaves one ~37min rewrite (job 465262)\n",
      flush=True)

cdl_path = BENCH_DIR / "header.cdl"
out_path = BENCH_DIR / "ncgen_built.nc"
cdl_path.write_text(build_cdl("ncgen_built"))
print(f"CDL written ({cdl_path.stat().st_size} bytes)", flush=True)

# -6 = 64-bit offset (matches NETCDF3_64BIT_OFFSET), -x = no fill, -b = binary out
t0 = time.time()
res = subprocess.run([NCGEN, "-6", "-x", "-b", "-o", str(out_path), str(cdl_path)],
                     capture_output=True, text=True)
t_ncgen = time.time() - t0
if res.returncode != 0:
    print(f"ncgen FAILED (rc={res.returncode}):\n{res.stdout}\n{res.stderr}", flush=True)
    raise SystemExit(1)
real_mib = out_path.stat().st_blocks * 512 / 2**20
print(f">>> ncgen built the full header: {t_ncgen:.1f}s "
      f"(real disk {real_mib:.0f} MiB, apparent {out_path.stat().st_size / 2**30:.1f} GiB) <<<",
      flush=True)

kind = subprocess.run([NCDUMP, "-k", str(out_path)], capture_output=True, text=True).stdout.strip()
print(f"    format kind: {kind}", flush=True)

# Now write data through netCDF4-python in append mode -- this must not
# touch the header, so no rewrite should occur.
t0 = time.time()
ds = nc.Dataset(out_path, "a")
v_big = ds.variables[VAR]
v_big.set_auto_scale(False)
ds.variables["LONGXY"][:] = np.arange(NCELL, dtype=np.float32)
ds.variables["LATIXY"][:] = np.arange(NCELL, dtype=np.float32)
ds.variables["DTIME"][:] = np.arange(TOTAL_STEPS, dtype=np.float64)
t_small = time.time()
print(f"    small-var data written (append mode): {t_small - t0:.1f}s", flush=True)

rows = 20000
payload = np.random.default_rng(0).integers(-32000, 32000, size=(rows, TOTAL_STEPS), dtype=np.int16)
v_big[0:rows, :] = payload
ds.close()
t_chunk = time.time()
print(f"    one {rows}-row chunk written: {t_chunk - t_small:.1f}s", flush=True)
real_mib = out_path.stat().st_blocks * 512 / 2**20
print(f"    TOTAL data-write phase: {t_chunk - t0:.1f}s (real disk {real_mib:.0f} MiB)", flush=True)

# Correctness: header values and packed data must round-trip exactly.
chk = nc.Dataset(out_path)
chk.set_auto_maskandscale(False)
attrs_ok = (np.isclose(chk.variables[VAR].add_offset, ADD_OFFSET)
            and np.isclose(chk.variables[VAR].scale_factor, SCALE_FACTOR)
            and chk.title == GLOBAL_ATTRS["title"]
            and chk.ocean_sentinel_raw == -14592
            and chk.variables["DTIME"].long_name == "Day of Year")
sample_rows = np.linspace(0, rows - 1, 50).astype(int)
data_ok = np.array_equal(chk.variables[VAR][sample_rows, :], payload[sample_rows, :])
chk.close()

print(f"\n=== VERIFICATION ===", flush=True)
print(f"  format is 64-bit offset:        {kind == '64-bit offset'}", flush=True)
print(f"  all header attributes correct:  {attrs_ok}", flush=True)
print(f"  packed data round-trips exact:  {data_ok}", flush=True)
print(f"\n=== RESULT ===", flush=True)
print(f"  ncgen header build: {t_ncgen:.1f}s", flush=True)
print(f"  vs netCDF4-python's one remaining rewrite: ~37 min (job 465262)", flush=True)
