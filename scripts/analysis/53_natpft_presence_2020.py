#!/usr/bin/env python
"""Per-PFT PRESENCE (has / has-not) difference, NLCD vs Chen, 2020, cell by cell.

Not looking at percent magnitudes -- only whether each PFT is present in a cell.
A PFT is "present" in a cell if PCT_NAT_PFT(j) > THR (% of the natveg column).
Each CONUS cell falls into one of 4 classes per PFT:
    both-absent | both-present | NLCD-only | Chen-only
Table gives counts (at THR=0, 1, 5 for robustness); maps use THR_MAP.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src")
from elm_landuse.chen_classes import ELM_PFT_NAMES  # noqa: E402

NL = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
          "s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc")
CH = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/"
          "processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
EXTENT = (-125.0, -65.0, 25.0, 50.0)
YEAR = 2020
NPFT = 17
THR_MAP = 1.0          # % of natveg: "present" for the maps
THRS = [0.0, 1.0, 5.0]  # table columns

SHORT = {i: n.replace("_tree", " tree").replace("_grass", " grass").replace("_shrub", " shrub")
         for i, n in enumerate(ELM_PFT_NAMES)}
# categorical: 0 both-absent, 1 both-present, 2 NLCD-only, 3 Chen-only
CATCOL = ListedColormap(["#f2f2f2", "#7f7f7f", "#2166ac", "#b2182b"])
CATLAB = ["both absent", "both present", "NLCD-only", "Chen-only"]


def main():
    nl = xr.open_dataset(NL); ch = xr.open_dataset(CH)
    lat = nl.lat.values; lon = nl.lon.values
    nl_yrs = nl.time.dt.year.values; ch_yrs = ch.time.values.astype(int)
    inl = int(np.where(nl_yrs == YEAR)[0][0]); ich = int(np.where(ch_yrs == YEAR)[0][0])
    i15 = int(np.where(nl_yrs == 2015)[0][0])

    pf_nl = np.nan_to_num(nl.PCT_NAT_PFT.isel(time=inl).values.astype(np.float64))
    pf_ch = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=ich).values.astype(np.float64))
    ur = nl.PCT_URBAN.isel(time=i15).values.sum(axis=0)
    nv15 = np.nan_to_num(nl.PCT_NATVEG.isel(time=i15).values)
    conus = (nv15 + ur) > 0.0
    ncon = int(conus.sum())

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    emit("="*104)
    emit(f"PCT_NAT_PFT PRESENCE (has/has-not) -- NLCD vs Chen(SSP1-RCP1.9), {YEAR}, CONUS {ncon:,} cells")
    emit(f"  present in a cell if PCT_NAT_PFT(j) > THR (% of natveg). counts of cells per class.")
    emit("="*104)
    hdr = f"{'PFT':>2} {'name':<36}"
    for t in THRS:
        hdr += f" | THR>{t:g}%  both  NLCDonly  Chenonly"
    emit(hdr); emit("-"*len(hdr))

    cat_map = {}
    for j in range(NPFT):
        row = f"{j:>2} {ELM_PFT_NAMES[j]:<36}"
        for t in THRS:
            pn = (pf_nl[j] > t) & conus
            pc = (pf_ch[j] > t) & conus
            both = int((pn & pc).sum()); no = int((pn & ~pc).sum()); co = int((~pn & pc).sum())
            row += f" | {both:>8,} {no:>8,} {co:>8,}"
        emit(row)
        # categorical field at THR_MAP
        pn = (pf_nl[j] > THR_MAP) & conus
        pc = (pf_ch[j] > THR_MAP) & conus
        cat = np.full(conus.shape, -1, dtype=np.int8)
        cat[conus & ~pn & ~pc] = 0
        cat[conus & pn & pc] = 1
        cat[conus & pn & ~pc] = 2
        cat[conus & ~pn & pc] = 3
        cat_map[j] = cat
    emit("-"*len(hdr))
    emit(f"(map threshold = {THR_MAP:g}% of natveg)")
    emit("")

    # per-cell presence-disagreement count across PFTs (at THR_MAP)
    disagree_any = np.zeros(conus.shape, bool)
    ndis = np.zeros(conus.shape, np.int16)
    for j in range(NPFT):
        d = np.isin(cat_map[j], (2, 3))
        disagree_any |= d
        ndis += d.astype(np.int16)
    emit(f"cells where NLCD and Chen disagree on presence of >=1 PFT (THR>{THR_MAP:g}%): "
         f"{int((disagree_any & conus).sum()):,} ({(disagree_any & conus).sum()/ncon*100:.1f}%)")
    emit(f"mean #PFTs whose presence disagrees, per CONUS cell: {ndis[conus].mean():.2f}")
    emit("")
    emit("summary per PFT at map threshold (both / NLCD-only / Chen-only / %disagree):")
    for j in range(NPFT):
        c = cat_map[j]
        both = int((c == 1).sum()); no = int((c == 2).sum()); co = int((c == 3).sum())
        emit(f"  {j:>2} {SHORT[j]:<34} both {both:>8,}  NLCD-only {no:>8,}  Chen-only {co:>8,}"
             f"  disagree {100*(no+co)/ncon:5.1f}%")

    # ---- figure: 17 categorical maps ----
    fig, axes = plt.subplots(5, 4, figsize=(18, 13), layout="constrained")
    axf = axes.ravel()
    for j in range(NPFT):
        a = axf[j]
        a.imshow(np.where(conus, cat_map[j], np.nan), origin="lower", extent=EXTENT,
                 cmap=CATCOL, vmin=0, vmax=3, interpolation="nearest")
        a.set_title(f"{j} {SHORT[j]}", fontsize=8)
        a.set_xticks([]); a.set_yticks([])
    for k in range(NPFT, len(axf)):
        axf[k].axis("off")
    axf[NPFT].legend(handles=[mpatches.Patch(color=CATCOL(i), label=CATLAB[i]) for i in range(4)],
                     loc="center", frameon=False, fontsize=12, title=f"presence (PCT_NAT_PFT > {THR_MAP:g}% natveg)")
    fig.suptitle(f"PCT_NAT_PFT presence: NLCD vs Chen SSP1-RCP1.9, {YEAR} "
                 f"(has / has-not per PFT, threshold {THR_MAP:g}% of natveg)", fontsize=13)
    f1 = OUTDIR / "figures" / "fig_natpft_presence_ssp1_2020.png"
    fig.savefig(f1, dpi=120); plt.close(fig)
    emit(f"wrote {f1}")

    txt = OUTDIR / "interim" / "natpft_presence_2020_ssp1.txt"
    txt.write_text("\n".join(lines) + "\n")
    print(f"wrote {txt}")
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
