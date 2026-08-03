#!/usr/bin/env python
"""Compare the FINAL landuse.timeseries products across SSP scenarios.

Reads the delivered files directly (not the interim diag npz):

    outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc

All static land-unit variables (AREA, LANDFRAC_PFT, PCT_NATVEG, PCT_CROP,
PCT_URBAN, ...) are byte-identical across scenarios -- they are copied from the
same NLCD-derived target -- and GRAZING is both scenario-identical and constant
in time. So the ONLY things that differ between scenarios are

    PCT_NAT_PFT(time, natpft, lat, lon)   composition of the natveg column
    HARVEST_VH1/VH2/SH1/SH2/SH3(time,...) wood harvest fractions

and that is what this script quantifies.

Areas are computed as
    natveg_km2   = AREA * LANDFRAC_PFT * PCT_NATVEG/100          (static)
    group_km2(t) = natveg_km2 * sum_{j in g} PCT_NAT_PFT(t,j)/100

Caveat on harvest (see the file's `harvest_natveg_convention` attribute):
HARVEST_* were normalized by the ANNUAL harmonized natveg, while the file's
PCT_NATVEG is the target's STATIC column. The absolute harvest areas below
therefore carry a factor natveg_static/natveg_annual. The same convention
applies to every scenario, so the cross-scenario comparison is unaffected.

Stage 1 (--compute) walks the four files a time-slice at a time and writes a
small npz; stage 2 (--plot) draws the figures from that npz. Default runs both.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import xarray as xr
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
PROC = ROOT / "outputs" / "processed"
OUTDIR = ROOT / "outputs"
NPZ = OUTDIR / "interim" / "scenario_compare_final.npz"
STEM = "landuse.timeseries_SEUS_1_24deg_nlcd2elm_%s_simyr2024-2100.nc"

SCEN = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]
SLAB = {"SSP1_RCP19": "SSP1-RCP1.9", "SSP2_RCP45": "SSP2-RCP4.5",
        "SSP3_RCP70": "SSP3-RCP7.0", "SSP5_RCP85": "SSP5-RCP8.5"}
SCOL = {"SSP1_RCP19": "#1a9850", "SSP2_RCP45": "#2c7fb8",
        "SSP3_RCP70": "#7b3294", "SSP5_RCP85": "#d73027"}

GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8], "Shrub": [9, 10, 11],
          "Grass": [12, 13, 14], "Crop": [15, 16]}
GN = list(GROUPS)
NG = len(GN)

HVARS = ["HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"]
HLAB = ["VH1 primary forest", "VH2 primary non-forest", "SH1 secondary mature",
        "SH2 secondary young", "SH3 secondary non-forest"]
HCOL = ["#08519c", "#6baed6", "#238b45", "#74c476", "#bdbdbd"]


# --------------------------------------------------------------------------
# stage 1: reduce the four 152 MB files to a small npz
# --------------------------------------------------------------------------
def compute() -> None:
    d0 = xr.open_dataset(PROC / (STEM % SCEN[0]), decode_times=False)
    years = d0.YEAR.values.astype(int)
    lat = d0.LATIXY.values[:, 0]
    lon = d0.LONGXY.values[0, :]
    area = np.nan_to_num(d0.AREA.values.astype(np.float64))
    lfrac = np.nan_to_num(d0.LANDFRAC_PFT.values.astype(np.float64))
    natveg_pct = np.nan_to_num(d0.PCT_NATVEG.values.astype(np.float64))
    natveg_km2 = area * lfrac * natveg_pct / 100.0
    mask = natveg_km2 > 0.0
    nyr = years.size
    d0.close()

    print(f"grid {lat.size}x{lon.size}  years {years[0]}-{years[-1]} ({nyr})")
    print(f"natveg cells {mask.sum()} / {mask.size}   "
          f"total natveg {natveg_km2.sum()/1e4:.3f} Mha")

    out = dict(years=years, lat=lat, lon=lon, gnames=np.array(GN),
               scen=np.array(SCEN), natveg_km2=natveg_km2, mask=mask,
               hvars=np.array(HVARS))

    for s in SCEN:
        f = PROC / (STEM % s)
        print(f"\n== {s}  {f.name}", flush=True)
        ds = xr.open_dataset(f, decode_times=False)
        assert int(ds.YEAR.values[0]) == years[0]

        g_km2 = np.zeros((nyr, NG))          # group area, km^2
        pft_km2 = np.zeros((nyr, 17))        # per-PFT area, km^2
        h_km2 = np.zeros((nyr, len(HVARS)))  # harvest area, km^2/yr
        gmap = np.zeros((2, NG, lat.size, lon.size))   # 2024, 2100 group %
        hcum = np.zeros((lat.size, lon.size))          # cumulative harvest frac

        for t in range(nyr):
            p = np.nan_to_num(ds.PCT_NAT_PFT.isel(time=t).values.astype(np.float64))
            pft_km2[t] = (p / 100.0 * natveg_km2[None]).sum(axis=(1, 2))
            gstack = np.stack([p[GROUPS[g]].sum(axis=0) for g in GN])
            g_km2[t] = (gstack / 100.0 * natveg_km2[None]).sum(axis=(1, 2))
            if t == 0:
                gmap[0] = gstack
            if t == nyr - 1:
                gmap[1] = gstack
            hslice = np.stack([np.nan_to_num(ds[v].isel(time=t).values.astype(np.float64))
                               for v in HVARS])
            h_km2[t] = (hslice * natveg_km2[None]).sum(axis=(1, 2))
            hcum += hslice.sum(axis=0)
            if t % 20 == 0:
                print(f"   t={t} {years[t]}", flush=True)
        ds.close()

        out[f"g_km2_{s}"] = g_km2
        out[f"pft_km2_{s}"] = pft_km2
        out[f"h_km2_{s}"] = h_km2
        out[f"gmap_{s}"] = gmap
        out[f"hcum_{s}"] = hcum
        print(f"   Tree {g_km2[0, 1]/1e4:.3f} -> {g_km2[-1, 1]/1e4:.3f} Mha  "
              f"harvest total {h_km2.sum()/1e4:.3f} Mha")

    NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(NPZ, **out)
    print(f"\nwrote {NPZ}")


# --------------------------------------------------------------------------
# stage 2: figures + tables
# --------------------------------------------------------------------------
def _load():
    with np.load(NPZ, allow_pickle=True) as z:
        return {k: np.asarray(z[k]) for k in z.files}


def _mapax(ax, field, mask, ext, vmax, cmap="BrBG"):
    f = np.where(mask, field, np.nan)
    im = ax.imshow(f, origin="lower", extent=ext, cmap=cmap,
                   norm=TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax),
                   interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    return im


def plot() -> None:
    Z = _load()
    years = Z["years"]; lat = Z["lat"]; lon = Z["lon"]
    mask = Z["mask"]; natveg_km2 = Z["natveg_km2"]
    ext = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    figdir = OUTDIR / "figures"; figdir.mkdir(parents=True, exist_ok=True)
    MHA = 1e4  # km^2 -> Mha
    w = natveg_km2[mask]

    g = {s: Z[f"g_km2_{s}"] / MHA for s in SCEN}          # (nyr, NG) Mha
    h = {s: Z[f"h_km2_{s}"] / MHA for s in SCEN}          # (nyr, 5)  Mha/yr
    gmap = {s: Z[f"gmap_{s}"] for s in SCEN}              # (2, NG, ny, nx) %
    hcum = {s: Z[f"hcum_{s}"] for s in SCEN}
    pft = {s: Z[f"pft_km2_{s}"] / MHA for s in SCEN}

    # ---------------- FIG 1: trajectories + net change + divergence --------
    fig = plt.figure(figsize=(19, 10.5))
    gs = GridSpec(2, 5, figure=fig, height_ratios=[1.0, 1.05],
                  hspace=0.34, wspace=0.30)

    for gi, gname in enumerate(GN):
        ax = fig.add_subplot(gs[0, gi])
        for s in SCEN:
            ax.plot(years, g[s][:, gi], color=SCOL[s], lw=2, label=SLAB[s])
        ax.set_title(gname, fontsize=12)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25, lw=0.5)
        if gi == 0:
            ax.set_ylabel("SEUS area [Mha]", fontsize=9)
            ax.legend(fontsize=7, loc="best")
    fig.text(0.5, 0.945, "1. Functional-group area over the SEUS domain, 2024-2100",
             ha="center", fontsize=14)

    # net change bars
    ax = fig.add_subplot(gs[1, :3])
    x = np.arange(NG); bw = 0.2
    for k, s in enumerate(SCEN):
        net = g[s][-1] - g[s][0]
        b = ax.bar(x + (k - 1.5) * bw, net, bw, color=SCOL[s], label=SLAB[s])
        ax.bar_label(b, fmt="%+.2f", fontsize=6.5, padding=1)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(GN, fontsize=11)
    ax.set_ylabel("net change 2024 -> 2100 [Mha]", fontsize=10)
    ax.legend(fontsize=8, ncol=4); ax.tick_params(labelsize=9)
    ax.grid(axis="y", alpha=0.25, lw=0.5)
    ax.set_title("2. Net area change per functional group, 2024 -> 2100", fontsize=13)

    # pairwise dissimilarity in 2100 (group level, % of natveg column)
    ax = fig.add_subplot(gs[1, 3:])
    D = np.zeros((len(SCEN), len(SCEN)))
    for i, a in enumerate(SCEN):
        for j, b in enumerate(SCEN):
            d = 0.5 * np.abs(gmap[a][1] - gmap[b][1]).sum(axis=0)
            D[i, j] = np.average(d[mask], weights=w)
    im = ax.imshow(D, cmap="magma_r", vmin=0)
    ax.set_xticks(range(len(SCEN))); ax.set_yticks(range(len(SCEN)))
    ax.set_xticklabels([SLAB[s] for s in SCEN], fontsize=8, rotation=20)
    ax.set_yticklabels([SLAB[s] for s in SCEN], fontsize=8)
    for i in range(len(SCEN)):
        for j in range(len(SCEN)):
            ax.text(j, i, f"{D[i, j]:.2f}", ha="center", va="center", fontsize=9,
                    color="w" if D[i, j] > D.max() * 0.55 else "k")
    fig.colorbar(im, ax=ax, shrink=0.85, label="mean dissimilarity [% of natveg column]")
    ax.set_title("3. Pairwise scenario dissimilarity in 2100\n"
                 "D = 0.5*sum_g|P_a,g - P_b,g|, area-weighted", fontsize=12)

    fig.suptitle("SEUS future landuse.timeseries -- scenario comparison "
                 "(state: PCT_NAT_PFT composition on a static natveg column)",
                 fontsize=15, y=0.995)
    p1 = figdir / "fig_scen_final_cmp_trajectory.png"
    fig.savefig(p1, dpi=130, bbox_inches="tight"); plt.close(fig)
    print(f"wrote {p1}")

    # ---------------- FIG 2: change maps -----------------------------------
    rows = [("Tree", 1), ("Crop", 4), ("Grass", 3)]
    fig = plt.figure(figsize=(19, 11.5))
    gs = GridSpec(len(rows), 5, figure=fig, width_ratios=[1, 1, 1, 1, 0.06],
                  hspace=0.16, wspace=0.06)
    for ri, (gname, gi) in enumerate(rows):
        dd = {s: gmap[s][1, gi] - gmap[s][0, gi] for s in SCEN}
        vmax = max(np.nanpercentile(np.abs(dd[s][mask]), 99.0) for s in SCEN)
        vmax = max(vmax, 1.0)
        for si, s in enumerate(SCEN):
            ax = fig.add_subplot(gs[ri, si])
            im = _mapax(ax, dd[s], mask, ext, vmax,
                        cmap="BrBG" if gname != "Crop" else "PuOr_r")
            m = np.average(dd[s][mask], weights=w)
            ax.set_title(f"{SLAB[s]}   mean {m:+.2f} pp", fontsize=10)
            if si == 0:
                ax.set_ylabel(f"$\\Delta$ {gname}", fontsize=13)
        cax = fig.add_subplot(gs[ri, 4])
        fig.colorbar(im, cax=cax, label=f"$\\Delta$ {gname} 2024->2100 "
                                        "[pp of natveg column]")
    fig.suptitle("Spatial pattern of composition change 2024 -> 2100, by scenario "
                 "(pp = percentage points of the natural-vegetation column)",
                 fontsize=15, y=0.925)
    p2 = figdir / "fig_scen_final_cmp_maps.png"
    fig.savefig(p2, dpi=130, bbox_inches="tight"); plt.close(fig)
    print(f"wrote {p2}")

    # ---------------- FIG 3: harvest ---------------------------------------
    fig = plt.figure(figsize=(19, 10.5))
    gs = GridSpec(2, 5, figure=fig, height_ratios=[1.0, 1.1],
                  width_ratios=[1, 1, 1, 1, 0.06], hspace=0.30, wspace=0.15)

    ax = fig.add_subplot(gs[0, :2])
    for s in SCEN:
        ax.plot(years, h[s].sum(axis=1), color=SCOL[s], lw=2, label=SLAB[s])
    ax.set_ylabel("total wood harvest [Mha yr$^{-1}$]", fontsize=10)
    ax.set_title("1. Annual wood-harvest area (sum of 5 HARVEST_* classes)", fontsize=13)
    ax.legend(fontsize=8); ax.grid(alpha=0.25, lw=0.5); ax.tick_params(labelsize=9)

    ax = fig.add_subplot(gs[0, 2:4])
    x = np.arange(len(SCEN)); bot = np.zeros(len(SCEN))
    for k in range(len(HVARS)):
        v = np.array([h[s][:, k].sum() for s in SCEN])
        ax.bar(x, v, 0.6, bottom=bot, color=HCOL[k], label=HLAB[k])
        bot += v
    for i, s in enumerate(SCEN):
        ax.text(i, bot[i], f"{bot[i]:.1f}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels([SLAB[s] for s in SCEN], fontsize=9)
    ax.set_ylabel("cumulative 2024-2100 [Mha]", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper left")
    ax.set_title("2. Cumulative harvest by class", fontsize=13)
    ax.tick_params(labelsize=9)

    vmax = max(np.nanpercentile(hcum[s][mask], 99.5) for s in SCEN)
    for si, s in enumerate(SCEN):
        ax = fig.add_subplot(gs[1, si])
        f = np.where(mask, hcum[s], np.nan)
        im = ax.imshow(f, origin="lower", extent=ext, cmap="YlOrRd",
                       vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{SLAB[s]}", fontsize=11)
        if si == 0:
            ax.set_ylabel("cumulative harvest", fontsize=12)
    cax = fig.add_subplot(gs[1, 4])
    fig.colorbar(im, cax=cax, label="sum over 2024-2100 of HARVEST_*\n"
                                    "[fraction of natveg column, cumulative]")
    fig.text(0.5, 0.475, "3. Where the harvest lands (cumulative 2024-2100)",
             ha="center", fontsize=13)
    fig.suptitle("SEUS future landuse.timeseries -- wood harvest and grazing forcing "
                 "(harvest downscaled from the paired LUH2 scenario)",
                 fontsize=15, y=0.955)
    p3 = figdir / "fig_scen_final_cmp_harvest.png"
    fig.savefig(p3, dpi=130, bbox_inches="tight"); plt.close(fig)
    print(f"wrote {p3}")

    # ---------------- tables -----------------------------------------------
    def rule(c="="):
        print(c * 96)

    rule()
    print("A. Functional-group area over SEUS [Mha]  (natveg column, static natveg)")
    print("   NOTE: 2024 already differs slightly between scenarios -- the Chen trend")
    print("   applies from 2024 on; the common anchor is NLCD 2023, not 2024.")
    rule("-")
    print(f"{'group':<7}" + "".join(f"{SLAB[s]:>22}" for s in SCEN))
    print(f"{'':<7}" + "".join(f"{'2024 -> 2100 (delta)':>22}" for s in SCEN))
    for gi, gname in enumerate(GN):
        row = f"{gname:<7}"
        for s in SCEN:
            row += (f"{g[s][0, gi]:>7.3f}->{g[s][-1, gi]:>7.3f}"
                    f"({g[s][-1, gi]-g[s][0, gi]:+.2f})")
        print(row)
    print(f"{'TOTAL':<7}" + "".join(f"{g[s][0].sum():>7.3f}->{g[s][-1].sum():>7.3f}"
                                    f"{'':>7}" for s in SCEN))
    print("   (TOTAL is the static natveg column: identical and constant by construction)")

    rule()
    print("B. Relative change 2024->2100 [% of the 2024 group area]")
    rule("-")
    print(f"{'group':<7}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for gi, gname in enumerate(GN):
        row = f"{gname:<7}"
        for s in SCEN:
            a0 = g[s][0, gi]
            row += f"{(g[s][-1, gi]-a0)/a0*100 if a0 > 0 else np.nan:>+15.2f}"
        print(row)

    rule()
    print("C. Wood harvest [Mha]")
    rule("-")
    print(f"{'class':<26}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for k, lab in enumerate(HLAB):
        print(f"{lab:<26}" + "".join(f"{h[s][:, k].sum():>15.3f}" for s in SCEN))
    print(f"{'TOTAL cumulative':<26}" + "".join(f"{h[s].sum():>15.3f}" for s in SCEN))
    print(f"{'mean annual':<26}" + "".join(f"{h[s].sum()/years.size:>15.4f}" for s in SCEN))
    print(f"{'2024':<26}" + "".join(f"{h[s][0].sum():>15.4f}" for s in SCEN))
    print(f"{'2100':<26}" + "".join(f"{h[s][-1].sum():>15.4f}" for s in SCEN))

    rule()
    print("D. Per-PFT area change 2024->2100 [Mha]  (PFTs with any change)")
    rule("-")
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from elm_landuse.chen_classes import ELM_PFT_NAMES
        names = list(ELM_PFT_NAMES)
    except Exception:
        names = [f"PFT{j}" for j in range(17)]
    print(f"{'j':>3} {'name':<34}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for j in range(17):
        d = [pft[s][-1, j] - pft[s][0, j] for s in SCEN]
        if max(abs(x) for x in d) < 1e-6 and max(pft[s][0, j] for s in SCEN) < 1e-6:
            continue
        print(f"{j:>3} {names[j][:34]:<34}" + "".join(f"{x:>+15.4f}" for x in d))

    rule()
    print("E. Divergence between scenarios in 2100 "
          "[mean |group %| dissimilarity, pp of natveg column]")
    rule("-")
    print(f"{'':<14}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for i, a in enumerate(SCEN):
        print(f"{SLAB[a]:<14}" + "".join(f"{D[i, j]:>15.3f}" for j in range(len(SCEN))))
    rule()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compute", action="store_true")
    ap.add_argument("--plot", action="store_true")
    a = ap.parse_args()
    if not (a.compute or a.plot):
        a.compute = a.plot = True
    if a.compute:
        compute()
    if a.plot:
        plot()


if __name__ == "__main__":
    main()
