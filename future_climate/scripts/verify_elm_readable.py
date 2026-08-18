#!/usr/bin/env python
"""Structural check: does a new future-forcing file match the shape the
patched Fortran cpl_bypass reader (lnd_import_export.F90, metsource==6,
metdata_type='era5-daymet-fut') actually needs to read it?

The reader only touches: format kind, dims n/DTIME, variables
DTIME/LONGXY/LATIXY/<var>, and <var>'s add_offset/scale_factor. It does not
care about extra global attributes, so this compares STRUCTURE against the
historical file (which has none) rather than requiring an exact match.

Usage: verify_elm_readable.py <new_file.nc> <var> [<historical_file.nc>]
If historical_file is omitted, defaults to the matching
Daymet_ERA5_TESSFA.4km_<var>_1980-2023_z01.nc.
"""
import subprocess
import sys
from pathlib import Path

import netCDF4 as nc
import numpy as np

NCDUMP = "/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/ncdump"
HIST_DIR = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
               "Daymet_ERA5_TESSFA2/cpl_bypass_full")

new_path = Path(sys.argv[1])
var = sys.argv[2]
hist_path = Path(sys.argv[3]) if len(sys.argv) > 3 else \
    HIST_DIR / f"Daymet_ERA5_TESSFA.4km_{var}_1980-2023_z01.nc"

failures = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""),
          flush=True)
    if not ok:
        failures.append(label)


print(f"new:        {new_path}", flush=True)
print(f"historical: {hist_path}\n", flush=True)

# 1. format kind must be exactly what the Fortran reader's nf90_open expects
kind_new = subprocess.run([NCDUMP, "-k", str(new_path)], capture_output=True, text=True).stdout.strip()
kind_hist = subprocess.run([NCDUMP, "-k", str(hist_path)], capture_output=True, text=True).stdout.strip()
check("format kind is '64-bit offset'", kind_new == "64-bit offset", kind_new)
check("format kind matches historical file", kind_new == kind_hist,
      f"new={kind_new} hist={kind_hist}")

dsn = nc.Dataset(new_path)
dsh = nc.Dataset(hist_path)

# 2. dimension names and n must match exactly (DTIME length legitimately
# differs: 44 historical years vs 78 future years)
check("dim names are exactly {n, DTIME}", set(dsn.dimensions) == {"n", "DTIME"},
      sorted(dsn.dimensions))
check("n matches historical grid size", len(dsn.dimensions["n"]) == len(dsh.dimensions["n"]),
      f"new n={len(dsn.dimensions['n'])} hist n={len(dsh.dimensions['n'])}")
check("DTIME is a fixed (non-record) dimension", not dsn.dimensions["DTIME"].isunlimited())

# 3. required variables present with the reader's expected dims/dtype
required = {
    "DTIME": (("DTIME",), "float64"),
    "LONGXY": (("n",), "float32"),
    "LATIXY": (("n",), "float32"),
    var: (("n", "DTIME"), "int16"),
}
for vname, (dims, dtype) in required.items():
    present = vname in dsn.variables
    check(f"variable {vname} exists", present)
    if present:
        v = dsn.variables[vname]
        check(f"  {vname} dims == {dims}", v.dimensions == dims, v.dimensions)
        check(f"  {vname} dtype == {dtype}", str(v.dtype) == dtype, str(v.dtype))

# 4. the reader applies (raw - add_offset) is wrong -- it's
# physical = raw*scale_factor + add_offset -- both attrs must exist and be
# float, and must match what pack_month/read_month assumed when packing
v_new = dsn.variables[var]
has_off = hasattr(v_new, "add_offset")
has_scale = hasattr(v_new, "scale_factor")
check(f"{var} has add_offset", has_off, getattr(v_new, "add_offset", None))
check(f"{var} has scale_factor", has_scale, getattr(v_new, "scale_factor", None))
if var in dsh.variables and has_off and has_scale:
    v_hist = dsh.variables[var]
    same_off = np.isclose(v_new.add_offset, v_hist.add_offset, rtol=1e-5)
    same_scale = np.isclose(v_new.scale_factor, v_hist.scale_factor, rtol=1e-5)
    check(f"{var} add_offset matches historical convention", bool(same_off),
          f"new={v_new.add_offset} hist={v_hist.add_offset}")
    check(f"{var} scale_factor matches historical convention", bool(same_scale),
          f"new={v_new.scale_factor} hist={v_hist.scale_factor}")

# 5. DTIME units anchor and length must be internally consistent with the
# dummy-year design (startyear_met=2023 in the Fortran patch)
units = getattr(dsn.variables["DTIME"], "units", "")
check("DTIME units anchored at 2023-01-01 (dummy-year design)",
      "2023-01-01" in units, units)
expected_steps = 2920 * 78  # dummy + 77 real years, 3-hourly
check("DTIME length == 78 years x 2920 steps (dummy + 2024-2100)",
      len(dsn.dimensions["DTIME"]) == expected_steps,
      f"got {len(dsn.dimensions['DTIME'])}, expected {expected_steps}")

# 6. LONGXY/LATIXY must be non-degenerate and inside the TESSFA2 domain
lon = dsn.variables["LONGXY"][:]
lat = dsn.variables["LATIXY"][:]
check("LONGXY within TESSFA2 domain [-100,-74]", bool(lon.min() >= -100 and lon.max() <= -74),
      f"[{lon.min():.2f}, {lon.max():.2f}]")
check("LATIXY within TESSFA2 domain [25,40]", bool(lat.min() >= 25 and lat.max() <= 40),
      f"[{lat.min():.2f}, {lat.max():.2f}]")
check("LONGXY/LATIXY match historical grid (same zone_mappings order)",
      bool(np.allclose(lon, dsh.variables["LONGXY"][:], atol=1e-3)
           and np.allclose(lat, dsh.variables["LATIXY"][:], atol=1e-3)))

dsn.close()
dsh.close()

print("\n=== VERDICT ===", flush=True)
if failures:
    print(f"FAIL -- {len(failures)} check(s) failed:", flush=True)
    for f in failures:
        print(f"  - {f}", flush=True)
    raise SystemExit(1)
print("PASS -- structurally readable by the patched cpl_bypass reader", flush=True)
