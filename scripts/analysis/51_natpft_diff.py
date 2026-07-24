#!/usr/bin/env python
"""Where do the two products' PCT_NAT_PFT (composition within natveg) differ?

PCT_NAT_PFT is % within the natveg column, 17 PFTs, sums to 100 in both files.
Raw per-PFT differences are inflated by the known 50/50 convention artifacts
(NLCD shrub 9==10; Chen grass 13/14; NLCD C4 cap) -- REFERENCE.md 11/12.5 --
so we quantify at two levels:

  * raw 17-PFT      : dissimilarity over all 17 (artifact-inflated)
  * functional group: Bare/Tree/Shrub/Grass/Crop (meaningful)

Per-cell dissimilarity  D = 0.5 * sum_k |chen_k - nlcd_k|   (0..100),
= the % of the natveg column assigned to different classes between products.

Composition is only meaningful where there is natveg, so cells are masked to
CONUS AND min(natveg_nlcd, natveg_chen) > NATVEG_MIN.
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
NATVEG_MIN = 5.0  # % of cell; below this the composition is noise

GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
          "Shrub": [9, 10, 11], "Grass": [12, 13, 14], "Crop": [15, 16]}
GN = list(GROUPS)


def cell_area_km2(lat, lon):
    dlat = float(np.mean(np.diff(lat))); dlon = float(np.mean(np.diff(lon)))
    ln = np.radians(lat + dlat/2); ls = np.radians(lat - dlat/2)
    band = R**2 * np.radians(dlon) * (np.sin(ln) - np.sin(ls))
    return np.repeat(band[:, None], lon.size, axis=1)


def load(ds, var, yrs, yr):
    i = int(np.where(yrs == yr)[0][0])
    return np.nan_to_num(ds[var].isel(time=i).values.astype(np.float64))


def group_stack(pft):
    """pft: (17, lat, lon) -> (5, lat, lon) group shares."""
    return np.stack([pft[GROUPS[g]].sum(axis=0) for g in GN])


def main():
    nl = xr.open_dataset(NL); ch = xr.open_dataset(CH)
    lat = nl.lat.values; lon = nl.lon.values
    area = cell_area_km2(lat, lon)
    nl_yrs = nl.time.dt.year.values; ch_yrs = ch.time.values.astype(int)

    lines = []
    def emit(s=""):
        print(s); lines.append(s)

    # CONUS mask (script 30 definition)
    nv15 = load(nl, "PCT_NATVEG", nl_yrs, 2015)
    ur15 = nl.PCT_URBAN.isel(time=int(np.where(nl_yrs == 2015)[0][0])).values.sum(axis=0)
    conus = (nv15 + ur15) > 0.0

    emit("="*74)
    emit("PCT_NAT_PFT dissimilarity  Chen(SSP1-RCP1.9) vs NLCD  [% of natveg column]")
    emit("  D = 0.5*sum|chen-nlcd|  (0..100). masked to CONUS & both natveg>%g%%" % NATVEG_MIN)
    emit("="*74)

    store = {}
    for yr in (2015, 2020):
        nv_nl = load(nl, "PCT_NATVEG", nl_yrs, yr)
        nv_ch = load(ch, "PCT_NATVEG", ch_yrs, yr)
        pf_nl = load(nl, "PCT_NAT_PFT", nl_yrs, yr)
        pf_ch = load(ch, "PCT_NAT_PFT", ch_yrs, yr)

        m = conus & (np.minimum(nv_nl, nv_ch) > NATVEG_MIN)
        # renormalize composition defensively to 100 within natveg
        def norm(p):
            s = p.sum(axis=0); s[s == 0] = 1.0
            return p / s[None] * 100.0
        pf_nl = norm(pf_nl); pf_ch = norm(pf_ch)

        g_nl = group_stack(pf_nl); g_ch = group_stack(pf_ch)

        d17 = 0.5 * np.abs(pf_ch - pf_nl).sum(axis=0)
        dgr = 0.5 * np.abs(g_ch - g_nl).sum(axis=0)
        d17 = np.where(m, d17, np.nan); dgr = np.where(m, dgr, np.nan)

        # weight by natveg area (NLCD side)
        w = (area * nv_nl / 100.0)[m]
        emit(f"----- {yr} -----   ({int(m.sum()):,} composition-valid cells)")
        emit(f"  natveg-area-weighted mean dissimilarity:  group {np.average(dgr[m], weights=w):5.2f}%"
             f"   raw17 {np.average(d17[m], weights=w):5.2f}%   "
             f"(raw17 inflated by the 50/50 conventions)")
        emit(f"  group D percentiles p50 p75 p90 p95 p99: "
             + "  ".join(f"{v:.1f}" for v in np.percentile(dgr[m], [50, 75, 90, 95, 99])))
        emit("  group D threshold     cells   %of-valid")
        for thr in (5, 10, 20, 30, 50):
            mm = dgr[m] > thr
            emit(f"    > {thr:>3d}%           {int(mm.sum()):>9,}   {mm.mean()*100:6.2f}%")
        # per-group signed contribution (area-weighted mean of chen-nlcd share)
        emit("  per-group share of natveg [%], area-weighted mean:")
        emit(f"    {'group':<7} {'NLCD':>7} {'Chen':>7} {'Chen-NLCD':>10}")
        for k, g in enumerate(GN):
            a = np.average(g_nl[k][m], weights=w); b = np.average(g_ch[k][m], weights=w)
            emit(f"    {g:<7} {a:>7.2f} {b:>7.2f} {b-a:>+10.2f}")
        emit("")
        store[yr] = dict(dgr=dgr, d17=d17, g_nl=g_nl, g_ch=g_ch, m=m)

    # ---- figure 1: dissimilarity maps (group vs raw17) x (2015,2020) ----
    fig, ax = plt.subplots(2, 2, figsize=(13, 7.2), layout="constrained")
    for r, yr in enumerate((2015, 2020)):
        for c, (key, ttl) in enumerate([("dgr", "group"), ("d17", "raw 17-PFT")]):
            a = ax[r, c]
            im = a.imshow(store[yr][key], origin="lower", extent=EXTENT,
                          cmap="magma_r", vmin=0, vmax=60, interpolation="nearest")
            a.set_title(f"composition dissimilarity D ({ttl}) {yr}", fontsize=10)
            a.set_xticks([]); a.set_yticks([]); fig.colorbar(im, ax=a, shrink=0.7)
    fig.suptitle("PCT_NAT_PFT: where the composition within natveg differs "
                 "(Chen SSP1-RCP1.9 vs NLCD)\nD = % of the natveg column assigned to "
                 "different classes; raw-17 inflated by 50/50 conventions", fontsize=12)
    f1 = OUTDIR / "figures" / "fig_natpft_dissimilarity_ssp1.png"
    fig.savefig(f1, dpi=130); plt.close(fig)
    emit(f"wrote {f1}")

    # ---- figure 2: per-group signed difference (2015) ----
    fig, ax = plt.subplots(2, 3, figsize=(16, 8), layout="constrained")
    axf = ax.ravel()
    st = store[2015]
    norm = TwoSlopeNorm(vmin=-40, vcenter=0, vmax=40)
    for k, g in enumerate(GN):
        d = np.where(st["m"], st["g_ch"][k] - st["g_nl"][k], np.nan)
        a = axf[k]
        im = a.imshow(d, origin="lower", extent=EXTENT, cmap="RdBu_r", norm=norm,
                      interpolation="nearest")
        a.set_title(f"{g}: Chen-NLCD share of natveg [pp] 2015", fontsize=10)
        a.set_xticks([]); a.set_yticks([]); fig.colorbar(im, ax=a, shrink=0.7)
    axf[5].axis("off")
    fig.suptitle("PCT_NAT_PFT by functional group: Chen SSP1-RCP1.9 - NLCD "
                 "(share of natveg column), 2015", fontsize=12)
    f2 = OUTDIR / "figures" / "fig_natpft_groupdiff_ssp1_2015.png"
    fig.savefig(f2, dpi=130); plt.close(fig)
    emit(f"wrote {f2}")

    txt = OUTDIR / "interim" / "natpft_diff_nlcd_vs_chen_ssp1.txt"
    txt.write_text("\n".join(lines) + "\n")
    print(f"wrote {txt}")
    nl.close(); ch.close()


if __name__ == "__main__":
    main()
