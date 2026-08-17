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
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import netCDF4 as nc
import numpy as np

TESSFA2_ROOT = Path("/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5")
ZONE_MAPPINGS = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
                      "Daymet_ERA5_TESSFA2/zone_mappings.txt")
OUT_ROOT = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
                 "Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim")

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
    with open(ZONE_MAPPINGS) as f:
        for i, line in enumerate(f):
            parts = line.split()
            lon[i] = float(parts[0])
            lat[i] = float(parts[1])
    return lon, lat


def pack_month(raw_lat_lon: np.ndarray, add_off: float, scale: float, raw_sentinel: int) -> np.ndarray:
    """(ntime, NLAT, NLON) float, NaN over ocean -> (ntime, NCELL) int16, n-ordered."""
    ntime = raw_lat_lon.shape[0]
    # (time, lat, lon) -> (time, lon, lat): flatten() on the last two axes then
    # gives n = ilon*NLAT + ilat, matching zone_mappings.txt row order.
    arr = np.transpose(raw_lat_lon, (0, 2, 1)).reshape(ntime, NCELL)
    valid = np.isfinite(arr)
    packed = np.empty((ntime, NCELL), dtype=np.int16)
    scaled = np.round((arr - add_off) / scale)
    scaled = np.clip(scaled, -32767, 32767)  # keep -32768 reserved for the PRECTmms sentinel itself
    packed[:] = np.where(valid, scaled, raw_sentinel).astype(np.int16)
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
        raw = ds.variables[srcvar][:].astype(np.float64)  # (time, lat, lon), _FillValue -> masked
        raw = np.ma.filled(raw, np.nan)
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

    print(f"[{var}/{args.scenario}] add_offset={add_off} scale_factor={scale} "
          f"ocean_sentinel_raw={raw_sentinel}")
    print(f"[{var}/{args.scenario}] writing {out_path}")

    lon, lat = load_grid_order()
    n_years = Y1 - Y0 + 1
    total_steps = STEPS_PER_YEAR + n_years * STEPS_PER_YEAR  # dummy year + real years

    ds = nc.Dataset(out_path, "w", format="NETCDF4")
    ds.createDimension("n", NCELL)
    ds.createDimension("DTIME", total_steps)
    v_dtime = ds.createVariable("DTIME", "f8", ("DTIME",))
    v_dtime.long_name = "Day of Year"
    v_dtime.units = f"Days since {DUMMY_YEAR}-01-01 00:00"
    v_lon = ds.createVariable("LONGXY", "f4", ("n",))
    v_lat = ds.createVariable("LATIXY", "f4", ("n",))
    v_lon[:] = lon
    v_lat[:] = lat
    # No compression: writing this variable was measured CPU-bound at complevel=4
    # (single core pinned near 100% doing zlib work, not I/O-bound), and the
    # uncompressed storage budget (~2.9TiB for all 7 vars x 4 scenarios) fits
    # comfortably within the ~46TB free on /projects/hpcl-cli185 -- see
    # README_cpl_bypass_future.md Sec.8. Chunking is kept (one chunk per year)
    # since writes still happen in DTIME-axis slices.
    v_var = ds.createVariable(var, "i2", ("n", "DTIME"),
                               chunksizes=(NCELL, min(STEPS_PER_YEAR, total_steps)))
    v_var.add_offset = np.float32(add_off)
    v_var.scale_factor = np.float32(scale)

    ds.title = "SEUS TESSFA2 future (2024-2100) CPL_BYPASS meteorological forcing"
    ds.source = (f"CanESM5 {args.scenario} r1i1p1f1, DBCCA bias-corrected/downscaled "
                 f"against Daymet, TESSFA2 (SEUS) 4km grid")
    ds.comment = (
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
    )
    ds.calendar_note = ("Source CanESM5-DBCCA-TESSFA2 data use a standard (Gregorian, "
                         "leap-year) calendar; Feb 29 was removed from every leap year "
                         "to match the model's CALENDAR=NO_LEAP (fixed 365 days/year, "
                         "2920 3-hourly steps/year).")
    ds.ocean_sentinel_raw = np.int16(raw_sentinel)
    ds.ocean_sentinel_note = ("Raw packed value used for ocean/invalid gridcells, taken "
                               "unchanged from the historical Daymet_ERA5_TESSFA.4km_"
                               f"{var}_1980-2023_z01.nc file so decoded sentinel behavior "
                               "is identical between the historical and future forcing.")

    # DTIME is pure arithmetic (doesn't depend on the source data at all) --
    # write it in one shot instead of one nc call per step.
    v_dtime[:] = (np.arange(1, total_steps + 1) / STEPS_PER_DAY
                  - 0.5 * (RES_HOURS / 24.0))

    # dummy year: sentinel everywhere
    v_var[:, 0:STEPS_PER_YEAR] = np.full((NCELL, STEPS_PER_YEAR), raw_sentinel, dtype=np.int16)

    nworkers = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 4))
    tasks = [(y, m) for y in range(Y0, Y1 + 1) for m in range(1, 13)]
    print(f"[{var}/{args.scenario}] {len(tasks)} months to process with {nworkers} worker processes")

    done = 0
    with ProcessPoolExecutor(max_workers=nworkers) as pool:
        futures = [pool.submit(process_month, args.scenario, var, y, m, add_off, scale, raw_sentinel)
                   for y, m in tasks]
        # Workers only read+pack; only this (main) process ever writes to ds,
        # so out-of-order completion is safe -- each block's position comes
        # from month_start_step, not from submission/completion order.
        for fut in as_completed(futures):
            year, month, start, packed = fut.result()
            ntime = packed.shape[0]
            v_var[:, start:start + ntime] = packed.T
            done += 1
            if done % 12 == 0 or done == len(tasks):
                print(f"[{var}/{args.scenario}] {done}/{len(tasks)} months written (last: {year}-{month:02d})")

    ds.close()
    print(f"[{var}/{args.scenario}] done: {out_path}")


if __name__ == "__main__":
    main()
