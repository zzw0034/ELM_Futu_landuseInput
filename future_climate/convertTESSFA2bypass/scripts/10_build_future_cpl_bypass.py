#!/usr/bin/env python
"""Build a CPL_BYPASS-format future (2024-2100) forcing file for one variable
of one CanESM5-DBCCA-TESSFA2 SSP scenario.

Reads the monthly 3-hourly clmforc files already produced for TESSFA2
(Precip3Hrly/Solar3Hrly/TPHWL3Hrly), strips Feb 29 (source calendar is
standard/Gregorian; the model's CALENDAR=NO_LEAP requires a fixed 365
days/year), reindexes the spatial grid to the flattened n=225625 order used
by zone_mappings.txt (n = ilon*361 + ilat, lon outer/lat inner, both
ascending -- verified to match the future files' own ascending lon/lat
arrays), packs to int16 using the same add_offset/scale_factor convention as
the historical makezones_reanalysis.f90 production script, and prepends one
unused dummy year (2023) so the file works with the startyear_met=2023 branch
added to lnd_import_export.F90 (commit f07c14d429). See
future_climate/README_cpl_bypass_future.md for the full design rationale.

Output: DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc, matching the filename the
patched Fortran reader constructs for metdata_type='era5-daymet-fut'.
"""
from __future__ import annotations

import argparse
import calendar
import os
import subprocess
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import netCDF4 as nc
import numpy as np

TESSFA2_ROOT = Path("/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5")
# NOT .../Daymet_ERA5_TESSFA2/zone_mappings.txt (parent dir) -- that's a
# different, older file (md5 differs; found 2026-08-17): its zone column is
# 2-7 with grid_map resetting per zone, matching cpl_bypass_full/7zone/, but
# NOT what the model actually reads. This copy, physically inside
# cpl_bypass_full/, has every row's zone flattened to 1 with grid_map as a
# single global 1..225625 index, matching the merged z01.nc files (and is
# what `metdata_bypass`+'/zone_mappings.txt' resolves to in the Fortran
# reader, since metdata_bypass points at cpl_bypass_full/). Only lon/lat are
# read here (used for LONGXY/LATIXY ordering) and those columns are
# identical between the two files, so this only matters for which file gets
# copied into each scenario's output dir (see submit_future_cpl_bypass.sbatch)
# -- but use the authoritative one here too, for consistency.
ZONE_MAPPINGS = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
                      "Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt")
OUT_ROOT = Path("/scratch/hpcl-cli185/zw5/future_clim")
# NOTE: /scratch is subject to periodic purging, unlike /projects. Fine for
# generating and validating output now; before the actual 2024-2100 future
# case runs, confirm these files still exist or move them to a durable
# location under /projects and update metdata_bypass accordingly.

NLON, NLAT = 625, 361
NCELL = NLON * NLAT
RES_HOURS = 3
STEPS_PER_DAY = 24 // RES_HOURS          # 8
STEPS_PER_YEAR = 365 * STEPS_PER_DAY     # 2920, fixed NOLEAP cadence
Y0, Y1 = 2024, 2100                      # real data years
DUMMY_YEAR = 2023                        # never read; see module docstring

# variable -> (source subdir, source file prefix, source var name, packing range)
# packing ranges match makezones_reanalysis.f90's data_ranges (same convention
# as the historical cpl_bypass files, so add_offset/scale_factor line up).
VARS = {
    "PRECTmms": ("Precip3Hrly", "clmforc.4km.Prec", "PRECTmms", (-0.04, 0.04)),
    "FSDS":     ("Solar3Hrly",  "clmforc.4km.Solr", "FSDS",     (-20.0, 2000.0)),
    "TBOT":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "TBOT",    (175.0, 350.0)),
    "QBOT":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "QBOT",    (0.0, 0.10)),
    "FLDS":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "FLDS",    (0.0, 1000.0)),
    "PSRF":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "PSRF",    (20000.0, 120000.0)),
    "WIND":     ("TPHWL3Hrly",  "clmforc.4km.TPQWL", "WIND",    (-1.0, 100.0)),
}

# raw packed sentinel values extracted from the historical cpl_bypass files
# (Daymet_ERA5_TESSFA.4km_<VAR>_1980-2023_z01.nc), verified invariant across
# 200 random ocean indices x 4 time slices per variable, 2026-08-17. User
# instruction: keep ocean/invalid gridcells consistent with the historical
# convention rather than inventing a new fill value.
OCEAN_SENTINEL_RAW = {
    "TBOT": 22725, "PSRF": -23831, "QBOT": -14592, "FSDS": -30984,
    "PRECTmms": -32768, "WIND": -14600, "FLDS": 14924,
}

# day-of-year (0-indexed) at the start of each month, fixed NOLEAP lengths
# (Feb pegged to 28, matching the source data with Feb 29 stripped).
_CUM_DAYS_NOLEAP = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


NCGEN = "/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/ncgen"


def _cdl_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def build_header_with_ncgen(path, var, total_steps, add_off, scale, raw_sentinel,
                            global_attrs):
    """Write the output file's COMPLETE header -- dimensions, all four
    variables, and every attribute -- in a single ncgen pass.

    Why not build the header with netCDF4-python: on a classic
    (NETCDF3_64BIT_OFFSET) file the header lives at the front, so growing it
    shifts everything after it -- here the whole ~96GiB packed variable. And
    netCDF4-python issues nc_redef/nc_enddef around EACH individually-set
    attribute on a NETCDF3 file (its own setncatts docstring says exactly
    this), so the 8-9 attributes these builders set after declaring that
    variable meant 8-9 full-file rewrites. Measured 2026-08-18: that is what
    made "creating the final file" take hours with zero visible progress
    (jobs 465175/465183 stalled 1.5h+; 465246/465247 cancelled after 40min
    still short of it). An isolated benchmark doing nothing but two
    setncatts() calls rewrote ~40GiB in 11 minutes with no data written
    (job 465260).

    Batching with setncatts() is not enough and neither is reordering:
    add_offset/scale_factor cannot be set until the variable exists, and that
    one remaining setncatts() still costs a full rewrite (~44MB/s, ~37min --
    job 465262). ncgen emits the entire header in one define session and one
    nc_enddef, the same way the historical Fortran producer
    (makezones_reanalysis.f90) does, so no rewrite is possible: measured
    **0.1s, 0 MiB written** for this exact 95.7GiB header (job 465276),
    verified to produce format kind "64-bit offset", correct attribute
    values, and byte-exact round-trip of packed int16 data.

    Callers then open the file with mode="a" and write data; data writes
    never touch the header, so the rewrite cannot reappear.

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
        else:  # int16 sentinel -- 's' suffix keeps it a short, as before
            lines.append(f"\t\t:{k} = {int(v)}s ;")
    lines.append("}")

    cdl_path = path.with_suffix(path.suffix + ".cdl")
    cdl_path.write_text("\n".join(lines) + "\n")
    res = subprocess.run([NCGEN, "-6", "-x", "-b", "-o", str(path), str(cdl_path)],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ncgen failed (rc={res.returncode}):\n{res.stdout}\n{res.stderr}")
    cdl_path.unlink()


def month_start_step(year: int, month: int) -> int:
    """0-based global DTIME index of (year, month)'s first record.

    Pure arithmetic (dummy year prefix + fixed NOLEAP month lengths), so it
    doesn't depend on processing order -- lets worker processes write their
    month's block directly without a running counter or fixed submission
    order.
    """
    return (STEPS_PER_YEAR + (year - Y0) * STEPS_PER_YEAR
            + _CUM_DAYS_NOLEAP[month - 1] * STEPS_PER_DAY)


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


def pack_month(raw_lat_lon: np.ndarray, add_off: float, scale: float, raw_sentinel: int) -> np.ndarray:
    """(ntime, NLAT, NLON) float32, NaN over ocean -> (ntime, NCELL) int16, n-ordered.

    Stays in float32 and reuses one buffer for the offset/scale/round chain
    (in place) instead of chaining separate arr-add_off / .../scale / round()
    expressions, each of which would otherwise allocate its own float64-sized
    temporary -- with 16 worker processes doing this concurrently, those
    temporaries were the actual cause of an OOM kill at --mem=48g (measured:
    naive per-worker peak ~2-3GB against float32 source data that's only
    ~223MB/month; this version peaks under ~500MB/worker).
    """
    ntime = raw_lat_lon.shape[0]
    # (time, lat, lon) -> (time, lon, lat): flatten() on the last two axes then
    # gives n = ilon*NLAT + ilat, matching zone_mappings.txt row order.
    # (transpose is a view; reshape on non-contiguous data forces the one copy
    # we actually need, so this is also the only new full-size buffer.)
    arr = np.transpose(raw_lat_lon, (0, 2, 1)).reshape(ntime, NCELL).astype(np.float32, copy=True)
    valid = np.isfinite(arr)
    arr -= np.float32(add_off)
    arr /= np.float32(scale)
    np.round(arr, out=arr)
    np.clip(arr, -32767, 32767, out=arr)  # keep -32768 reserved for the PRECTmms sentinel itself
    arr[~valid] = 0.0  # NaN -> int16 cast is undefined behavior; zero first, overwrite below anyway
    packed = arr.astype(np.int16)
    packed[~valid] = raw_sentinel
    return packed


def strip_feb29(times: np.ndarray, arr: np.ndarray) -> np.ndarray:
    """times: cftime/datetime64 array aligned to arr's first axis."""
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
        raw = raw.filled(np.nan).astype(np.float32, copy=False)  # source is already float32
        t = ds.variables["time"]
        times = nc.num2date(t[:], t.units, calendar=getattr(t, "calendar", "standard"))
    ndays = calendar.monthrange(year, month)[1]
    expect = ndays * STEPS_PER_DAY
    if raw.shape[0] != expect:
        raise AssertionError(f"{path}: expected {expect} steps, got {raw.shape[0]}")
    if month == 2 and calendar.isleap(year):
        times_dt = np.array([np.datetime64(f"{d.year:04d}-{d.month:02d}-{d.day:02d}") for d in times])
        raw = strip_feb29(times_dt, raw)
        assert raw.shape[0] == 28 * STEPS_PER_DAY, raw.shape
    return raw


def process_month(scenario: str, var: str, year: int, month: int,
                   add_off: float, scale: float, raw_sentinel: int):
    """Worker: read + pack one month. Runs in a subprocess -- must not touch
    the (single, main-process-owned) output NetCDF handle."""
    raw = read_month(scenario, var, year, month)
    packed = pack_month(raw, add_off, scale, raw_sentinel)
    return year, month, month_start_step(year, month), packed


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

    out_dir = Path(args.out_dir) if args.out_dir else OUT_ROOT / args.scenario
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DBCCA_Daymet_TESSFA2_{var}_2023-2100_z01.nc"
    # Write under a .partial name and only rename to the real filename (the
    # exact name the patched Fortran reader looks for) once everything below
    # -- all years written, ds.close() succeeded -- has actually happened.
    # An interrupted run (OOM, walltime, crash) then leaves an unambiguous
    # .partial file instead of something that looks like a finished,
    # ready-to-read output at the expected path.
    tmp_path = out_path.with_suffix(out_path.suffix + ".partial")
    if tmp_path.exists():
        leftover = tmp_path.stat().st_size
        print(f"[{var}/{args.scenario}] removing leftover {tmp_path} "
              f"({leftover} bytes)", flush=True)
        tmp_path.unlink()

    print(f"[{var}/{args.scenario}] add_offset={add_off} scale_factor={scale} "
          f"ocean_sentinel_raw={raw_sentinel}", flush=True)
    print(f"[{var}/{args.scenario}] writing {tmp_path} -> {out_path}", flush=True)

    lon, lat = load_grid_order()
    n_years = Y1 - Y0 + 1
    total_steps = STEPS_PER_YEAR + n_years * STEPS_PER_YEAR  # dummy year + real years

    # NETCDF3_64BIT_OFFSET (classic "64-bit offset" format), matching the
    # historical Daymet_ERA5_TESSFA.4km_*_1980-2023_z01.nc files exactly
    # (confirmed via `ncdump -k`) -- NOT NetCDF4/HDF5. An earlier NETCDF4 +
    # chunked version of this script produced a file that read back
    # corrupted (values outside the physical range) once run at the full
    # 78-year scale, even after enlarging the HDF5 chunk cache to fit one
    # full year-chunk (which *did* fix it at the 2-4 year scale tested
    # before scaling up -- the failure mode only showed up with enough
    # out-of-order year-chunks in flight to thrash a cache sized for just
    # one). Classic format has no chunking at all -- writes are direct
    # positional I/O, same as the Fortran production script
    # (makezones_reanalysis.f90) that built the historical files -- so this
    # whole class of bug doesn't apply.
    global_attrs = {
        "title": "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing",
        "source": (f"CanESM5 {args.scenario} r1i1p1f1, DBCCA bias-corrected/downscaled "
                   f"against Daymet, TESSFA2 (SEUS) 4km grid"),
        "comment": (
            f"Record 1 (DTIME index 0-{STEPS_PER_YEAR - 1}, nominal year {DUMMY_YEAR}) is an "
            "UNUSED PLACEHOLDER YEAR, not real data. It exists only so that "
            "startyear_met in the patched cpl_bypass reader (lnd_import_export.F90, "
            "metdata_type='era5-daymet-fut') can be set to one year before the "
            "future run's real first year (2024), which avoids a tindex "
            "wraparound bug in a shared bound-check for runs whose first model "
            f"year equals startyear_met exactly. Every cell of the {DUMMY_YEAR} "
            "record (land and ocean) is filled with the same raw sentinel value "
            "used for ocean/invalid cells in the real years, so it decodes to an "
            "obviously out-of-physical-range value and fails loudly if ever read "
            "by mistake. Real forcing begins at DTIME index "
            f"{STEPS_PER_YEAR} (2024-01-01 00:00Z, 3-hourly, mid-interval "
            "timestamps)."
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
    print(f"[{var}/{args.scenario}] header built by ncgen", flush=True)

    # Append mode: the header is already complete and final, so nothing here
    # can trigger the header-growth rewrite described in
    # build_header_with_ncgen(). Never add an attribute past this point.
    ds = nc.Dataset(tmp_path, "a")
    v_dtime = ds.variables["DTIME"]
    v_lon = ds.variables["LONGXY"]
    v_lat = ds.variables["LATIXY"]
    v_var = ds.variables[var]
    # Data assigned to v_var is already packed int16, not physical values --
    # without this, netCDF4-python's default auto-scale-on-write would
    # (re-)apply (data-add_offset)/scale_factor to it, since add_offset/
    # scale_factor are present in the header.
    v_var.set_auto_scale(False)

    v_lon[:] = lon
    v_lat[:] = lat
    # DTIME is pure arithmetic (doesn't depend on the source data at all) --
    # write it in one shot instead of one nc call per step.
    v_dtime[:] = (np.arange(1, total_steps + 1) / STEPS_PER_DAY
                  - 0.5 * (RES_HOURS / 24.0))

    # dummy year: sentinel everywhere
    v_var[:, 0:STEPS_PER_YEAR] = np.full((NCELL, STEPS_PER_YEAR), raw_sentinel, dtype=np.int16)
    print(f"[{var}/{args.scenario}] dummy year {DUMMY_YEAR} written "
          f"({tmp_path.stat().st_size} bytes so far)", flush=True)

    nworkers = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 4))
    tasks = [(y, m) for y in range(Y0, Y1 + 1) for m in range(1, 13)]
    print(f"[{var}/{args.scenario}] {len(tasks)} months to process with {nworkers} worker processes",
          flush=True)

    # Bounded sliding window, not "submit all 924 up front": workers finish
    # faster than this process's netCDF writes drain them, so an unbounded
    # submit let completed-but-unconsumed results (each a full packed month,
    # ~100+MB) pile up in memory faster than the write loop could keep up --
    # that backlog, not per-worker peak usage, is what OOM-killed the first
    # two attempts at --mem=48g even after the float32 fix. Capping in-flight
    # futures at 2x worker count bounds that backlog to a fixed size.
    window = nworkers * 2
    task_iter = iter(tasks)
    in_flight = set()

    def _submit_next(pool):
        try:
            y, m = next(task_iter)
        except StopIteration:
            return False
        in_flight.add(pool.submit(process_month, args.scenario, var, y, m, add_off, scale, raw_sentinel))
        return True

    # Writes are batched per-year (12 months at a time), not per-month.
    # Measured: a classic-format (n, DTIME) variable's DTIME axis is the
    # fastest-varying dimension, so a write covering a time range touches
    # ALL 225,625 "n" rows once per write call, non-contiguously. Timed a
    # single month-write at ~76-99s -- ~1.4MB/s effective, far below any
    # plausible storage bandwidth, i.e. latency/overhead-bound on those
    # 225,625 separate strided row-touches, not bandwidth-bound. Batching 12
    # months into one write touches each row once instead of twelve times;
    # measured a clean ~12x speedup (80s for a full year vs. ~920-1190s for
    # 12 separate month-writes covering the same data). Tasks are submitted
    # in (year, month) order and the window is a modest multiple of worker
    # count, so only a handful of years are ever "in progress" at once --
    # buffering incomplete years costs at most a few GB, not the whole file.
    year_buf: dict[int, dict[int, np.ndarray]] = {}
    done_months = 0
    done_years = 0
    n_years_total = Y1 - Y0 + 1

    def _flush_year(year):
        nonlocal done_years
        months = year_buf.pop(year)
        block = np.concatenate([months[m] for m in range(1, 13)], axis=0)
        start = month_start_step(year, 1)
        v_var[:, start:start + block.shape[0]] = block.T
        done_years += 1
        print(f"[{var}/{args.scenario}] {done_years}/{n_years_total} years written "
              f"(last: {year}, {done_months}/{len(tasks)} months processed)",
              flush=True)

    with ProcessPoolExecutor(max_workers=nworkers) as pool:
        while len(in_flight) < window and _submit_next(pool):
            pass
        # Workers only read+pack; only this (main) process ever writes to ds,
        # so out-of-order completion is safe -- each block's position comes
        # from month_start_step, not from submission/completion order.
        while in_flight:
            completed, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in completed:
                year, month, start, packed = fut.result()
                year_buf.setdefault(year, {})[month] = packed
                done_months += 1
                if len(year_buf[year]) == 12:
                    _flush_year(year)
                _submit_next(pool)

    assert not year_buf, f"incomplete years never flushed: {sorted(year_buf)}"
    assert done_years == n_years_total, f"{done_years}/{n_years_total} years written"
    ds.close()

    # Only reaches here after every year was written and the file closed
    # cleanly -- rename .partial -> the real name the Fortran reader expects
    # now, not before, so an interrupted run never leaves something at
    # out_path that looks complete but isn't (see tmp_path comment above).
    final_size = tmp_path.stat().st_size
    expected_size_min = NCELL * total_steps * 2  # int16 data alone, file has a bit more (header, DTIME, lon/lat)
    if final_size < expected_size_min:
        raise AssertionError(f"{tmp_path} is {final_size} bytes, expected at least {expected_size_min}")
    tmp_path.rename(out_path)
    print(f"[{var}/{args.scenario}] done: {out_path} ({final_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
