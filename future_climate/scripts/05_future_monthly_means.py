#!/usr/bin/env python
"""Future CanESM5/TESSFA2 forcing: domain-mean MONTHLY TBOT and PRECTmms,
2015-2029.

Same source and variables as script 02, but only the years around the splice
and kept at monthly resolution. Each source file already is one month, so a
monthly mean is just the mean of the file.

2015-2023 overlaps the historical record; 2024-2029 is the first stretch that
actually gets used. Both are computed here and separated at plot time.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path("/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5")
OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/"
           "future_climate/outputs")
DIRFMT = "CanESM5_%s_r1i1p1f1_DBCCA_Daymet_TESSFA2"
Y0, Y1 = 2015, 2029      # defaults; override with --y0/--y1
STEP_SECONDS = 3 * 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True,
                    choices=["ssp119", "ssp245", "ssp370", "ssp585", "historical"])
    ap.add_argument("--y0", type=int, default=Y0)
    ap.add_argument("--y1", type=int, default=Y1)
    a = ap.parse_args()
    base = ROOT / (DIRFMT % a.scenario)
    assert base.is_dir(), base
    OUT.mkdir(parents=True, exist_ok=True)

    years = np.arange(a.y0, a.y1 + 1)
    nyr = years.size
    tbot = np.full((nyr, 12), np.nan)
    prec_rate = np.full((nyr, 12), np.nan)      # mm/s
    nstep = np.zeros((nyr, 12), dtype=np.int64)
    missing = []

    print(f"{a.scenario}: {base}  {a.y0}-{a.y1}", flush=True)
    for iy, y in enumerate(years):
        for m in range(1, 13):
            fp = base / "Precip3Hrly" / f"clmforc.4km.Prec.{y}-{m:02d}.nc"
            ft = base / "TPHWL3Hrly" / f"clmforc.4km.TPQWL.{y}-{m:02d}.nc"
            if not fp.exists() or not ft.exists():
                missing.append(f"{y}-{m:02d}")
                continue
            with xr.open_dataset(fp, decode_times=False) as d:
                v = d.PRECTmms.values
                prec_rate[iy, m - 1] = float(np.nanmean(v))
            with xr.open_dataset(ft, decode_times=False) as d:
                tbot[iy, m - 1] = float(np.nanmean(d.TBOT.values))
                nstep[iy, m - 1] = d.sizes["time"]
        print(f"  {y}: TBOT {np.nanmean(tbot[iy])-273.15:6.2f} degC  "
              f"annual PRECT "
              f"{np.nansum(prec_rate[iy]*nstep[iy]*STEP_SECONDS):7.1f} mm", flush=True)

    prec_mm = prec_rate * nstep * STEP_SECONDS      # mm per month

    out = OUT / f"future_monthly_means_{a.scenario}.npz"
    np.savez(out, years=years, months=np.arange(1, 13), tbot_K=tbot,
             prect_mm_s=prec_rate, prect_mm_mon=prec_mm, nstep=nstep,
             missing=np.array(missing, dtype=object))
    print(f"\nwrote {out}")
    print(f"missing months: {len(missing)}" + (f" {missing[:12]}" if missing else ""))


if __name__ == "__main__":
    main()
