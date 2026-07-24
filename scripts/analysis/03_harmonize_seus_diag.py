#!/usr/bin/env python
"""Diagnostics for the SEUS harmonization pilot (HARMONIZATION_SEUS_PILOT.md §13.9):
  1. per-group trajectory 2023->2100: NLCD-2023 (const) vs Chen vs harmonized
  2. budget residual map + ΔPCT_NATVEG map + composition-change map (★ sample cells)
  3. sample cells before/after PFT composition, AUTO-SELECTED to span behaviour:
     frozen (Chen projects no change) / composition shift / natveg loss (urban).

Chen's SSP1 transient is spatially concentrated, so ~half the domain is frozen
(composition dissimilarity p50 = 0); the sample cells are picked to show both
the frozen case and the cells that actually move.
"""
from __future__ import annotations
from pathlib import Path
import sys
import argparse
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src")
from elm_landuse.chen_classes import ELM_PFT_NAMES  # noqa: E402

OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")


def diag_npz(scenario):
    """Scenario diag npz, with fallback to the unsuffixed SSP1 name."""
    p = OUTDIR / "interim" / f"harmonize_seus_diag_{scenario}.npz"
    if not p.exists() and scenario == "SSP1_RCP19":
        p = OUTDIR / "interim" / "harmonize_seus_diag.npz"
    return p


GCOL = {"Bare": "#b3ac9f", "Tree": "#1c5f2c", "Shrub": "#ccb879",
        "Grass": "#dfdfc2", "Crop": "#ab6c28"}
ACTIVE_PFT = [0, 1, 7, 9, 10, 13, 14, 15]
SHORT = {i: ELM_PFT_NAMES[i].replace("_", " ")[:20] for i in range(17)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="SSP1_RCP19")
    args = ap.parse_args()
    NC = OUTDIR / "processed" / f"harmonized_SEUS_{args.scenario}_2024-2100_1_24deg.nc"
    z = np.load(diag_npz(args.scenario), allow_pickle=True)
    annual = z["annual"]; area = z["area"]; mask = z["seus_mask"]
    Pnl = z["Pnl_g"]; Pch = z["Pch_g"]; Pharm = z["Pharm_g"]; GN = list(z["gnames"])
    lat = z["lat"]; lon = z["lon"]
    ext = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    w = area[mask]
    awmean = lambda f: np.average(f[mask], weights=w)

    nyr = annual.size
    traj = {g: dict(nl=awmean(Pnl[gi]),
                    ch=np.array([awmean(Pch[t, gi]) for t in range(nyr)]),
                    hm=np.array([awmean(Pharm[t, gi]) for t in range(nyr)]))
            for gi, g in enumerate(GN)}

    dch = Pch.sum(1)[1:] - Pch.sum(1)[:-1]
    dhm = Pharm.sum(1)[1:] - Pharm.sum(1)[:-1]
    resid = np.abs(dch - dhm).max(axis=0)
    resid_m = np.where(mask, resid, np.nan)

    ds = xr.open_dataset(NC)
    latn = ds.lat.values; lonn = ds.lon.values; yrs = ds.time.values.astype(int)
    # nc now starts at 2024 (2023 is NLCD's own file); use the first year as "before"
    i23 = 0; i00 = int(np.where(yrs == 2100)[0][0])
    yb = int(yrs[i23])   # = 2024
    c23 = np.nan_to_num(ds.PCT_NAT_PFT.isel(time=i23).values)
    c00 = np.nan_to_num(ds.PCT_NAT_PFT.isel(time=i00).values)
    nv23 = np.nan_to_num(ds.PCT_NATVEG.isel(time=i23).values)
    nv00 = np.nan_to_num(ds.PCT_NATVEG.isel(time=i00).values)
    dcomp = 0.5 * np.abs(c00 - c23).sum(axis=0)        # composition dissimilarity 0..100
    dnv = nv00 - nv23
    natmask = mask & (nv23 > 5)

    # --- auto-select 3 sample cells spanning behaviour ---
    def pick(score, extra=None):
        s = np.where(natmask & (extra if extra is not None else True), score, -np.inf)
        return np.unravel_index(np.argmax(s), score.shape)
    # frozen: high natveg, multiple groups, ~0 composition change
    ngrp = (np.stack([c23[g].sum(0) for g in
             ([0], [1, 2, 3, 4, 5, 6, 7, 8], [9, 10, 11], [12, 13, 14], [15, 16])]) > 1).sum(0)
    frozen = pick(-dcomp + 0.0, extra=(nv23 > 90) & (ngrp >= 2) & (dcomp < 0.05))
    # composition shift: moderate-large dissim, stays vegetated both years
    shift = pick(-(np.abs(dcomp - 45)), extra=(nv23 > 60) & (nv00 > 60))
    # urban loss: biggest natveg drop
    loss = pick(-dnv, extra=(nv23 > 40))
    samples = [(frozen, "frozen (Chen ~no change)"),
               (shift, "composition shift"),
               (loss, "natveg loss (urban)")]

    # ================= figure =================
    fig = plt.figure(figsize=(17, 12.5))
    gs = GridSpec(3, 6, figure=fig, height_ratios=[1, 1.25, 1.15], hspace=0.42, wspace=0.5)

    # row 1: trajectories (5 groups, cols 0..4; col 5 blank/legend)
    for gi, g in enumerate(GN):
        ax = fig.add_subplot(gs[0, gi])
        ax.axhline(traj[g]["nl"], color="k", ls="--", lw=1, label="NLCD 2023")
        ax.plot(annual, traj[g]["ch"], color="#c1361b", lw=1.6, label="Chen")
        ax.plot(annual, traj[g]["hm"], color=GCOL[g], lw=2.6, label="harmonized")
        ax.set_title(g, fontsize=10); ax.tick_params(labelsize=7)
        if gi == 0:
            ax.set_ylabel("group %, of cell\n(SEUS area-wt mean)", fontsize=8)
            ax.legend(fontsize=7)
    fig.text(0.5, 0.905, "1. Per-group trajectory 2023→2100  "
             "(NLCD-2023 anchor · Chen trend · harmonized)", ha="center", fontsize=12)

    # row 2: three maps
    def addmap(col0, col1, arr, title, cmap, vmin, vmax, stars=False):
        ax = fig.add_subplot(gs[1, col0:col1])
        im = ax.imshow(arr, origin="lower", extent=ext, cmap=cmap, vmin=vmin, vmax=vmax,
                       interpolation="nearest")
        ax.set_title(title, fontsize=9); ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.75)
        if stars:
            cols = {"frozen (Chen ~no change)": "cyan", "composition shift": "red",
                    "natveg loss (urban)": "magenta"}
            for (jj, ii), lab in samples:
                ax.plot(lonn[ii], latn[jj], "*", color=cols[lab], ms=15, mec="k")
        return ax
    addmap(0, 2, resid_m, f"2. Budget residual max_t|Δchen−Δharm| [%cell]\n"
           f"mean {np.nanmean(resid_m):.2f}, max {np.nanmax(resid_m):.1f}", "inferno_r", 0, 5)
    addmap(2, 4, np.where(mask, dnv, np.nan), f"harmonized ΔPCT_NATVEG {yb}→2100 [pp]",
           "BrBG", -30, 30)
    addmap(4, 6, np.where(natmask, dcomp, np.nan),
           "composition change |ΔPCT_NAT_PFT| [0..100]\n(★ = sample cells)",
           "viridis", 0, 60, stars=True)

    # row 3: sample-cell composition bars
    x = np.arange(len(ACTIVE_PFT))
    for si, ((jj, ii), lab) in enumerate(samples):
        a = fig.add_subplot(gs[2, si*2:si*2+2])
        v23 = c23[ACTIVE_PFT, jj, ii]; v00 = c00[ACTIVE_PFT, jj, ii]
        a.bar(x - 0.2, v23, 0.4, color="#8aa0b6",
              label=f"{yb} harm (natveg {nv23[jj,ii]:.0f}%)")
        a.bar(x + 0.2, v00, 0.4, color="#1c5f2c",
              label=f"2100 harm (natveg {nv00[jj,ii]:.0f}%)")
        a.set_xticks(x); a.set_xticklabels([SHORT[p] for p in ACTIVE_PFT],
                                           rotation=60, ha="right", fontsize=6)
        a.set_title(f"{lab}\nlat {latn[jj]:.2f} lon {lonn[ii]:.2f}  (dissim {dcomp[jj,ii]:.0f})",
                    fontsize=9)
        a.set_ylabel("% of natveg", fontsize=8); a.tick_params(labelsize=7); a.legend(fontsize=6)
    fig.text(0.5, 0.335, "3. Sample-cell composition (auto-selected): frozen · shift · natveg-loss",
             ha="center", fontsize=12)

    fig.suptitle(f"SEUS harmonization pilot — NLCD state + Chen2022 {args.scenario} trend "
                 "(anchor 2023, group-level eq.1, NLCD-frozen re-split)", fontsize=13, y=0.965)
    out = OUTDIR / "figures" / f"fig_harmonize_seus_diag_{args.scenario}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")
    for (jj, ii), lab in samples:
        print(f"  {lab:<26} lat {latn[jj]:.2f} lon {lonn[ii]:.2f}  "
              f"dissim {dcomp[jj,ii]:.1f}  natveg {nv23[jj,ii]:.0f}->{nv00[jj,ii]:.0f}")
    ds.close()


if __name__ == "__main__":
    main()
