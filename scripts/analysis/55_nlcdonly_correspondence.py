#!/usr/bin/env python
"""For selected PFTs (7,9,13): understand the 'NLCD-only present' cells.

Three questions, 2020, SSP1-RCP1.9, CONUS:
  (1) how is Chen's own PCT_NAT_PFT(j) distributed?
  (2) in cells where ONLY NLCD has PFT j (NLCD>1%, Chen<=1%), what does Chen
      put there instead? -> Chen dominant PFT / functional group breakdown.
  (3) in cells where NLCD has PFT j, what is the magnitude PCT_NAT_PFT(j)?
      (split: both-present vs NLCD-only)
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
THR = 1.0
TARGETS = [7, 9, 13]

GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
          "Shrub": [9, 10, 11], "Grass": [12, 13, 14], "Crop": [15, 16]}
GN = list(GROUPS)
GCOL = {"Bare": "#b3ac9f", "Tree": "#1c5f2c", "Shrub": "#ccb879",
        "Grass": "#dfdfc2", "Crop": "#ab6c28"}
GMAP = ListedColormap([GCOL[g] for g in GN] + ["#ffffff"])
SHORT = {i: n.replace("_tree", " tree").replace("_grass", " grass").replace("_shrub", " shrub")
         for i, n in enumerate(ELM_PFT_NAMES)}
PFT2GRP = {j: gi for gi, g in enumerate(GN) for j in GROUPS[g]}


def main():
    nl = xr.open_dataset(NL); ch = xr.open_dataset(CH)
    lat = nl.lat.values; lon = nl.lon.values
    nl_yrs = nl.time.dt.year.values; ch_yrs = ch.time.values.astype(int)
    inl = int(np.where(nl_yrs == YEAR)[0][0]); ich = int(np.where(ch_yrs == YEAR)[0][0])
    i15 = int(np.where(nl_yrs == 2015)[0][0])

    pf_nl = np.nan_to_num(nl.PCT_NAT_PFT.isel(time=inl).values.astype(np.float64))
    pf_ch = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=ich).values.astype(np.float64))
    ur = nl.PCT_URBAN.isel(time=i15).values.sum(axis=0)
    conus = (np.nan_to_num(nl.PCT_NATVEG.isel(time=i15).values) + ur) > 0.0

    # Chen dominant functional group per cell
    g_ch = np.stack([pf_ch[GROUPS[g]].sum(axis=0) for g in GN])  # (5,lat,lon)
    dom_g_ch = np.where(conus, g_ch.argmax(axis=0), len(GN)).astype(np.int16)
    # Chen dominant PFT per cell
    dom_pft_ch = np.where(conus, pf_ch.argmax(axis=0), -1)

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    emit("="*90)
    emit(f"NLCD-only cells: what does Chen have there?  ({YEAR}, SSP1-RCP1.9, CONUS, THR>{THR:g}%)")
    emit("="*90)

    fig, axes = plt.subplots(len(TARGETS), 3, figsize=(17, 4.2*len(TARGETS)), layout="constrained")

    for r, j in enumerate(TARGETS):
        pres_nl = (pf_nl[j] > THR) & conus
        pres_ch = (pf_ch[j] > THR) & conus
        nlcd_only = pres_nl & ~pres_ch
        both = pres_nl & pres_ch

        emit("")
        emit("#"*90)
        emit(f"PFT {j}  {ELM_PFT_NAMES[j]}   (group: {GN[PFT2GRP[j]]})")
        emit("#"*90)
        emit(f"  present: both {int(both.sum()):,}   NLCD-only {int(nlcd_only.sum()):,}   "
             f"Chen-only {int((pres_ch & ~pres_nl).sum()):,}")

        # (3) magnitude of NLCD PCT_j
        def pcts(mask):
            v = pf_nl[j][mask]
            if v.size == 0:
                return "n/a"
            return "p25/50/75/90 = " + " / ".join(f"{x:.1f}" for x in np.percentile(v, [25, 50, 75, 90])) \
                   + f"  mean {v.mean():.1f}"
        emit(f"  NLCD PCT_NAT_PFT({j}) magnitude [% of natveg]:")
        emit(f"     over all NLCD-present : {pcts(pres_nl)}")
        emit(f"     over both-present     : {pcts(both)}")
        emit(f"     over NLCD-only        : {pcts(nlcd_only)}")

        # (2) in NLCD-only cells, what is Chen's dominant PFT / group?
        emit(f"  In the {int(nlcd_only.sum()):,} NLCD-only cells, Chen's DOMINANT functional group:")
        dg = dom_g_ch[nlcd_only]
        tot = dg.size
        for gi, g in enumerate(GN):
            c = int((dg == gi).sum())
            if c:
                emit(f"     {g:<6} {c:>8,}  ({c/tot*100:5.1f}%)")
        emit(f"  In the same cells, Chen's DOMINANT PFT (top 6):")
        dp = dom_pft_ch[nlcd_only]
        vals, cnts = np.unique(dp, return_counts=True)
        order = np.argsort(cnts)[::-1]
        for k in order[:6]:
            pj = int(vals[k]); c = int(cnts[k])
            # mean Chen share of that PFT in these cells
            msh = pf_ch[pj][nlcd_only].mean()
            emit(f"     PFT {pj:>2} {SHORT[pj]:<34} {c:>8,} ({c/tot*100:5.1f}%)  mean Chen share {msh:.1f}%")
        # mean Chen share of the SAME PFT j in NLCD-only cells (should be ~0-ish, below THR)
        emit(f"     [Chen's own PFT {j} share in these cells: mean {pf_ch[j][nlcd_only].mean():.2f}%]")

        # ---- panel A: Chen PCT_j magnitude ----
        a = axes[r, 0]
        im = a.imshow(np.where(conus, pf_ch[j], np.nan), origin="lower", extent=EXTENT,
                      cmap="viridis", vmin=0, vmax=60, interpolation="nearest")
        a.set_title(f"Chen PCT_NAT_PFT({j}) {SHORT[j]} [% natveg]", fontsize=9)
        a.set_xticks([]); a.set_yticks([]); fig.colorbar(im, ax=a, shrink=0.7)

        # ---- panel B: in NLCD-only cells, Chen dominant group ----
        b = axes[r, 1]
        canvas = np.full(conus.shape, np.nan)
        canvas[nlcd_only] = dom_g_ch[nlcd_only]
        b.imshow(canvas, origin="lower", extent=EXTENT, cmap=GMAP, vmin=0, vmax=len(GN),
                 interpolation="nearest")
        b.set_title(f"NLCD-only PFT{j} cells: Chen's dominant group", fontsize=9)
        b.set_xticks([]); b.set_yticks([])
        if r == 0:
            b.legend(handles=[mpatches.Patch(color=GCOL[g], label=g) for g in GN],
                     loc="lower left", fontsize=7, framealpha=0.9)

        # ---- panel C: NLCD PCT_j histogram (both vs nlcd-only) ----
        c = axes[r, 2]
        c.hist(pf_nl[j][both], bins=np.linspace(0, 100, 41), alpha=0.6, label="both-present", color="#7f7f7f")
        c.hist(pf_nl[j][nlcd_only], bins=np.linspace(0, 100, 41), alpha=0.6, label="NLCD-only", color="#2166ac")
        c.set_title(f"NLCD PCT_NAT_PFT({j}) magnitude in NLCD-present cells", fontsize=9)
        c.set_xlabel("% of natveg"); c.set_ylabel("cells"); c.legend(fontsize=8)

    fig.suptitle(f"NLCD-only presence, what Chen has instead — PFT 7/9/13, {YEAR} SSP1-RCP1.9", fontsize=13)
    f1 = OUTDIR / "figures" / "fig_nlcdonly_correspondence_ssp1_2020.png"
    fig.savefig(f1, dpi=125); plt.close(fig)
    emit("")
    emit(f"wrote {f1}")
    txt = OUTDIR / "interim" / "nlcdonly_correspondence_2020_ssp1.txt"
    txt.write_text("\n".join(lines) + "\n")
    print(f"wrote {txt}")
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
