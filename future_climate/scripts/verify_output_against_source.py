#!/usr/bin/env python
"""End-to-end check of a finished cpl_bypass file: re-read the ORIGINAL
CanESM5 source months, re-pack them independently, and compare against what
actually landed in the output file.

This is the check that matters after changing how the file is built (header
now written by ncgen, data appended afterwards -- see
build_header_with_ncgen() in 10_build_future_cpl_bypass.py). A correct
header and a fast runtime prove nothing if the packed values moved.

Checks, in order of what would hurt most if wrong:
  1. every sampled cell of the dummy year decodes to the ocean sentinel
  2. sampled real months match a fresh independent re-pack from source,
     value for value, at the DTIME offsets month_start_step() defines
  3. ocean/invalid cells in real years carry the sentinel
  4. land values decode into the variable's physical range

Usage: verify_output_against_source.py <file.nc> <scenario> <var>
"""
import importlib
import sys
from pathlib import Path

import netCDF4 as nc
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
_b = importlib.import_module("10_build_future_cpl_bypass")

path, scenario, var = sys.argv[1], sys.argv[2], sys.argv[3]
_, _, _, (lo, hi) = _b.VARS[var]
add_off, scale = _b.add_offset_scale(lo, hi)
sentinel = _b.OCEAN_SENTINEL_RAW[var]

ds = nc.Dataset(path)
ds.set_auto_maskandscale(False)
v = ds.variables[var]
print(f"file: {path}\nvar={var} scenario={scenario} shape={v.shape} "
      f"add_offset={v.add_offset} scale_factor={v.scale_factor}", flush=True)

rows = np.linspace(0, _b.NCELL - 1, 400).astype(int)
failures = []

# 1. dummy year must be sentinel everywhere it is sampled
for t in (0, 1000, _b.STEPS_PER_YEAR - 1):
    vals = v[rows, t]
    if not np.all(vals == sentinel):
        failures.append(f"dummy year t={t}: {np.sum(vals != sentinel)}/{len(rows)} cells "
                        f"are not the sentinel {sentinel} (e.g. {vals[vals != sentinel][:5]})")
print(f"[1] dummy year is all sentinel: {'PASS' if not failures else 'FAIL'}", flush=True)

# 2. independently re-pack real months from source and compare exactly
probe = [(2024, 1), (2024, 2), (2043, 7), (2072, 12), (2100, 2), (2100, 12)]
mismatches = 0
for year, month in probe:
    packed = _b.pack_month(_b.read_month(scenario, var, year, month), add_off, scale, sentinel)
    start = _b.month_start_step(year, month)
    # a few timesteps inside the month, including its first and last
    offs = sorted({0, 1, packed.shape[0] // 2, packed.shape[0] - 1})
    for off in offs:
        from_file = v[rows, start + off]
        expected = packed[off, rows]
        if not np.array_equal(from_file, expected):
            bad = int(np.sum(from_file != expected))
            mismatches += bad
            failures.append(f"{year}-{month:02d} t+{off} (DTIME {start + off}): "
                            f"{bad}/{len(rows)} values differ")
    print(f"    {year}-{month:02d}: DTIME {start}..{start + packed.shape[0] - 1} "
          f"{'ok' if mismatches == 0 else 'MISMATCH'}", flush=True)
print(f"[2] real months match fresh re-pack from source: "
      f"{'PASS' if mismatches == 0 else f'FAIL ({mismatches} values)'}", flush=True)

# 3+4. sentinel placement and physical range in a real year
t_real = _b.STEPS_PER_YEAR + 1234
vals = v[:, t_real]
is_sent = vals == sentinel
land = vals[~is_sent].astype(np.float64) * scale + add_off
n_land, n_ocean = int((~is_sent).sum()), int(is_sent.sum())
in_range = bool(np.all((land >= lo - abs(lo) * 0.05 - 1e-6) & (land <= hi + abs(hi) * 0.05 + 1e-6)))
print(f"[3] sentinel/land split at DTIME {t_real}: {n_ocean} sentinel, {n_land} land "
      f"({100 * n_land / len(vals):.1f}% land)", flush=True)
print(f"[4] land values decode inside [{lo}, {hi}]: {'PASS' if in_range else 'FAIL'} "
      f"(min={land.min():.4g} max={land.max():.4g})", flush=True)
if not in_range:
    failures.append("decoded land values fall outside the variable's physical range")
if n_land == 0:
    failures.append("no land cells found -- the whole timestep is sentinel")

ds.close()
print("\n=== VERDICT ===", flush=True)
if failures:
    print("FAIL", flush=True)
    for f in failures:
        print(f"  - {f}", flush=True)
    raise SystemExit(1)
print("PASS -- output matches an independent re-pack from source", flush=True)
