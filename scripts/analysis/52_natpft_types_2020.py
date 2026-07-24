#!/usr/bin/env python
"""Which PCT_NAT_PFT *types* differ between NLCD and Chen, cell by cell, in 2020?

Two questions:
  (1) structural: which of the 17 PFTs does each product populate at all in
      CONUS? (present = nonzero somewhere)  -> the "types" difference.
  (2) spatial: per PFT, where and by how much do they differ?

Quantity for the per-cell/per-PFT difference is p(j) = the PFT's share of the
WHOLE cell = PCT_NATVEG/100 * PCT_NAT_PFT(j)  [in % of cell], which is
commensurable between the two products (shared denominator = the cell), unlike
PCT_NAT_PFT alone (denominator = each product's own natveg). Area [km^2] =
cell_area * p(j)/100.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src")
from elm_landuse.chen_classes import ELM_PFT_NAMES  # noqa: E402

NL = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
          "s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc")
CH = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/"
          "processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
EXTENT = (-125.0, -65.0, 25.0, 50.0)
R = 6371.0
YEAR = 2020
PRESENT_FRAC = 0.5   # a PFT counts as "present" in a cell if its p(j) > this % of cell
NPFT = 17

SHORT = {i: n.replace("_tree", " tree").replace("_grass", " grass").replace("_shrub", " shrub")
         for i, n in enumerate(ELM_PFT_NAMES)}


def cell_area_km2(lat, lon):
    dlat = float(np.mean(np.diff(lat))); dlon = float(np.mean(np.diff(lon)))
    ln = np.radians(lat + dlat/2); ls = np.radians(lat - dlat/2)
    band = R**2 * np.radians(dlon) * (np.sin(ln) - np.sin(ls))
    return np.repeat(band[:, None], lon.size, axis=1)


def main():
    nl = xr.open_dataset(NL); ch = xr.open_dataset(CH)
    lat = nl.lat.values; lon = nl.lon.values
    area = cell_area_km2(lat, lon)
    nl_yrs = nl.time.dt.year.values; ch_yrs = ch.time.values.astype(int)
    inl = int(np.where(nl_yrs == YEAR)[0][0]); ich = int(np.where(ch_yrs == YEAR)[0][0])

    nv_nl = np.nan_to_num(nl.PCT_NATVEG.isel(time=inl).values.astype(np.float64))
    nv_ch = np.nan_to_num(ch.PCT_NATVEG.isel(time=ich).values.astype(np.float64))
    pf_nl = np.nan_to_num(nl.PCT_NAT_PFT.isel(time=inl).values.astype(np.float64))
    pf_ch = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=ich).values.astype(np.float64))
    ur = nl.PCT_URBAN.isel(time=int(np.where(nl_yrs == 2015)[0][0])).values.sum(axis=0)
    conus = (np.nan_to_num(nl.PCT_NATVEG.isel(time=int(np.where(nl_yrs==2015)[0][0])).values) + ur) > 0.0

    # p(j) = PFT share of whole cell [%]
    p_nl = pf_nl * nv_nl[None] / 100.0
    p_ch = pf_ch * nv_ch[None] / 100.0

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    emit("="*94)
    emit(f"PCT_NAT_PFT types: NLCD vs Chen(SSP1-RCP1.9), {YEAR}, CONUS")
    emit(f"  p(j) = PCT_NATVEG/100 * PCT_NAT_PFT(j)  [% of cell];  area = cell_area * p(j)/100")
    emit(f"  'present' in a cell if p(j) > {PRESENT_FRAC}% of the cell")
    emit("="*94)
    emit(f"CONUS: {int(conus.sum()):,} cells")
    emit("")
    hdr = (f"{'PFT':>2} {'name':<36} "
           f"{'NLCD area':>11} {'cells':>8} | {'Chen area':>11} {'cells':>8} | "
           f"{'Chen-NLCD':>11} {'class':>10}")
    emit(hdr); emit("-"*len(hdr))

    nl_present_idx = []; ch_present_idx = []
    for j in range(NPFT):
        anl = float((area * p_nl[j] / 100.0)[conus].sum())
        ach = float((area * p_ch[j] / 100.0)[conus].sum())
        cnl = int(((p_nl[j] > PRESENT_FRAC) & conus).sum())
        cch = int(((p_ch[j] > PRESENT_FRAC) & conus).sum())
        innl = anl > 1.0  # populated anywhere (>1 km2 total)
        inch = ach > 1.0
        if innl: nl_present_idx.append(j)
        if inch: ch_present_idx.append(j)
        cls = ("both" if innl and inch else
               "CHEN-only" if inch else
               "NLCD-only" if innl else "neither")
        emit(f"{j:>2} {ELM_PFT_NAMES[j]:<36} "
             f"{anl:>11,.0f} {cnl:>8,} | {ach:>11,.0f} {cch:>8,} | "
             f"{ach-anl:>+11,.0f} {cls:>10}")
    emit("-"*len(hdr))
    emit(f"NLCD populates {len(nl_present_idx)} PFTs: {nl_present_idx}")
    emit(f"Chen populates {len(ch_present_idx)} PFTs: {ch_present_idx}")
    emit(f"  Chen-only types: {sorted(set(ch_present_idx)-set(nl_present_idx))}")
    emit(f"  NLCD-only types: {sorted(set(nl_present_idx)-set(ch_present_idx))}")
    emit("")

    # per-cell: how many PFTs present in each, and per-cell type-set disagreement
    npft_nl = ((p_nl > PRESENT_FRAC) & conus[None]).sum(axis=0)
    npft_ch = ((p_ch > PRESENT_FRAC) & conus[None]).sum(axis=0)
    # cells where the SET of present PFTs differs
    setdiff = (((p_nl > PRESENT_FRAC) != (p_ch > PRESENT_FRAC)).any(axis=0)) & conus
    emit(f"cells where the set of present PFTs differs: {int(setdiff.sum()):,} "
         f"({setdiff.sum()/conus.sum()*100:.1f}% of CONUS)")
    emit(f"mean #PFTs present per cell:  NLCD {npft_nl[conus].mean():.2f}   Chen {npft_ch[conus].mean():.2f}")
    emit("")

    # dominant PFT per cell (argmax over p), with tie detection
    def dominant(p):
        pm = np.where(conus[None], p, -1.0)
        d = pm.argmax(axis=0).astype(np.int16)
        top = np.take_along_axis(p, d[None], 0)[0]
        # tie: another PFT within 1e-6
        tie = ((np.abs(p - top[None]) < 1e-6).sum(axis=0) > 1) & conus & (top > 0)
        d[~conus] = -1
        return d, tie
    dnl, tnl = dominant(p_nl); dch, tch = dominant(p_ch)
    agree = (dnl == dch) & conus & ~tnl & ~tch
    disagree = (dnl != dch) & conus & ~tnl & ~tch
    emit(f"dominant-PFT (untied cells): agree {int(agree.sum()):,} "
         f"({agree.sum()/conus.sum()*100:.1f}%), differ {int(disagree.sum()):,} "
         f"({disagree.sum()/conus.sum()*100:.1f}%); "
         f"tie NLCD {int((tnl&conus).sum()):,}, tie Chen {int((tch&conus).sum()):,}")

    # ---- figure: per-PFT Chen-NLCD p(j) [% of cell], 17 panels ----
    fig, axes = plt.subplots(5, 4, figsize=(18, 13), layout="constrained")
    axf = axes.ravel()
    norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30)
    for j in range(NPFT):
        d = np.where(conus, p_ch[j] - p_nl[j], np.nan)
        a = axf[j]
        im = a.imshow(d, origin="lower", extent=EXTENT, cmap="RdBu_r", norm=norm,
                      interpolation="nearest")
        cls = ("both" if (p_nl[j][conus].sum()>0 and p_ch[j][conus].sum()>0)
               else "Chen-only" if p_ch[j][conus].sum()>0
               else "NLCD-only" if p_nl[j][conus].sum()>0 else "neither")
        a.set_title(f"{j} {SHORT[j]}  [{cls}]", fontsize=8)
        a.set_xticks([]); a.set_yticks([])
    for k in range(NPFT, len(axf)):
        axf[k].axis("off")
    fig.colorbar(im, ax=axes[-1, -1], shrink=0.9, label="Chen-NLCD  p(j) [% of cell]")
    fig.suptitle(f"PCT_NAT_PFT per-PFT difference (share of whole cell), Chen SSP1-RCP1.9 - NLCD, {YEAR}",
                 fontsize=13)
    f1 = OUTDIR / "figures" / "fig_natpft_perpft_diff_ssp1_2020.png"
    fig.savefig(f1, dpi=120); plt.close(fig)
    emit(f"wrote {f1}")

    txt = OUTDIR / "interim" / "natpft_types_2020_ssp1.txt"
    txt.write_text("\n".join(lines) + "\n")
    print(f"wrote {txt}")
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
