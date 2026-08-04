#!/usr/bin/env python
"""Historical TESSFA2 forcing: domain-mean MONTHLY TBOT and PRECTmms, 2010-2023.

Same source and layout as script 01, binned by calendar month instead of year.
Monthly resolution is the better splice diagnostic: two records can agree on
the annual mean while disagreeing on the seasonal cycle, and only the monthly
view separates those.

The cpl_bypass DTIME axis is 3-hourly NOLEAP, so every year is 2920 steps and
month m starts at a fixed offset within the year -- no calendar arithmetic
beyond the fixed noleap month lengths.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from tessfa_mask import assert_physical, valid_cell_mask

HIST = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
            "Daymet_ERA5_TESSFA2/cpl_bypass_full")
OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/"
           "future_climate/outputs")
STEM = "Daymet_ERA5_TESSFA.4km_%s_1980-2023_z01.nc"

YEAR0_FILE = 1980
Y0, Y1 = 2010, 2023          # defaults; override with --y0/--y1
STEPS_PER_DAY = 8
MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])  # noleap
SPY = int(MONTH_DAYS.sum()) * STEPS_PER_DAY          # 2920
MSTART = np.concatenate([[0], np.cumsum(MONTH_DAYS)]) * STEPS_PER_DAY
NBLOCK = 4000


def monthly_means(var: str, valid: np.ndarray) -> np.ndarray:
    """-> (nyear, 12) domain-mean monthly value, land cells only."""
    ds = xr.open_dataset(HIST / (STEM % var), decode_times=False)
    da = ds[var]
    n = ds.sizes["n"]
    nyr = Y1 - Y0 + 1
    t0 = (Y0 - YEAR0_FILE) * SPY
    t1 = (Y1 + 1 - YEAR0_FILE) * SPY
    assert t1 <= ds.sizes["DTIME"]
    print(f"  {var}: n={n} time[{t0}:{t1}] ({t1-t0} steps, {nyr} yr)", flush=True)

    acc = np.zeros((nyr, 12)); cnt = np.zeros((nyr, 12), dtype=np.int64)
    for s in range(0, n, NBLOCK):
        e = min(s + NBLOCK, n)
        vb = valid[s:e]
        if not vb.any():
            continue
        blk = da.isel(n=slice(s, e), DTIME=slice(t0, t1)).values.astype(np.float64)
        blk = blk[vb]
        assert_physical(var, blk)
        blk = blk.reshape(vb.sum(), nyr, SPY)
        for m in range(12):
            seg = blk[:, :, MSTART[m]:MSTART[m + 1]]
            acc[:, m] += np.nansum(seg, axis=(0, 2))
            cnt[:, m] += np.sum(np.isfinite(seg), axis=(0, 2))
        if (s // NBLOCK) % 15 == 0:
            print(f"    n {s}/{n}", flush=True)
    ds.close()
    return acc / cnt


def main():
    global Y0, Y1
    ap = argparse.ArgumentParser()
    ap.add_argument("--y0", type=int, default=Y0)
    ap.add_argument("--y1", type=int, default=Y1)
    ap.add_argument("--out", default="hist_monthly_means.npz")
    a = ap.parse_args()
    Y0, Y1 = a.y0, a.y1
    OUT.mkdir(parents=True, exist_ok=True)
    years = np.arange(Y0, Y1 + 1)
    print(f"historical monthly {Y0}-{Y1}")
    valid = valid_cell_mask()
    print(f"land mask: {valid.sum()} valid cells of {valid.size}")
    tbot = monthly_means("TBOT", valid)                           # K
    prec = monthly_means("PRECTmms", valid)                       # mm/s
    # monthly total in mm, using this calendar's month lengths
    prec_mm = prec * MONTH_DAYS[None, :] * 86400.0

    np.savez(OUT / a.out, years=years, months=np.arange(1, 13),
             tbot_K=tbot, prect_mm_s=prec, prect_mm_mon=prec_mm,
             month_days=MONTH_DAYS)
    print(f"\nwrote {OUT/a.out}\n")
    print("climatological seasonal cycle %d-%d:" % (Y0, Y1))
    print(f"{'month':<7}{'TBOT [degC]':>13}{'PRECT [mm/mon]':>16}")
    for m in range(12):
        print(f"{m+1:<7}{tbot[:, m].mean()-273.15:>13.2f}{prec_mm[:, m].mean():>16.1f}")


if __name__ == "__main__":
    main()
