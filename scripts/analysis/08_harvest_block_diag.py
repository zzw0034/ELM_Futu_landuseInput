#!/usr/bin/env python
"""Why does cumulative HARVEST_* show 0.25-degree blocks?

The harvest downscaling (02_harmonize_seus.py stage B, verbatim from s4_2) is

    frac_i = F_c * w_i * sum_c(area) / sum_c(w*area)      w = tree_share * natveg

so within one LUH2 coarse cell c the output is F_c (a constant) times the
normalized fine-scale weight. Two distinct things can make a block visible:

  1. F_c differs from its neighbours   -> block edge, unavoidable at 0.25 deg
  2. sum_c(w*area) == 0                -> `valid` is False for the whole block
                                          and frac_i stays 0 EVERYWHERE in it,
                                          even when F_c > 0. That silently drops
                                          harvest area.

Case 2 is the one worth finding: it is a real loss of forcing, not resolution.
This script separates them by comparing, per coarse cell,

    the downscaled cumulative harvest we produced   (from the compare npz)
    the LUH2 source cumulative harvest              (from the transitions file)
    our harmonized tree share and natveg            (the weight)

and reports how much LUH2 harvest area falls into cells we could not place.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
LUH_DIR = Path("/projects/hpcl-cli185/proj-shared/zw5/luh")
NPZ = ROOT / "outputs" / "interim" / "scenario_compare_final.npz"
PROC = ROOT / "outputs" / "processed"
STEM = "landuse.timeseries_SEUS_1_24deg_nlcd2elm_%s_simyr2024-2100.nc"

SCEN = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]
LUH_FILE = {"SSP1_RCP19": "ssp1rcp19_transitions.nc",
            "SSP2_RCP45": "ssp2rcp45_transitions.nc",
            "SSP3_RCP70": "ssp3rcp70_transitions.nc",
            "SSP5_RCP85": "ssp5rcp85_transitions.nc"}
HVARS = ["primf_harv", "primn_harv", "secmf_harv", "secyf_harv", "secnf_harv"]
LUH_YEAR0, LUH_LAST = 2015, 2099
TREE = [1, 2, 3, 4, 5, 6, 7, 8]
NB = 6  # fine cells per 0.25 deg coarse cell


def block_sum(a, nb=NB):
    """(ny,nx) -> (ny/nb, nx/nb) sum over nb x nb blocks."""
    ny, nx = a.shape
    return a.reshape(ny // nb, nb, nx // nb, nb).sum(axis=(1, 3))


def main():
    z = {k: np.asarray(v) for k, v in np.load(NPZ, allow_pickle=True).items()}
    lat, lon = z["lat"], z["lon"]
    mask, natveg_km2, years = z["mask"], z["natveg_km2"], z["years"]
    ny, nx = lat.size, lon.size
    assert ny % NB == 0 and nx % NB == 0

    # fine cell area (km2 of land in the natveg column is natveg_km2; the
    # downscaler used full cell area, so recover it the same way)
    d0 = xr.open_dataset(PROC / (STEM % SCEN[0]), decode_times=False)
    area_hr = np.nan_to_num(d0.AREA.values.astype(np.float64))
    d0.close()

    # coarse-block geometry: the fine grid starts on a 0.25 deg edge
    blat = lat.reshape(-1, NB).mean(axis=1)
    blon = lon.reshape(-1, NB).mean(axis=1)
    print(f"fine {ny}x{nx}  ->  coarse blocks {blat.size}x{blon.size} "
          f"({NB}x{NB} fine cells each, 0.25 deg)")
    print(f"block lat {blat[0]:.4f}..{blat[-1]:.4f}  lon {blon[0]:.4f}..{blon[-1]:.4f}")

    natveg_blk = block_sum(natveg_km2)          # km2 of natveg per coarse block
    nveg_cells = block_sum(mask.astype(np.float64))

    print("\n" + "=" * 92)
    print("Per-scenario accounting of the 0.25 deg blocks")
    print("=" * 92)

    for s in SCEN:
        hcum = z[f"hcum_{s}"]                    # fine, sum over years of sum of 5 vars
        # our placed harvest AREA per block (LUT units are fraction of veg unit)
        placed_km2 = block_sum(hcum * natveg_km2)

        # LUH2 source: same year window and the same k=-1 convention as stage B
        luh = xr.open_dataset(LUH_DIR / LUH_FILE[s], decode_times=False)
        clat, clon = luh.lat.values, luh.lon.values
        # LUH2 lat descends; find the SEUS window
        i0 = int(np.argmin(np.abs(clat - blat[-1])))
        i1 = int(np.argmin(np.abs(clat - blat[0])))
        j0 = int(np.argmin(np.abs(clon - blon[0])))
        j1 = int(np.argmin(np.abs(clon - blon[-1])))
        assert i1 - i0 + 1 == blat.size and j1 - j0 + 1 == blon.size, \
            f"window mismatch {i1-i0+1}x{j1-j0+1} vs {blat.size}x{blon.size}"

        src = np.zeros((blat.size, blon.size))
        for yr in years:
            hidx = min(int(yr), LUH_LAST) - LUH_YEAR0
            for v in HVARS:
                a = luh[v].isel(time=hidx, lat=slice(i0, i1 + 1),
                                lon=slice(j0, j1 + 1)).values.astype(np.float64)
                src += np.nan_to_num(a)
        src = src[::-1]                          # LUH2 lat desc -> our lat asc
        luh.close()

        # LUH2 fractions are of the whole grid cell -> area using the fine-cell
        # area that actually falls inside each block (what the downscaler used)
        area_blk = block_sum(area_hr)
        src_km2 = src * area_blk

        has_src = src_km2 > 0
        placed_none = placed_km2 <= 0
        dropped = has_src & placed_none & (natveg_blk > 0)
        no_natveg = has_src & (natveg_blk <= 0)

        print(f"\n--- {s} ---")
        print(f"  coarse blocks total                        {src.size}")
        print(f"  blocks with LUH2 harvest > 0               {has_src.sum()}")
        print(f"  ... of which we placed nothing             {(has_src & placed_none).sum()}")
        print(f"        because the block has no natveg      {no_natveg.sum()}")
        print(f"        DESPITE the block having natveg      {dropped.sum()}")
        print(f"  LUH2 harvest area in domain      {src_km2.sum()/1e4:>10.3f} Mha")
        print(f"  ... we placed                    {placed_km2.sum()/1e4:>10.3f} Mha"
              f"   ({100*placed_km2.sum()/src_km2.sum():.2f}%)")
        print(f"  ... unplaced, block has natveg   {src_km2[dropped].sum()/1e4:>10.3f} Mha")
        print(f"  ... unplaced, block has no natveg{src_km2[no_natveg].sum()/1e4:>10.3f} Mha")

        if dropped.any():
            ii, jj = np.where(dropped)
            order = np.argsort(-src_km2[dropped])
            print(f"  largest blocks with source harvest but nothing placed:")
            print(f"    {'lat':>8} {'lon':>9} {'LUH2 Mha':>9} {'natveg km2':>11} "
                  f"{'veg cells':>9}")
            for k in order[:8]:
                i, j = ii[k], jj[k]
                print(f"    {blat[i]:>8.3f} {blon[j]:>9.3f} "
                      f"{src_km2[i, j]/1e4:>9.4f} {natveg_blk[i, j]:>11.1f} "
                      f"{nveg_cells[i, j]:>9.0f}")

        # how blocky is the result? compare within-block spread to between-block
        if s == "SSP2_RCP45":
            ok = (natveg_blk > 0) & (placed_km2 > 0)
            print(f"\n  block-level structure ({ok.sum()} populated blocks):")
            print(f"    between-block CV of placed harvest area  "
                  f"{placed_km2[ok].std()/placed_km2[ok].mean():.3f}")
            src_ok = src[ok]
            print(f"    LUH2 source fraction  min {src_ok.min():.4f}  "
                  f"med {np.median(src_ok):.4f}  max {src_ok.max():.4f}")
            print(f"    -> the visible squares are F_c, constant inside each "
                  f"0.25 deg cell by construction")

    # tree share: is the weight ever zero where natveg is not?
    print("\n" + "=" * 92)
    print("Is the weight (tree_share * natveg) zero anywhere with natveg > 0?")
    print("=" * 92)
    for s in SCEN[:1]:
        ds = xr.open_dataset(PROC / (STEM % s), decode_times=False)
        for t, lab in ((0, str(years[0])), (len(years) - 1, str(years[-1]))):
            p = np.nan_to_num(ds.PCT_NAT_PFT.isel(time=t).values.astype(np.float64))
            tree = p[TREE].sum(axis=0)
            treeless = mask & (tree <= 0)
            print(f"  {s} {lab}: natveg cells with ZERO tree share  "
                  f"{treeless.sum()} / {mask.sum()}  "
                  f"({100*treeless.sum()/mask.sum():.2f}%)")
            tb = block_sum((tree > 0).astype(np.float64))
            print(f"      coarse blocks with natveg but no tree at all: "
                  f"{((tb <= 0) & (natveg_blk > 0)).sum()}")
        ds.close()


if __name__ == "__main__":
    main()
