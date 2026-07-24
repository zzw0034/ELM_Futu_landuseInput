#!/usr/bin/env python
"""Where do the two products' PCT_NATVEG differ, cell by cell?

NLCD-derived  : elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc  (PCT_NATVEG float64)
Chen2022 SSP1 : chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc

Both on the identical 1/24 deg grid (601 x 1441). Overlap years: 2015, 2020.
Reports the distribution of (Chen - NLCD) PCT_NATVEG over the CONUS mask and
maps it. PCT_NATVEG is % of the whole cell in both files, so the difference is
directly in percentage-points of cell.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

NL = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
          "s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc")
CH = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/"
          "processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
EXTENT = (-125.0, -65.0, 25.0, 50.0)
R = 6371.0


def cell_area_km2(lat, lon):
    dlat = float(np.mean(np.diff(lat))); dlon = float(np.mean(np.diff(lon)))
    ln = np.radians(lat + dlat/2); ls = np.radians(lat - dlat/2)
    band = R**2 * np.radians(dlon) * (np.sin(ln) - np.sin(ls))
    return np.repeat(band[:, None], lon.size, axis=1)


def main():
    nl = xr.open_dataset(NL)
    ch = xr.open_dataset(CH)
    lat = nl.lat.values; lon = nl.lon.values
    assert np.allclose(lat, ch.lat.values) and np.allclose(lon, ch.lon.values), "grid mismatch"
    area = cell_area_km2(lat, lon)

    nl_yrs = nl.time.dt.year.values
    ch_yrs = ch.time.values.astype(int)

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    # CONUS mask from NLCD 2015 (same definition as script 30)
    i15 = int(np.where(nl_yrs == 2015)[0][0])
    nv15_nl = nl.PCT_NATVEG.isel(time=i15).values.astype(np.float64)
    ur15 = nl.PCT_URBAN.isel(time=i15).values.astype(np.float64).sum(axis=0)
    conus = (nv15_nl + ur15) > 0.0
    ncell = int(conus.sum())

    emit("="*72)
    emit("PCT_NATVEG difference  Chen(SSP1-RCP1.9) - NLCD   [percentage-points of cell]")
    emit("="*72)
    emit(f"CONUS mask (NLCD natveg+urban>0 @2015): {ncell:,} cells, "
         f"{area[conus].sum():,.0f} km^2")
    emit("")

    diffs = {}
    for yr in (2015, 2020):
        inl = int(np.where(nl_yrs == yr)[0][0])
        ich = int(np.where(ch_yrs == yr)[0][0])
        a = nl.PCT_NATVEG.isel(time=inl).values.astype(np.float64)
        b = np.nan_to_num(ch.PCT_NATVEG.isel(time=ich).values.astype(np.float64))
        d = np.where(conus, b - a, np.nan)
        diffs[yr] = (a, b, d)

        dd = d[conus]
        adiff = np.abs(dd)
        w = area[conus]
        emit(f"----- {yr} -----")
        emit(f"  area-weighted mean natveg:  NLCD {np.average(a[conus], weights=w):6.2f}%   "
             f"Chen {np.average(b[conus], weights=w):6.2f}%   "
             f"(Chen-NLCD {np.average(dd, weights=w):+5.2f} pp)")
        emit(f"  signed diff  mean {dd.mean():+.3f}  median {np.median(dd):+.3f}  "
             f"RMS {np.sqrt((dd**2).mean()):.3f}  min {dd.min():+.2f}  max {dd.max():+.2f}")
        emit(f"  Chen>NLCD: {int((dd>0).sum()):>8,} cells ({(dd>0).mean()*100:4.1f}%)   "
             f"Chen<NLCD: {int((dd<0).sum()):>8,} ({(dd<0).mean()*100:4.1f}%)   "
             f"equal: {int((dd==0).sum()):>8,} ({(dd==0).mean()*100:4.1f}%)")
        emit("  |diff| threshold      cells   %ofCONUS   natveg-area involved (min-of-two) km^2")
        for thr in (0.0, 0.5, 1, 2, 5, 10, 25, 50):
            m = adiff > thr
            # area where they disagree, counted as the natveg area at stake
            involved = (np.minimum(a[conus], b[conus])/100.0 * w)[m].sum() if m.any() else 0.0
            emit(f"    > {thr:>5.1f} pp        {int(m.sum()):>9,}   {m.mean()*100:6.2f}%     {involved:>14,.0f}")
        # percentiles of |diff|
        pcs = np.percentile(adiff, [50, 75, 90, 95, 99, 99.9])
        emit("  |diff| percentiles  p50 p75 p90 p95 p99 p99.9: "
             + "  ".join(f"{v:.2f}" for v in pcs))
        emit("")

    # ---- figure: NLCD | Chen | diff, for 2015 and 2020 ----
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), layout="constrained")
    dmax = 40
    for r, yr in enumerate((2015, 2020)):
        a, b, d = diffs[yr]
        am = np.where(conus, a, np.nan); bm = np.where(conus, b, np.nan)
        for c, (arr, ttl, cmap, norm) in enumerate([
            (am, f"NLCD PCT_NATVEG {yr}", "YlGn", None),
            (bm, f"Chen SSP1 PCT_NATVEG {yr}", "YlGn", None),
            (d,  f"Chen - NLCD {yr} [pp]", "RdBu_r",
             TwoSlopeNorm(vmin=-dmax, vcenter=0, vmax=dmax)),
        ]):
            ax = axes[r, c]
            kw = dict(origin="lower", extent=EXTENT, interpolation="nearest")
            if norm is not None:
                im = ax.imshow(arr, cmap=cmap, norm=norm, **kw)
            else:
                im = ax.imshow(arr, cmap=cmap, vmin=0, vmax=100, **kw)
            ax.set_title(ttl, fontsize=10); ax.set_xticks([]); ax.set_yticks([])
            fig.colorbar(im, ax=ax, shrink=0.7)
    fig.suptitle("PCT_NATVEG: NLCD-derived vs Chen2022 SSP1-RCP1.9, overlap years", fontsize=13)
    figp = OUTDIR / "figures" / "fig_natveg_diff_nlcd_vs_chen_ssp1.png"
    figp.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figp, dpi=130); plt.close(fig)
    emit(f"wrote {figp}")

    txtp = OUTDIR / "interim" / "natveg_diff_nlcd_vs_chen_ssp1.txt"
    txtp.parent.mkdir(parents=True, exist_ok=True)
    txtp.write_text("\n".join(lines) + "\n")
    print(f"wrote {txtp}")

    # also dump the 2020 diff array for any follow-up
    np.savez_compressed(OUTDIR / "interim" / "natveg_diff_ssp1.npz",
                        conus=conus, area=area, lat=lat, lon=lon,
                        diff_2015=diffs[2015][2].astype(np.float32),
                        diff_2020=diffs[2020][2].astype(np.float32))
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
