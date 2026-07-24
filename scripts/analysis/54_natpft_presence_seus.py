#!/usr/bin/env python
"""Per-PFT PRESENCE (has/has-not) difference, NLCD vs Chen, 2020, SOUTHEAST US.

Same as script 53 but restricted to the SEUS bbox (lon -95..-74, lat 24..37.5,
the project's SEUS box, REFERENCE.md 7). Maps are cropped to the bbox.
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
YEAR = 2020
NPFT = 17
THR_MAP = 1.0
THRS = [0.0, 1.0, 5.0]
SEUS = dict(lon0=-95.0, lon1=-74.0, lat0=24.0, lat1=37.5)

SHORT = {i: n.replace("_tree", " tree").replace("_grass", " grass").replace("_shrub", " shrub")
         for i, n in enumerate(ELM_PFT_NAMES)}
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

    # SEUS bbox mask + crop indices
    jlat = np.where((lat >= SEUS["lat0"]) & (lat <= SEUS["lat1"]))[0]
    ilon = np.where((lon >= SEUS["lon0"]) & (lon <= SEUS["lon1"]))[0]
    la0, la1 = jlat[0], jlat[-1] + 1
    lo0, lo1 = ilon[0], ilon[-1] + 1
    ext = (lon[lo0], lon[lo1-1], lat[la0], lat[la1-1])

    def crop(a):
        return a[..., la0:la1, lo0:lo1]

    conus_s = crop(conus)
    pf_nl_s = crop(pf_nl); pf_ch_s = crop(pf_ch)
    nseus = int(conus_s.sum())

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    emit("="*104)
    emit(f"PCT_NAT_PFT PRESENCE (has/has-not) -- NLCD vs Chen(SSP1-RCP1.9), {YEAR}, SOUTHEAST US")
    emit(f"  bbox lon {SEUS['lon0']}..{SEUS['lon1']}, lat {SEUS['lat0']}..{SEUS['lat1']}  "
         f"({nseus:,} CONUS cells in box)")
    emit(f"  present if PCT_NAT_PFT(j) > THR (% of natveg)")
    emit("="*104)
    hdr = f"{'PFT':>2} {'name':<36}"
    for t in THRS:
        hdr += f" | THR>{t:g}%  both  NLCDonly  Chenonly"
    emit(hdr); emit("-"*len(hdr))

    cat_map = {}
    for j in range(NPFT):
        row = f"{j:>2} {ELM_PFT_NAMES[j]:<36}"
        for t in THRS:
            pn = (pf_nl_s[j] > t) & conus_s
            pc = (pf_ch_s[j] > t) & conus_s
            both = int((pn & pc).sum()); no = int((pn & ~pc).sum()); co = int((~pn & pc).sum())
            row += f" | {both:>8,} {no:>8,} {co:>8,}"
        emit(row)
        pn = (pf_nl_s[j] > THR_MAP) & conus_s
        pc = (pf_ch_s[j] > THR_MAP) & conus_s
        cat = np.full(conus_s.shape, -1, dtype=np.int8)
        cat[conus_s & ~pn & ~pc] = 0
        cat[conus_s & pn & pc] = 1
        cat[conus_s & pn & ~pc] = 2
        cat[conus_s & ~pn & pc] = 3
        cat_map[j] = cat
    emit("-"*len(hdr))

    ndis = np.zeros(conus_s.shape, np.int16)
    dis_any = np.zeros(conus_s.shape, bool)
    for j in range(NPFT):
        d = np.isin(cat_map[j], (2, 3))
        ndis += d.astype(np.int16); dis_any |= d
    emit(f"cells disagreeing on presence of >=1 PFT (THR>{THR_MAP:g}%): "
         f"{int((dis_any & conus_s).sum()):,} ({(dis_any & conus_s).sum()/nseus*100:.1f}%)")
    emit(f"mean #PFTs whose presence disagrees, per SEUS cell: {ndis[conus_s].mean():.2f}")
    emit("")
    emit(f"per PFT at THR>{THR_MAP:g}% (both / NLCD-only / Chen-only / %disagree of SEUS):")
    for j in range(NPFT):
        c = cat_map[j]
        both = int((c == 1).sum()); no = int((c == 2).sum()); co = int((c == 3).sum())
        if both + no + co == 0:
            continue
        emit(f"  {j:>2} {SHORT[j]:<34} both {both:>7,}  NLCD-only {no:>7,}  Chen-only {co:>7,}"
             f"  disagree {100*(no+co)/nseus:5.1f}%")

    # ---- figure: only the PFTs that appear in SEUS ----
    active = [j for j in range(NPFT) if (cat_map[j] >= 1).any()]
    ncol = 3
    nrow = int(np.ceil(len(active) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol*5.2, nrow*3.2), layout="constrained")
    axf = np.atleast_1d(axes).ravel()
    for k, j in enumerate(active):
        a = axf[k]
        a.imshow(np.where(conus_s, cat_map[j], np.nan), origin="lower", extent=ext,
                 cmap=CATCOL, vmin=0, vmax=3, interpolation="nearest")
        c = cat_map[j]
        no = int((c == 2).sum()); co = int((c == 3).sum())
        a.set_title(f"{j} {SHORT[j]}  (NLCD-only {no:,} / Chen-only {co:,})", fontsize=9)
        a.set_xticks([]); a.set_yticks([])
    for k in range(len(active), len(axf)):
        axf[k].axis("off")
    axf[min(len(active), len(axf)-1)].legend(
        handles=[mpatches.Patch(color=CATCOL(i), label=CATLAB[i]) for i in range(4)],
        loc="center", frameon=False, fontsize=11) if len(active) < len(axf) else None
    fig.suptitle(f"PCT_NAT_PFT presence, SOUTHEAST US, {YEAR}: NLCD vs Chen SSP1-RCP1.9 "
                 f"(has/has-not per PFT, THR {THR_MAP:g}% natveg)", fontsize=12)
    f1 = OUTDIR / "figures" / "fig_natpft_presence_SEUS_ssp1_2020.png"
    fig.savefig(f1, dpi=130); plt.close(fig)
    emit(f"wrote {f1}")

    txt = OUTDIR / "interim" / "natpft_presence_SEUS_2020_ssp1.txt"
    txt.write_text("\n".join(lines) + "\n")
    print(f"wrote {txt}")
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
