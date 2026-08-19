#!/usr/bin/env python
"""Approach B (split into small per-year staging files, then ROW-MAJOR
merge) production build for one variable of one CanESM5-DBCCA-TESSFA2 SSP
scenario -- full 78-year production-scale test, alongside the existing
year-batched approach (10_build_future_cpl_bypass.py, "Approach A").

Reuses read_month/pack_month/load_grid_order/VARS/OCEAN_SENTINEL_RAW/
add_offset_scale/STEPS_PER_DAY/RES_HOURS from 10_build_future_cpl_bypass.py
unchanged -- packing semantics are guaranteed identical to Approach A;
only the write strategy (and worker task granularity) differs:

  Stage: one worker task per YEAR (not per month, unlike Approach A) --
  each worker reads+packs its own 12 months and writes them straight to
  its own small per-year file (n, STEPS_PER_YEAR) under a staging
  subdirectory. Since every year is a separate file with no shared
  handle, the write happens directly in the worker, fully in parallel
  across up to nworkers years at once -- no need to funnel writes
  through the main process the way Approach A's single shared final
  file requires.

  Merge: once every year (dummy + all real years) is staged, create the
  final (n, DTIME) file and fill it row-chunk by row-chunk -- for each
  chunk of rows, read that chunk's data from every staged year file
  (each read is a contiguous slice within that small file) and
  concatenate + write it as ONE contiguous block into the final file.
  Every write into the final file is then sequential, not strided
  across all 225,625 rows (which is what makes Approach A slow).

Validated on a 3-year real-data sample (ssp370/PRECTmms, job 465163,
2026-08-18): produced byte-identical output to Approach A, ~31x faster
on the pure data-movement portion. This script is the first full
78-year production-scale test of the same approach.

See future_climate/README_cpl_bypass_future.md for background on the
overall pipeline design (dummy year, ocean sentinels, calendar handling).
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import netCDF4 as nc
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
_base = importlib.import_module("10_build_future_cpl_bypass")

NCELL = _base.NCELL
STEPS_PER_YEAR = _base.STEPS_PER_YEAR
STEPS_PER_DAY = _base.STEPS_PER_DAY
RES_HOURS = _base.RES_HOURS
Y0, Y1 = _base.Y0, _base.Y1
DUMMY_YEAR = _base.DUMMY_YEAR
VARS = _base.VARS
OCEAN_SENTINEL_RAW = _base.OCEAN_SENTINEL_RAW
add_offset_scale = _base.add_offset_scale
load_grid_order = _base.load_grid_order
read_month = _base.read_month
pack_month = _base.pack_month
build_header_with_ncgen = _base.build_header_with_ncgen

ROW_CHUNK = 20000


def create_var_file(path, var, total_steps):
    """One transient per-year staging file: raw packed int16, no attributes.

    Deliberately carries NO add_offset/scale_factor. Setting an attribute
    after declaring the variable rewrites the whole file (see
    build_header_with_ncgen() in 10_build_future_cpl_bypass.py) -- only
    ~1.3GiB each here rather than ~96GiB, but that is still ~200GiB of
    pointless I/O across 78 files x 2 attributes. Safe to omit: these files
    are read back below with set_auto_maskandscale(False), which returns the
    stored int16 untouched regardless of attributes, and they are deleted
    once the merge succeeds. The real packing metadata lives in the final
    file's ncgen-built header.
    """
    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", total_steps)
    v = ds.createVariable(var, "i2", ("n", "DTIME"), fill_value=False)
    v.set_auto_scale(False)
    return ds, v


def process_and_stage_year(scenario, var, year, add_off, scale, raw_sentinel, stage_path):
    """Worker: read+pack all 12 months of one year AND write that year's own
    small staging file, entirely inside this worker process. Safe to run
    fully in parallel across years -- unlike Approach A's shared final file,
    each year here is a separate file with no cross-process handle
    contention, so there's no reason to route the write back through the
    main process."""
    months = [pack_month(read_month(scenario, var, year, m), add_off, scale, raw_sentinel)
              for m in range(1, 13)]
    block = np.concatenate(months, axis=0)  # (2920, NCELL)
    ds, v = create_var_file(stage_path, var, STEPS_PER_YEAR)
    v[:, :] = block.T
    ds.close()
    return year, stage_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=["ssp119", "ssp245", "ssp370", "ssp585"])
    ap.add_argument("--var", required=True, choices=list(VARS))
    ap.add_argument("--out-dir", default=None, help="override OUT_ROOT/<scenario>")
    args = ap.parse_args()

    var = args.var
    _, _, _, (lo, hi) = VARS[var]
    add_off, scale = add_offset_scale(lo, hi)
    raw_sentinel = OCEAN_SENTINEL_RAW[var]

    out_dir = Path(args.out_dir) if args.out_dir else _base.OUT_ROOT / args.scenario
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DBCCA_Daymet_TESSFA2_{var}_2023-2100_z01.nc"
    tmp_path = out_path.with_suffix(out_path.suffix + ".partial")
    stage_dir = out_dir / f"_stage_{var}"

    if tmp_path.exists():
        print(f"[{var}/{args.scenario}] removing leftover {tmp_path}", flush=True)
        tmp_path.unlink()
    if stage_dir.exists():
        print(f"[{var}/{args.scenario}] removing leftover staging dir {stage_dir}", flush=True)
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    print(f"[{var}/{args.scenario}] APPROACH B (row-major merge), add_offset={add_off} "
          f"scale_factor={scale} ocean_sentinel_raw={raw_sentinel}", flush=True)

    t0 = time.time()

    # ---- Stage: dummy year (pure sentinel, no source read needed) ----
    dummy_path = stage_dir / f"y{DUMMY_YEAR}.nc"
    ds_d, v_d = create_var_file(dummy_path, var, STEPS_PER_YEAR)
    v_d[:, :] = np.full((NCELL, STEPS_PER_YEAR), raw_sentinel, dtype=np.int16)
    ds_d.close()
    print(f"[{var}/{args.scenario}] dummy year {DUMMY_YEAR} staged ({time.time() - t0:.1f}s)", flush=True)

    # ---- Stage: real years -- one task per YEAR, each worker reads+packs its ----
    # ---- own 12 months AND writes its own staging file, fully in parallel ----
    # ---- (no shared file handle, so no reason to funnel writes through the ----
    # ---- main process the way Approach A must) ----
    nworkers = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 4))
    n_years_total = Y1 - Y0 + 1
    print(f"[{var}/{args.scenario}] {n_years_total} years to stage with {nworkers} worker processes "
          f"(one year per worker task)", flush=True)

    year_files = {DUMMY_YEAR: dummy_path}
    done_years = 0

    with ProcessPoolExecutor(max_workers=nworkers) as pool:
        futures = {
            pool.submit(process_and_stage_year, args.scenario, var, y, add_off, scale, raw_sentinel,
                        stage_dir / f"y{y}.nc"): y
            for y in range(Y0, Y1 + 1)
        }
        for fut in as_completed(futures):
            year, path = fut.result()
            year_files[year] = path
            done_years += 1
            print(f"[{var}/{args.scenario}] staged {done_years}/{n_years_total} years "
                  f"(last: {year}, {time.time() - t0:.1f}s)", flush=True)

    assert done_years == n_years_total, f"{done_years}/{n_years_total} years staged"
    t_stage = time.time() - t0
    print(f"[{var}/{args.scenario}] STAGING done: {t_stage:.1f}s", flush=True)

    # ---- Merge: row-major reassembly into the final file ----
    n_years_all = n_years_total + 1  # + dummy year
    total_steps = STEPS_PER_YEAR * n_years_all
    all_years_ordered = [DUMMY_YEAR] + list(range(Y0, Y1 + 1))

    # Header built entirely by ncgen in one pass -- see
    # build_header_with_ncgen() in 10_build_future_cpl_bypass.py for why
    # (building it with netCDF4-python cost 8-9 full ~96GiB rewrites here and
    # is what stalled jobs 465175/465183/465246/465247).
    global_attrs = {
        "title": "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing",
        "source": (f"CanESM5 {args.scenario} r1i1p1f1, DBCCA bias-corrected/downscaled "
                   f"against Daymet, TESSFA2 (SEUS) 4km grid"),
        "build_method": ("Approach B: staged per-year files, then row-major merge; "
                         "header written in one pass by ncgen "
                         "(see future_climate/README_cpl_bypass_future.md)"),
        "comment": (
            f"Record 1 (DTIME index 0-{STEPS_PER_YEAR - 1}, nominal year {DUMMY_YEAR}) is an "
            "UNUSED PLACEHOLDER YEAR, not real data. It exists only so that "
            "startyear_met in the patched cpl_bypass reader (lnd_import_export.F90, "
            "metdata_type='era5-daymet-fut') can be set to one year before the "
            "future run's real first year (2024), which avoids a tindex "
            "wraparound bug in a shared bound-check for runs whose first model "
            f"year equals startyear_met exactly. Every cell of the {DUMMY_YEAR} "
            "record (land and ocean) is filled with the same raw sentinel value "
            "used for ocean/invalid cells in the real years. Real forcing begins "
            f"at DTIME index {STEPS_PER_YEAR} (2024-01-01 00:00Z, 3-hourly, "
            "mid-interval timestamps)."
        ),
        "calendar_note": ("Source CanESM5-DBCCA-TESSFA2 data use a standard (Gregorian, "
                          "leap-year) calendar; Feb 29 was removed from every leap year "
                          "to match the model's CALENDAR=NO_LEAP (fixed 365 days/year, "
                          "2920 3-hourly steps/year)."),
        "ocean_sentinel_raw": np.int16(raw_sentinel),
        "ocean_sentinel_note": ("Raw packed value used for ocean/invalid gridcells, taken "
                                "unchanged from the historical Daymet_ERA5_TESSFA.4km_"
                                f"{var}_1980-2023_z01.nc file so decoded sentinel behavior "
                                "is identical between the historical and future forcing."),
    }
    build_header_with_ncgen(tmp_path, var, total_steps, add_off, scale, raw_sentinel,
                            global_attrs)

    # Append mode: header is complete and final. Never add an attribute past
    # this point -- that is what reintroduces the full-file rewrite.
    ds_final = nc.Dataset(tmp_path, "a")
    v_final = ds_final.variables[var]
    v_final.set_auto_scale(False)

    lon, lat = load_grid_order()
    ds_final.variables["LONGXY"][:] = lon
    ds_final.variables["LATIXY"][:] = lat
    ds_final.variables["DTIME"][:] = (np.arange(1, total_steps + 1) / STEPS_PER_DAY
                                      - 0.5 * (RES_HOURS / 24.0))
    print(f"[{var}/{args.scenario}] final file created ({time.time() - t0:.1f}s)", flush=True)

    readers = [nc.Dataset(year_files[y]) for y in all_years_ordered]
    for r in readers:
        r.set_auto_maskandscale(False)

    n_chunks = (NCELL + ROW_CHUNK - 1) // ROW_CHUNK
    for c in range(n_chunks):
        r0 = c * ROW_CHUNK
        r1 = min(r0 + ROW_CHUNK, NCELL)
        chunk = np.concatenate([readers[i].variables[var][r0:r1, :] for i in range(n_years_all)], axis=1)
        v_final[r0:r1, :] = chunk
        print(f"[{var}/{args.scenario}] merge chunk {c + 1}/{n_chunks} (rows {r0}:{r1}) "
              f"({time.time() - t0:.1f}s)", flush=True)
    for r in readers:
        r.close()
    ds_final.close()
    t_total = time.time() - t0
    print(f"[{var}/{args.scenario}] MERGE done, TOTAL SO FAR: {t_total:.1f}s", flush=True)

    final_size = tmp_path.stat().st_size
    expected_min = NCELL * total_steps * 2
    if final_size < expected_min:
        raise AssertionError(f"{tmp_path} is {final_size} bytes, expected at least {expected_min}")
    tmp_path.rename(out_path)
    shutil.rmtree(stage_dir)
    print(f"[{var}/{args.scenario}] done: {out_path} ({final_size} bytes), staging cleaned up.", flush=True)
    print(f"[{var}/{args.scenario}] TOTAL WALL TIME (Approach B, full pipeline): {t_total:.1f}s "
          f"({t_total / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
