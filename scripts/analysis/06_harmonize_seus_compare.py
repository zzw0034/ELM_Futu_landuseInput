#!/usr/bin/env python
"""Compare the SEUS harmonized product across the 4 SSP scenarios.
Reads only the per-scenario diag npz (harmonize_seus_diag_<SSP>.npz), which
holds group totals P_g (% of cell) for NLCD-2023, Chen, and harmonized.

  1. per-group trajectory 2023->2100: 4 harmonized SSP lines + NLCD-2023 anchor
  2. harmonized ΔPCT_NATVEG 2023->2100 map, one per scenario
  3. net Δ per group per scenario (grouped bars, SEUS area-weighted mean)
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.colors import TwoSlopeNorm

OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
SCEN = ["SSP1_RCP19", "SSP2_RCP45", "SSP4_RCP60", "SSP5_RCP85"]
SCOL = {"SSP1_RCP19": "#1a9850", "SSP2_RCP45": "#2c7fb8",
        "SSP4_RCP60": "#f4a020", "SSP5_RCP85": "#d73027"}
EXT = None


def diag_npz(s):
    p = OUTDIR / "interim" / f"harmonize_seus_diag_{s}.npz"
    if not p.exists() and s == "SSP1_RCP19":
        p = OUTDIR / "interim" / "harmonize_seus_diag.npz"
    return p


def main():
    # materialize arrays once per scenario (NpzFile re-decompresses on every
    # __getitem__, so indexing it inside loops would be catastrophically slow).
    D = {}
    for s in SCEN:
        with np.load(diag_npz(s), allow_pickle=True) as z:
            D[s] = {k: np.asarray(z[k]) for k in ("Pnl_g", "Pch_g", "Pharm_g")}
            if s == SCEN[0]:
                meta = {k: np.asarray(z[k]) for k in
                        ("annual", "area", "seus_mask", "lat", "lon", "gnames")}
    annual = meta["annual"]; area = meta["area"]; mask = meta["seus_mask"]
    lat = meta["lat"]; lon = meta["lon"]; GN = list(meta["gnames"])
    ext = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    w = area[mask]
    awmean = lambda f: np.average(f[mask], weights=w)
    NG = len(GN); nyr = annual.size

    # trajectories (harmonized) + NLCD anchor (same for all)
    traj = {s: {gi: np.array([awmean(D[s]["Pharm_g"][t, gi]) for t in range(nyr)])
                for gi in range(NG)} for s in SCEN}
    nl_anchor = {gi: awmean(D[SCEN[0]]["Pnl_g"][gi]) for gi in range(NG)}
    # ΔNATVEG per scenario (Σ_g Pharm_g[last] - [0])
    dnat = {s: np.where(mask, D[s]["Pharm_g"].sum(1)[-1] - D[s]["Pharm_g"].sum(1)[0], np.nan)
            for s in SCEN}
    # net Δ per group per scenario
    net = {s: [awmean(D[s]["Pharm_g"][-1, gi]) - awmean(D[s]["Pharm_g"][0, gi]) for gi in range(NG)]
           for s in SCEN}

    fig = plt.figure(figsize=(18, 13))
    gs = GridSpec(3, 5, figure=fig, height_ratios=[1, 1.15, 0.95], hspace=0.4, wspace=0.34)

    # row 1: trajectories
    for gi, g in enumerate(GN):
        ax = fig.add_subplot(gs[0, gi])
        ax.axhline(nl_anchor[gi], color="k", ls="--", lw=1, label="NLCD 2023")
        for s in SCEN:
            ax.plot(annual, traj[s][gi], color=SCOL[s], lw=2, label=s)
        ax.set_title(g, fontsize=11); ax.tick_params(labelsize=7)
        if gi == 0:
            ax.set_ylabel("group %, of cell\n(SEUS area-wt mean)", fontsize=8)
            ax.legend(fontsize=6.5)
    fig.text(0.5, 0.905, "1. Harmonized per-group trajectory 2023→2100 by scenario",
             ha="center", fontsize=13)

    # row 2: ΔNATVEG maps
    for si, s in enumerate(SCEN):
        ax = fig.add_subplot(gs[1, si])
        im = ax.imshow(dnat[s], origin="lower", extent=ext, cmap="BrBG",
                       norm=TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30), interpolation="nearest")
        ax.set_title(f"{s}\nΔNATVEG mean {awmean(np.nan_to_num(dnat[s])):+.2f} pp", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    cax = fig.add_subplot(gs[1, 4])
    cax.axis("off"); fig.colorbar(im, ax=cax, shrink=0.9, label="Δ PCT_NATVEG 2023→2100 [pp]")
    fig.text(0.5, 0.605, "2. Harmonized ΔPCT_NATVEG 2023→2100 (urbanization) by scenario",
             ha="center", fontsize=13)

    # row 3: net Δ per group per scenario (grouped bars)
    ax = fig.add_subplot(gs[2, :])
    x = np.arange(NG); bw = 0.2
    for k, s in enumerate(SCEN):
        ax.bar(x + (k - 1.5) * bw, net[s], bw, color=SCOL[s], label=s)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(GN, fontsize=10)
    ax.set_ylabel("net Δ 2023→2100\n[% of cell, SEUS mean]", fontsize=9)
    ax.legend(fontsize=9, ncol=4); ax.tick_params(labelsize=8)
    ax.set_title("3. Net change per functional group 2023→2100, by scenario", fontsize=12)

    fig.suptitle("SEUS harmonized product — scenario comparison (NLCD-2023 state + Chen SSP trend)",
                 fontsize=14, y=0.965)
    out = OUTDIR / "figures" / "fig_harmonize_seus_scenario_compare.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}\n")
    print("net Δ 2023→2100 [% of cell, SEUS area-wt mean]:")
    print(f"  {'group':<7}" + "".join(f"{s:>13}" for s in SCEN))
    for gi, g in enumerate(GN):
        print(f"  {g:<7}" + "".join(f"{net[s][gi]:>+13.3f}" for s in SCEN))
    print(f"  {'NATVEG':<7}" + "".join(f"{awmean(np.nan_to_num(dnat[s])):>+13.3f}" for s in SCEN))


if __name__ == "__main__":
    main()
