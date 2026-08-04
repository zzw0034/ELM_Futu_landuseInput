#!/usr/bin/env python
"""Future CanESM5/TESSFA2 forcing: domain-mean annual TBOT and PRECTmms.

    <root>/CanESM5_<ssp>_r1i1p1f1_DBCCA_Daymet_TESSFA2/
        Precip3Hrly/clmforc.4km.Prec.YYYY-MM.nc     PRECTmms (time,lat,lon) mm/s
        TPHWL3Hrly/clmforc.4km.TPQWL.YYYY-MM.nc     TBOT     (time,lat,lon) K

Deliberately uses the SAME two variables the historical cpl_bypass files hold,
3-hourly in both cases. The cheaper DBCCA_dy/ daily files would have meant
(tmax+tmin)/2 against a true 3-hourly mean, and that methodological offset is
exactly what a splice check would misread as a jump.

Data start in 2015, so 2015-2023 overlaps the historical record. That overlap
is a far stronger continuity test than the single 2023->2024 step, so it is
computed here and kept separate in the output.

Unlike the historical file, these carry leap days (Feb 2024 has 232 steps),
so annual precipitation uses each year's actual step count.
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
Y0, Y1 = 2015, 2100
STEP_HOURS = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True,
                    choices=["ssp119", "ssp245", "ssp370", "ssp585"])
    a = ap.parse_args()
    base = ROOT / (DIRFMT % a.scenario)
    assert base.is_dir(), base
    OUT.mkdir(parents=True, exist_ok=True)

    years = np.arange(Y0, Y1 + 1)
    nyr = years.size
    tbot = np.full(nyr, np.nan)
    prec_rate = np.full(nyr, np.nan)     # mm/s, time+space mean
    nsteps = np.zeros(nyr, dtype=np.int64)
    missing = []

    print(f"{a.scenario}: {base}", flush=True)
    for iy, y in enumerate(years):
        t_sum = p_sum = 0.0
        t_n = p_n = 0
        for m in range(1, 13):
            fp = base / "Precip3Hrly" / f"clmforc.4km.Prec.{y}-{m:02d}.nc"
            ft = base / "TPHWL3Hrly" / f"clmforc.4km.TPQWL.{y}-{m:02d}.nc"
            if not fp.exists() or not ft.exists():
                missing.append(f"{y}-{m:02d}")
                continue
            with xr.open_dataset(fp, decode_times=False) as d:
                v = d.PRECTmms.values
                p_sum += float(np.nansum(v)); p_n += int(np.isfinite(v).sum())
            with xr.open_dataset(ft, decode_times=False) as d:
                v = d.TBOT.values
                t_sum += float(np.nansum(v)); t_n += int(np.isfinite(v).sum())
                nsteps[iy] += d.sizes["time"]
        if t_n:
            tbot[iy] = t_sum / t_n
        if p_n:
            prec_rate[iy] = p_sum / p_n
        if y % 10 == 0 or y <= 2025:
            print(f"  {y}: TBOT {tbot[iy]-273.15:7.3f} degC   "
                  f"PRECT {prec_rate[iy]*nsteps[iy]*STEP_HOURS*3600:8.1f} mm/yr   "
                  f"({nsteps[iy]} steps)", flush=True)

    # annual precip total uses each year's own step count (leap years included)
    prec_mm_yr = prec_rate * nsteps * STEP_HOURS * 3600.0

    out = OUT / f"future_annual_means_{a.scenario}.npz"
    np.savez(out, years=years, tbot_K=tbot, prect_mm_s=prec_rate,
             prect_mm_yr=prec_mm_yr, nsteps=nsteps,
             missing=np.array(missing, dtype=object))
    print(f"\nwrote {out}")
    if missing:
        print(f"MISSING {len(missing)} months: {missing[:12]}"
              f"{' ...' if len(missing) > 12 else ''}")
    else:
        print("no missing months")
    print(f"\n2015-2023 mean (overlap): TBOT {np.nanmean(tbot[:9])-273.15:.3f} degC   "
          f"PRECT {np.nanmean(prec_mm_yr[:9]):.1f} mm/yr")
    print(f"2024 (first future year):  TBOT {tbot[9]-273.15:.3f} degC   "
          f"PRECT {prec_mm_yr[9]:.1f} mm/yr")


if __name__ == "__main__":
    main()
