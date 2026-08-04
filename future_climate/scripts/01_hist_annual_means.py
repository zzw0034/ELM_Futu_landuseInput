#!/usr/bin/env python
"""Historical TESSFA2 forcing: domain-mean annual TBOT and PRECTmms, 2000-2023.

Source is the cpl_bypass layout:

    Daymet_ERA5_TESSFA.4km_<VAR>_1980-2023_z01.nc
    VAR(n=225625, DTIME=128480)   int16 + scale_factor/add_offset

`n` is the flattened TESSFA2 grid, lat-fastest (625 lon x 361 lat), and its
LONGXY/LATIXY match the future files' lat/lon exactly -- verified before
writing this. DTIME is 3-hourly on a NOLEAP calendar: 128480 = 44 yr x 365 d
x 8, so year y starts at (y-1980)*2920.

Layout is (n, DTIME) with time fastest, so a block of whole rows is a
contiguous read; we stream over n in blocks and split by year in memory.

Units: PRECTmms is mm H2O/s (same as the future files); reported here as
mm/yr using this calendar's 365 days. TBOT is K, reported as degC.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from tessfa_mask import assert_physical, valid_cell_mask

HIST = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
            "Daymet_ERA5_TESSFA2/cpl_bypass_full")
OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/"
           "future_climate/outputs")
STEM = "Daymet_ERA5_TESSFA.4km_%s_1980-2023_z01.nc"

YEAR0_FILE = 1980           # first year in the file
Y0, Y1 = 2000, 2023         # window we want (inclusive)
STEPS_PER_DAY = 8
DAYS_PER_YEAR = 365         # noleap
SPY = DAYS_PER_YEAR * STEPS_PER_DAY   # 2920 steps per year
NBLOCK = 4000               # gridcells per read block


def annual_means(var: str, valid: np.ndarray) -> np.ndarray:
    """-> (nyear,) domain-mean annual value of `var` over Y0..Y1.

    `valid` masks the cells outside the TESSFA2 land mask, which carry an int
    sentinel that decodes to a finite value (see tessfa_mask).
    """
    f = HIST / (STEM % var)
    ds = xr.open_dataset(f, decode_times=False)
    da = ds[var]
    n = ds.sizes["n"]
    nyr = Y1 - Y0 + 1
    t0 = (Y0 - YEAR0_FILE) * SPY
    t1 = (Y1 + 1 - YEAR0_FILE) * SPY
    assert t1 <= ds.sizes["DTIME"], (t1, ds.sizes["DTIME"])
    print(f"  {var}: n={n} time[{t0}:{t1}] ({t1-t0} steps, {nyr} yr)", flush=True)

    acc = np.zeros(nyr, dtype=np.float64)   # sum over cells and steps
    cnt = np.zeros(nyr, dtype=np.int64)
    nbad = 0
    for s in range(0, n, NBLOCK):
        e = min(s + NBLOCK, n)
        vb = valid[s:e]
        if not vb.any():
            continue
        blk = da.isel(n=slice(s, e), DTIME=slice(t0, t1)).values.astype(np.float64)
        blk = blk[vb]
        assert_physical(var, blk)
        bad = ~np.isfinite(blk)
        if bad.any():
            nbad += int(bad.sum())
            blk[bad] = np.nan
        blk = blk.reshape(vb.sum(), nyr, SPY)
        acc += np.nansum(blk, axis=(0, 2))
        cnt += np.sum(np.isfinite(blk), axis=(0, 2))
        if (s // NBLOCK) % 10 == 0:
            print(f"    n {s}/{n}", flush=True)
    ds.close()
    if nbad:
        print(f"    WARNING {var}: {nbad} non-finite values ignored")
    return acc / cnt


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    years = np.arange(Y0, Y1 + 1)
    print(f"historical TESSFA2 {Y0}-{Y1} from {HIST}")
    valid = valid_cell_mask()
    print(f"land mask: {valid.sum()} valid cells of {valid.size}")

    tbot = annual_means("TBOT", valid)              # K
    prec = annual_means("PRECTmms", valid)          # mm/s
    prec_mm_yr = prec * DAYS_PER_YEAR * 86400.0     # mm/yr

    np.savez(OUT / "hist_annual_means.npz", years=years, tbot_K=tbot,
             prect_mm_s=prec, prect_mm_yr=prec_mm_yr)
    print(f"\nwrote {OUT/'hist_annual_means.npz'}\n")
    print(f"{'year':<6}{'TBOT [degC]':>13}{'PRECT [mm/yr]':>16}")
    for i, y in enumerate(years):
        print(f"{y:<6}{tbot[i]-273.15:>13.3f}{prec_mm_yr[i]:>16.1f}")
    print(f"\n{Y0}-{Y1} mean: TBOT {np.mean(tbot)-273.15:.3f} degC   "
          f"PRECT {np.mean(prec_mm_yr):.1f} mm/yr")


if __name__ == "__main__":
    main()
