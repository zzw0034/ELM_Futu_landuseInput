#!/usr/bin/env python
"""Build an ELM CPL_BYPASS forcing file for one variable of one
CanESM5-DBCCA-TESSFA2 SSP scenario, covering 2024-2100.

Reads the monthly 3-hourly clmforc files already produced for TESSFA2
(Precip3Hrly/Solar3Hrly/TPHWL3Hrly), strips Feb 29 (the source calendar is
Gregorian; the model's CALENDAR=NO_LEAP needs a fixed 365 days/year),
reindexes the grid to the flattened n=225625 order used by
zone_mappings.txt (n = ilon*NLAT + ilat), packs to int16 with the same
add_offset/scale_factor convention as the historical production script
(makezones_reanalysis.f90), and prepends one unused dummy year (2023) so
the file works with the startyear_met=2023 branch in lnd_import_export.F90.

Output: DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc -- the exact filename
the patched Fortran reader constructs for metdata_type='era5-daymet-fut'.

Two design choices carry the whole runtime; both are explained where they
happen (build_header_with_ncgen, and the staging/merge split in main) and
summarised in README.md. Changing either one back will make this take hours
instead of minutes.

usage: build_cpl_bypass_tessfa2.py --scenario ssp245 --var TBOT [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import calendar
import os
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import netCDF4 as nc
import numpy as np

TESSFA2_ROOT = Path("/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5")
# Use the copy INSIDE cpl_bypass_full/, not the one in the parent
# Daymet_ERA5_TESSFA2/ directory. Same filename, different file: the parent
# copy has zones 2-7 with grid_map restarting per zone, while this one has
# every zone flattened to 1 with a single global 1..225625 index -- and that
# is what the model actually reads, since metdata_bypass points at
# cpl_bypass_full/.
ZONE_MAPPINGS = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
                     "Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt")
# NOTE: /scratch is purged periodically, unlike /projects. Move the finished
# files somewhere durable (and update metdata_bypass) before the real runs.
OUT_ROOT = Path("/scratch/hpcl-cli185/zw5/future_clim")
NCGEN = "/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/ncgen"

NLON, NLAT = 625, 361
NCELL = NLON * NLAT
RES_HOURS = 3
STEPS_PER_DAY = 24 // RES_HOURS          # 8
STEPS_PER_YEAR = 365 * STEPS_PER_DAY     # 2920, fixed NOLEAP cadence
Y0, Y1 = 2024, 2100                      # real data years
DUMMY_YEAR = 2023                        # never read; see module docstring
ROW_CHUNK = 20000                        # rows per merge write

# variable -> (source subdir, source file prefix, source var name, packing range).
# Packing ranges match makezones_reanalysis.f90's data_ranges, so the
# resulting add_offset/scale_factor line up with the historical files.
VARS = {
    "PRECTmms": ("Precip3Hrly", "clmforc.4km.Prec", "PRECTmms", (-0.04, 0.04)),
    "FSDS":     ("Solar3Hrly",  "clmforc.4km.Solr", "FSDS",     (-20.0, 2000.0)),
    "TBOT":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "TBOT",    (175.0, 350.0)),
    "QBOT":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "QBOT",    (0.0, 0.10)),
    "FLDS":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "FLDS",    (0.0, 1000.0)),
    "PSRF":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "PSRF",    (20000.0, 120000.0)),
    "WIND":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "WIND",    (-1.0, 100.0)),
}

# Raw packed sentinel values taken from the historical cpl_bypass files
# (Daymet_ERA5_TESSFA.4km_<VAR>_1980-2023_z01.nc), so ocean/invalid cells
# decode identically in the historical and future forcing.
OCEAN_SENTINEL_RAW = {
    "TBOT": 22725, "PSRF": -23831, "QBOT": -14592, "FSDS": -30984,
    "PRECTmms": -32768, "WIND": -14600, "FLDS": 14924,
}


def add_offset_scale(lo: float, hi: float) -> tuple[float, float]:
    off = (hi + lo) / 2.0
    scale = (hi - lo) * 1.1 / 2 ** 15
    return off, scale


def load_grid_order() -> tuple[np.ndarray, np.ndarray]:
    """LONGXY(n), LATIXY(n) in the same order as zone_mappings.txt."""
    lon = np.empty(NCELL, dtype=np.float64)
    lat = np.empty(NCELL, dtype=np.float64)
    n_lines = 0
    with open(ZONE_MAPPINGS) as f:
        for i, line in enumerate(f):
            if i >= NCELL:
                raise AssertionError(f"{ZONE_MAPPINGS} has more than {NCELL} rows")
            parts = line.split()
            lon[i] = float(parts[0])
            lat[i] = float(parts[1])
            n_lines += 1
    if n_lines != NCELL:
        raise AssertionError(f"{ZONE_MAPPINGS} has {n_lines} rows, expected {NCELL}")
    return lon, lat


def strip_feb29(times: np.ndarray, arr: np.ndarray) -> np.ndarray:
    """times: datetime64 array aligned to arr's first axis."""
    months = times.astype("datetime64[M]").astype(int) % 12 + 1
    days = (times - times.astype("datetime64[M]")).astype("timedelta64[D]").astype(int) + 1
    keep = ~((months == 2) & (days == 29))
    return arr[keep]


def read_month(scenario: str, var: str, year: int, month: int) -> np.ndarray:
    subdir, prefix, srcvar, _ = VARS[var]
    path = (TESSFA2_ROOT / f"CanESM5_{scenario}_r1i1p1f1_DBCCA_Daymet_TESSFA2" /
            subdir / f"{prefix}.{year:04d}-{month:02d}.nc")
    with nc.Dataset(path) as ds:
        raw = ds.variables[srcvar][:]  # (time, lat, lon) float32, _FillValue -> masked
        raw = raw.filled(np.nan).astype(np.float32, copy=False)
        t = ds.variables["time"]
        times = nc.num2date(t[:], t.units, calendar=getattr(t, "calendar", "standard"))
    expect = calendar.monthrange(year, month)[1] * STEPS_PER_DAY
    if raw.shape[0] != expect:
        raise AssertionError(f"{path}: expected {expect} steps, got {raw.shape[0]}")
    if month == 2 and calendar.isleap(year):
        times_dt = np.array([np.datetime64(f"{d.year:04d}-{d.month:02d}-{d.day:02d}")
                             for d in times])
        raw = strip_feb29(times_dt, raw)
        assert raw.shape[0] == 28 * STEPS_PER_DAY, raw.shape
    return raw


def pack_month(raw_lat_lon: np.ndarray, add_off: float, scale: float,
               raw_sentinel: int) -> np.ndarray:
    """(ntime, NLAT, NLON) float32, NaN over ocean -> (ntime, NCELL) int16, n-ordered.

    Stays in float32 and reuses one buffer for the offset/scale/round chain
    in place. Chaining separate expressions instead allocates a float64-sized
    temporary per step, which with many concurrent workers was enough to
    trigger OOM kills (measured ~2-3GB per worker against ~223MB/month of
    source data; this version stays under ~500MB).
    """
    ntime = raw_lat_lon.shape[0]
    # (time, lat, lon) -> (time, lon, lat), so flattening the last two axes
    # gives n = ilon*NLAT + ilat, matching zone_mappings.txt row order.
    arr = np.transpose(raw_lat_lon, (0, 2, 1)).reshape(ntime, NCELL).astype(np.float32, copy=True)
    valid = np.isfinite(arr)
    arr -= np.float32(add_off)
    arr /= np.float32(scale)
    np.round(arr, out=arr)
    np.clip(arr, -32767, 32767, out=arr)  # -32768 stays reserved for the PRECTmms sentinel
    arr[~valid] = 0.0  # NaN -> int16 is undefined behaviour; overwritten below anyway
    packed = arr.astype(np.int16)
    packed[~valid] = raw_sentinel
    return packed


def _cdl_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_header_with_ncgen(path, var, total_steps, add_off, scale, global_attrs):
    """Write the file's COMPLETE header -- dimensions, all four variables and
    every attribute -- in a single ncgen pass.

    Do not replace this with netCDF4-python. These are classic
    (NETCDF3_64BIT_OFFSET) files, whose header sits at the front of the file,
    so a header that grows shifts -- and therefore rewrites -- everything
    behind it, here the whole ~96GiB packed variable. netCDF4-python wraps
    each individually-set attribute on a NETCDF3 file in its own
    nc_redef/nc_enddef pair (its own setncatts docstring says so), so setting
    the ~9 attributes this file carries after declaring the big variable cost
    ~9 full-file rewrites: file creation ran for hours with no data on disk.
    Reordering and setncatts() batching only get that to 1 rewrite, because
    add_offset/scale_factor cannot be set before the variable exists.

    ncgen emits everything in one define session and one nc_enddef, exactly
    as the historical Fortran producer (makezones_reanalysis.f90) does.
    Measured: 0.1s and 0 bytes written for a 95.7GiB header, verified to
    produce format kind "64-bit offset", correct attribute values, and
    byte-exact round-trip of packed int16 data.

    The caller then opens the file with mode="a" and writes data; data writes
    never touch the header. Adding an attribute after this point brings the
    whole problem back.

    -6 = 64-bit offset (what NETCDF3_64BIT_OFFSET means, matching the
    historical files); -x = no fill, so declaring the variable costs nothing.
    """
    lines = [f"netcdf {path.stem} {{", "dimensions:",
             f"\tn = {NCELL} ;", f"\tDTIME = {total_steps} ;", "variables:",
             "\tdouble DTIME(DTIME) ;",
             '\t\tDTIME:long_name = "Day of Year" ;',
             f'\t\tDTIME:units = "Days since {DUMMY_YEAR}-01-01 00:00" ;',
             "\tfloat LONGXY(n) ;", "\tfloat LATIXY(n) ;",
             f"\tshort {var}(n, DTIME) ;",
             # repr of the float32-rounded value, so ncgen stores the same
             # bits netCDF4-python's np.float32(...) would have stored.
             f"\t\t{var}:add_offset = {float(np.float32(add_off))!r}f ;",
             f"\t\t{var}:scale_factor = {float(np.float32(scale))!r}f ;",
             "", "// global attributes:"]
    for k, v in global_attrs.items():
        if isinstance(v, str):
            lines.append(f'\t\t:{k} = "{_cdl_escape(v)}" ;')
        else:  # int16 sentinel -- the 's' suffix keeps it a short
            lines.append(f"\t\t:{k} = {int(v)}s ;")
    lines.append("}")

    cdl_path = path.with_suffix(path.suffix + ".cdl")
    cdl_path.write_text("\n".join(lines) + "\n")
    res = subprocess.run([NCGEN, "-6", "-x", "-b", "-o", str(path), str(cdl_path)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ncgen failed (rc={res.returncode}):\n{res.stdout}\n{res.stderr}")
    cdl_path.unlink()


def create_stage_file(path, var):
    """One transient per-year staging file: raw packed int16, no attributes.

    Deliberately carries no add_offset/scale_factor -- setting an attribute
    after declaring the variable rewrites the file (see
    build_header_with_ncgen), ~1.3GiB each here but ~200GiB across 78 files.
    Safe to omit: these are read back with set_auto_maskandscale(False),
    which returns the stored int16 regardless of attributes, and they are
    deleted once the merge succeeds. The real packing metadata lives in the
    final file's header.
    """
    ds = nc.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", STEPS_PER_YEAR)
    v = ds.createVariable(var, "i2", ("n", "DTIME"), fill_value=False)
    v.set_auto_scale(False)
    return ds, v


def stage_year(scenario, var, year, add_off, scale, raw_sentinel, stage_path):
    """Worker: read + pack one year's 12 months and write its own staging file.

    The write happens here, in the worker, not back in the main process: each
    year is a separate file with no shared handle, so all of this runs fully
    in parallel across years.
    """
    months = [pack_month(read_month(scenario, var, year, m), add_off, scale, raw_sentinel)
              for m in range(1, 13)]
    block = np.concatenate(months, axis=0)  # (STEPS_PER_YEAR, NCELL)
    ds, v = create_stage_file(stage_path, var)
    v[:, :] = block.T
    ds.close()
    return year, stage_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True,
                    choices=["ssp119", "ssp245", "ssp370", "ssp585"])
    ap.add_argument("--var", required=True, choices=list(VARS))
    ap.add_argument("--out-dir", default=None, help="override OUT_ROOT/<scenario>")
    args = ap.parse_args()

    var = args.var
    _, _, _, (lo, hi) = VARS[var]
    add_off, scale = add_offset_scale(lo, hi)
    raw_sentinel = OCEAN_SENTINEL_RAW[var]

    out_dir = Path(args.out_dir) if args.out_dir else OUT_ROOT / args.scenario
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DBCCA_Daymet_TESSFA2_{var}_2023-2100_z01.nc"
    # Write under .partial and only rename once every year is in and the file
    # is closed, so an interrupted run never leaves something that looks
    # finished at the path the Fortran reader will look for.
    tmp_path = out_path.with_suffix(out_path.suffix + ".partial")
    stage_dir = out_dir / f"_stage_{var}"

    if tmp_path.exists():
        print(f"[{var}/{args.scenario}] removing leftover {tmp_path}", flush=True)
        tmp_path.unlink()
    if stage_dir.exists():
        print(f"[{var}/{args.scenario}] removing leftover staging dir {stage_dir}", flush=True)
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    print(f"[{var}/{args.scenario}] add_offset={add_off} scale_factor={scale} "
          f"ocean_sentinel_raw={raw_sentinel}", flush=True)
    t0 = time.time()

    # ---- Stage: one small file per year ----
    # Writing year-by-year straight into the final (n, DTIME) file is the
    # obvious approach and is ~23x slower: DTIME is the fastest-varying
    # dimension, so a write covering one year but all rows touches every one
    # of the 225,625 rows non-contiguously. Staging first lets the merge
    # below write each row's full time series in one contiguous block.
    dummy_path = stage_dir / f"y{DUMMY_YEAR}.nc"
    ds_d, v_d = create_stage_file(dummy_path, var)
    v_d[:, :] = np.full((NCELL, STEPS_PER_YEAR), raw_sentinel, dtype=np.int16)
    ds_d.close()
    print(f"[{var}/{args.scenario}] dummy year {DUMMY_YEAR} staged "
          f"({time.time() - t0:.1f}s)", flush=True)

    nworkers = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 4))
    n_years = Y1 - Y0 + 1
    print(f"[{var}/{args.scenario}] {n_years} years to stage with {nworkers} workers",
          flush=True)

    year_files = {DUMMY_YEAR: dummy_path}
    done = 0
    with ProcessPoolExecutor(max_workers=nworkers) as pool:
        futures = [pool.submit(stage_year, args.scenario, var, y, add_off, scale,
                               raw_sentinel, stage_dir / f"y{y}.nc")
                   for y in range(Y0, Y1 + 1)]
        for fut in as_completed(futures):
            year, path = fut.result()
            year_files[year] = path
            done += 1
            print(f"[{var}/{args.scenario}] staged {done}/{n_years} years "
                  f"(last: {year}, {time.time() - t0:.1f}s)", flush=True)
    assert done == n_years, f"{done}/{n_years} years staged"
    print(f"[{var}/{args.scenario}] STAGING done: {time.time() - t0:.1f}s", flush=True)

    # ---- Merge: reassemble row-chunk by row-chunk ----
    all_years = [DUMMY_YEAR] + list(range(Y0, Y1 + 1))
    total_steps = STEPS_PER_YEAR * len(all_years)
    global_attrs = {
        "title": "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing",
        "source": (f"CanESM5 {args.scenario} r1i1p1f1, DBCCA bias-corrected/downscaled "
                   f"against Daymet, TESSFA2 (SEUS) 4km grid"),
        "comment": (
            f"Record 1 (DTIME index 0-{STEPS_PER_YEAR - 1}, nominal year {DUMMY_YEAR}) is an "
            "UNUSED PLACEHOLDER YEAR, not real data. It exists only so that "
            "startyear_met in the patched cpl_bypass reader (lnd_import_export.F90, "
            "metdata_type='era5-daymet-fut') can be set to one year before the future "
            "run's real first year (2024), which avoids a tindex wraparound bug in a "
            "shared bound-check for runs whose first model year equals startyear_met "
            f"exactly. Every cell of the {DUMMY_YEAR} record (land and ocean) holds the "
            "same raw sentinel value used for ocean/invalid cells in the real years, so "
            "it decodes to an obviously out-of-range value and fails loudly if ever read "
            f"by mistake. Real forcing begins at DTIME index {STEPS_PER_YEAR} "
            "(2024-01-01 00:00Z, 3-hourly, mid-interval timestamps)."
        ),
        "calendar_note": ("Source CanESM5-DBCCA-TESSFA2 data use a standard (Gregorian, "
                          "leap-year) calendar; Feb 29 was removed from every leap year "
                          "to match the model's CALENDAR=NO_LEAP (fixed 365 days/year, "
                          "2920 3-hourly steps/year)."),
        "ocean_sentinel_raw": np.int16(raw_sentinel),
        "ocean_sentinel_note": ("Raw packed value used for ocean/invalid gridcells, taken "
                                "unchanged from the historical Daymet_ERA5_TESSFA.4km_"
                                f"{var}_1980-2023_z01.nc file so decoded sentinel behaviour "
                                "is identical between the historical and future forcing."),
    }
    build_header_with_ncgen(tmp_path, var, total_steps, add_off, scale, global_attrs)

    # Append mode: the header is complete and final. Never set an attribute
    # past this point -- see build_header_with_ncgen.
    ds_final = nc.Dataset(tmp_path, "a")
    v_final = ds_final.variables[var]
    v_final.set_auto_scale(False)  # data below is already packed int16

    lon, lat = load_grid_order()
    ds_final.variables["LONGXY"][:] = lon
    ds_final.variables["LATIXY"][:] = lat
    ds_final.variables["DTIME"][:] = (np.arange(1, total_steps + 1) / STEPS_PER_DAY
                                      - 0.5 * (RES_HOURS / 24.0))
    print(f"[{var}/{args.scenario}] final file created ({time.time() - t0:.1f}s)", flush=True)

    readers = [nc.Dataset(year_files[y]) for y in all_years]
    for r in readers:
        r.set_auto_maskandscale(False)
    n_chunks = (NCELL + ROW_CHUNK - 1) // ROW_CHUNK
    for c in range(n_chunks):
        r0 = c * ROW_CHUNK
        r1 = min(r0 + ROW_CHUNK, NCELL)
        # Each staged read is a contiguous slice within its small file, and
        # the write below is one contiguous block of the final file.
        chunk = np.concatenate([r.variables[var][r0:r1, :] for r in readers], axis=1)
        v_final[r0:r1, :] = chunk
        print(f"[{var}/{args.scenario}] merge chunk {c + 1}/{n_chunks} "
              f"(rows {r0}:{r1}) ({time.time() - t0:.1f}s)", flush=True)
    for r in readers:
        r.close()
    ds_final.close()

    final_size = tmp_path.stat().st_size
    expected_min = NCELL * total_steps * 2
    if final_size < expected_min:
        raise AssertionError(f"{tmp_path} is {final_size} bytes, expected >= {expected_min}")
    tmp_path.rename(out_path)
    shutil.rmtree(stage_dir)
    total = time.time() - t0
    print(f"[{var}/{args.scenario}] done: {out_path} ({final_size} bytes), "
          f"staging cleaned up.", flush=True)
    print(f"[{var}/{args.scenario}] TOTAL WALL TIME: {total:.1f}s ({total / 60:.1f} min)",
          flush=True)


if __name__ == "__main__":
    main()
