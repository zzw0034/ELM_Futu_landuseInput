#!/usr/bin/env python
"""Compare our SEUS landuse.timeseries to the E3SM 0.5 deg RCP8.5 file.

Reference (LUH2 via mksurfdata, global 0.5 deg, cropped to SEUS):
  /projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/surfdata_map/
    landuse.timeseries_0.5x0.5_rcp8.5_simyr2015-2100_c191004.nc

Ours: 1/24 deg SEUS, 2024-2100. Pairing is SSP5-RCP8.5 <-> rcp8.5.
Other SSPs are drawn on the trajectory panel only, to show scenario spread
vs the product gap.

Aggregation direction: ours is coarsened UP to 0.5 deg (12 x 12 fine cells,
area-weighted on p(j) = PCT_NATVEG * PCT_NAT_PFT(j)/100). The 0.5 deg file
is never interpolated down. Fine cells nest on the 0.5 deg edges
(24.0-37.5 N, 95-74 W).

Stage 1 (--compute) writes a small npz; stage 2 (--plot) draws figures.
Default runs both.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr
from netCDF4 import Dataset
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
PROC = ROOT / "outputs" / "processed"
OUTDIR = ROOT / "outputs"
NPZ = OUTDIR / "interim" / "compare_halfdeg_rcp85.npz"
STEM = "landuse.timeseries_SEUS_1_24deg_nlcd2elm_%s_simyr2024-2100.nc"
REF = Path(
    "/projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/surfdata_map/"
    "landuse.timeseries_0.5x0.5_rcp8.5_simyr2015-2100_c191004.nc"
)

OURS_SSP5 = "SSP5_RCP85"
SCEN = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]
SLAB = {
    "SSP1_RCP19": "ours SSP1-1.9",
    "SSP2_RCP45": "ours SSP2-4.5",
    "SSP3_RCP70": "ours SSP3-7.0",
    "SSP5_RCP85": "ours SSP5-8.5",
    "REF": "E3SM 0.5° RCP8.5",
}
SCOL = {
    "SSP1_RCP19": "#1a9850",
    "SSP2_RCP45": "#2c7fb8",
    "SSP3_RCP70": "#7b3294",
    "SSP5_RCP85": "#d73027",
    "REF": "#000000",
}

# Same groups as 02_harmonize_seus.py. PFT 16 (irrigated) is structurally 0
# on our side; on the 0.5 deg file it is folded into Crop if present.
GROUPS = {
    "Bare": [0],
    "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
    "Shrub": [9, 10, 11],
    "Grass": [12, 13, 14],
    "Crop": [15, 16],
}
GN = list(GROUPS)
NG = len(GN)
BLOCK = 12
LAT0, LAT1, LON0, LON1 = 24.0, 37.5, -95.0, -74.0
MHA = 1e4  # km^2 -> Mha


def _block_sum(a, by=BLOCK, bx=BLOCK):
    """Sum the last two axes in by x bx blocks. a: (..., ny, nx)."""
    *lead, ny, nx = a.shape
    if ny % by or nx % bx:
        raise ValueError(f"grid {ny}x{nx} is not divisible by {by}x{bx}")
    return a.reshape(*lead, ny // by, by, nx // bx, bx).sum(axis=(-3, -1))


def _seus_window(lat, lon):
    """Keep 0.5 deg cells whose edges lie in [LAT0, LAT1] x [LON0, LON1]."""
    dlat = float(np.median(np.diff(lat)))
    dlon = float(np.median(np.diff(lon)))
    lat_ok = (lat - 0.5 * dlat >= LAT0 - 1e-9) & (lat + 0.5 * dlat <= LAT1 + 1e-9)
    lon_ok = (lon - 0.5 * dlon >= LON0 - 1e-9) & (lon + 0.5 * dlon <= LON1 + 1e-9)
    ia = np.where(lat_ok)[0]
    ja = np.where(lon_ok)[0]
    return ia[0], ia[-1] + 1, ja[0], ja[-1] + 1


def compute() -> None:
    ours0 = xr.open_dataset(PROC / (STEM % OURS_SSP5), decode_times=False)
    years = ours0.YEAR.values.astype(int)
    lat_f = ours0.LATIXY.values[:, 0]
    lon_f = ours0.LONGXY.values[0, :]
    area_f = np.nan_to_num(ours0.AREA.values.astype(np.float64))
    lfrac_f = np.nan_to_num(ours0.LANDFRAC_PFT.values.astype(np.float64))
    natveg_f = np.nan_to_num(ours0.PCT_NATVEG.values.astype(np.float64))
    w_f = area_f * lfrac_f
    nv_f = w_f * natveg_f / 100.0
    ny, nx = natveg_f.shape
    nyr = years.size
    ours0.close()

    lat_c = _block_sum(lat_f[:, None] * np.ones_like(lon_f)[None, :]) / BLOCK**2
    lat_c = lat_c[:, 0]
    lon_c = _block_sum(lon_f[None, :] * np.ones_like(lat_f)[:, None]) / BLOCK**2
    lon_c = lon_c[0, :]
    nlat_c, nlon_c = lat_c.size, lon_c.size
    print(f"ours fine {ny}x{nx}  ->  coarse {nlat_c}x{nlon_c}  "
          f"lat {lat_c[0]:.4f}..{lat_c[-1]:.4f}  lon {lon_c[0]:.4f}..{lon_c[-1]:.4f}")
    print(f"years {years[0]}-{years[-1]} ({nyr})")
    print(f"ours fine natveg {nv_f.sum()/MHA:.3f} Mha")

    # --- reference 0.5 deg, cropped (netCDF4 so the 3.9 GB file is sliced on disk) ---
    ref = Dataset(REF)
    rlat = np.asarray(ref.variables["LATIXY"][:, 0], dtype=np.float64)
    rlon = np.asarray(ref.variables["LONGXY"][0, :], dtype=np.float64)
    i0, i1, j0, j1 = _seus_window(rlat, rlon)
    rlat_s, rlon_s = rlat[i0:i1], rlon[j0:j1]
    print(f"ref crop {rlat_s.size}x{rlon_s.size}  "
          f"lat {rlat_s[0]:.4f}..{rlat_s[-1]:.4f}  "
          f"lon {rlon_s[0]:.4f}..{rlon_s[-1]:.4f}  "
          f"index lat {i0}:{i1} lon {j0}:{j1}")
    if rlat_s.size != nlat_c or rlon_s.size != nlon_c:
        raise RuntimeError("coarse ours and ref SEUS windows have different shapes")
    if not (np.allclose(rlat_s, lat_c, atol=1e-4) and np.allclose(rlon_s, lon_c, atol=1e-4)):
        print("WARNING: coarse-center mismatch vs ref "
              f"max|dlat|={np.abs(rlat_s-lat_c).max():.4g}  "
              f"max|dlon|={np.abs(rlon_s-lon_c).max():.4g}")
    else:
        print("coarse centers match ref to 1e-4 deg")

    r_area = np.nan_to_num(np.asarray(ref.variables["AREA"][i0:i1, j0:j1], dtype=np.float64))
    r_lfrac = np.nan_to_num(np.asarray(ref.variables["LANDFRAC_PFT"][i0:i1, j0:j1], dtype=np.float64))
    r_natveg = np.nan_to_num(np.asarray(ref.variables["PCT_NATVEG"][i0:i1, j0:j1], dtype=np.float64))
    if "PCT_CROP" in ref.variables:
        r_crop_col = np.nan_to_num(np.asarray(ref.variables["PCT_CROP"][i0:i1, j0:j1], dtype=np.float64))
    else:
        r_crop_col = np.zeros_like(r_natveg)
    r_w = r_area * r_lfrac
    r_nv = r_w * r_natveg / 100.0
    r_crop_km2 = r_w * r_crop_col / 100.0
    r_year = np.asarray(ref.variables["YEAR"][:], dtype=int)
    r_idx = {int(y): k for k, y in enumerate(r_year)}
    missing = [int(y) for y in years if int(y) not in r_idx]
    if missing:
        raise RuntimeError(f"ref missing years {missing[:8]}...")
    print(f"ref crop natveg {r_nv.sum()/MHA:.3f} Mha  "
          f"PCT_CROP column {r_crop_km2.sum()/MHA:.3f} Mha")

    # --- aggregate ours (static natveg) ---
    ours_nv_c = _block_sum(nv_f)
    ours_w_c = _block_sum(w_f)
    ours_natveg_c = np.where(ours_w_c > 0, 100.0 * ours_nv_c / ours_w_c, 0.0)
    print(f"ours coarse natveg {ours_nv_c.sum()/MHA:.3f} Mha  "
          f"(fine conserved: {np.isclose(ours_nv_c.sum(), nv_f.sum())})")

    out = dict(
        years=years, lat=lat_c, lon=lon_c,
        gnames=np.array(GN), scen=np.array(SCEN),
        ours_natveg_pct=ours_natveg_c.astype(np.float32),
        ref_natveg_pct=r_natveg.astype(np.float32),
        ours_nv_km2=ours_nv_c, ref_nv_km2=r_nv,
        ref_crop_col_km2=r_crop_km2,
        ours_w=ours_w_c, ref_w=r_w,
    )

    # per-scenario group/PFT area on the coarse grid (SSP5 also keeps maps)
    for s in SCEN:
        f = PROC / (STEM % s)
        print(f"\n== coarsen {s}", flush=True)
        ds = xr.open_dataset(f, decode_times=False)
        g_km2 = np.zeros((nyr, NG))
        pft_km2 = np.zeros((nyr, 17))
        gmap = np.zeros((2, NG, nlat_c, nlon_c))          # % of natveg
        pcell = np.zeros((2, NG, nlat_c, nlon_c))         # % of cell
        for t in range(nyr):
            p = np.nan_to_num(ds.PCT_NAT_PFT.isel(time=t).values.astype(np.float64))
            pft_area = p / 100.0 * nv_f[None]
            pft_c = _block_sum(pft_area)
            if t == 0 and s == OURS_SSP5:
                print(f"   conservation fine vs coarse PFT area km2: "
                      f"{pft_area.sum():.4f} vs {pft_c.sum():.4f}")
            pft_km2[t] = pft_c.sum(axis=(1, 2))
            gstack_area = np.stack([pft_c[GROUPS[g]].sum(axis=0) for g in GN])
            g_km2[t] = gstack_area.sum(axis=(1, 2))
            g_pct = np.where(ours_nv_c[None] > 0, 100.0 * gstack_area / ours_nv_c[None], 0.0)
            g_cell = np.where(ours_w_c[None] > 0, 100.0 * gstack_area / ours_w_c[None], 0.0)
            if t == 0:
                gmap[0], pcell[0] = g_pct, g_cell
            if t == nyr - 1:
                gmap[1], pcell[1] = g_pct, g_cell
            if t % 20 == 0:
                print(f"   t={t} {years[t]}", flush=True)
        ds.close()
        out[f"g_km2_{s}"] = g_km2
        out[f"pft_km2_{s}"] = pft_km2
        out[f"gmap_{s}"] = gmap.astype(np.float32)
        out[f"pcell_{s}"] = pcell.astype(np.float32)
        print(f"   Tree {g_km2[0, 1]/MHA:.3f} -> {g_km2[-1, 1]/MHA:.3f} Mha")

    # --- reference time series + maps, same years ---
    print("\n== ref 0.5 deg", flush=True)
    g_km2 = np.zeros((nyr, NG))
    pft_km2 = np.zeros((nyr, 17))
    gmap = np.zeros((2, NG, nlat_c, nlon_c))
    pcell = np.zeros((2, NG, nlat_c, nlon_c))
    for t, y in enumerate(years):
        k = r_idx[int(y)]
        p = np.nan_to_num(np.asarray(
            ref.variables["PCT_NAT_PFT"][k, :, i0:i1, j0:j1], dtype=np.float64
        ))
        pft_area = p / 100.0 * r_nv[None]
        pft_km2[t] = pft_area.sum(axis=(1, 2))
        gstack_area = np.stack([pft_area[GROUPS[g]].sum(axis=0) for g in GN])
        gstack_cell = gstack_area.copy()
        gstack_cell[GN.index("Crop")] = gstack_cell[GN.index("Crop")] + r_crop_km2
        g_km2[t] = gstack_cell.sum(axis=(1, 2))
        g_pct = np.where(r_nv[None] > 0, 100.0 * gstack_area / r_nv[None], 0.0)
        g_cell = np.where(r_w[None] > 0, 100.0 * gstack_cell / r_w[None], 0.0)
        if t == 0:
            gmap[0], pcell[0] = g_pct, g_cell
        if t == nyr - 1:
            gmap[1], pcell[1] = g_pct, g_cell
        if t % 20 == 0:
            print(f"   t={t} {y}", flush=True)
    ref.close()
    out["g_km2_REF"] = g_km2
    out["pft_km2_REF"] = pft_km2
    out["gmap_REF"] = gmap.astype(np.float32)
    out["pcell_REF"] = pcell.astype(np.float32)
    print(f"   Tree {g_km2[0, 1]/MHA:.3f} -> {g_km2[-1, 1]/MHA:.3f} Mha")

    NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(NPZ, **out)
    print(f"\nwrote {NPZ}")


def _load():
    with np.load(NPZ, allow_pickle=True) as z:
        return {k: np.asarray(z[k]) for k in z.files}


def _print_tables(Z) -> None:
    years = Z["years"]
    print("\n" + "=" * 88)
    print("A. Static PCT_NATVEG over SEUS [Mha of natveg]")
    print("-" * 88)
    ours = float(Z["ours_nv_km2"].sum() / MHA)
    refn = float(Z["ref_nv_km2"].sum() / MHA)
    print(f"  ours (aggregated to 0.5°)  {ours:8.3f}")
    print(f"  E3SM 0.5° RCP8.5 crop      {refn:8.3f}")
    print(f"  Chen/NLCD - E3SM           {ours-refn:+8.3f}  ({100*(ours-refn)/refn:+.1f}%)")
    crop_col = float(Z["ref_crop_col_km2"].sum() / MHA)
    print(f"  ref PCT_CROP column (added into Crop group below) {crop_col:.3f} Mha")

    print("\n" + "=" * 88)
    print("B. Functional-group area [Mha]  (natveg * group share; ref Crop includes PCT_CROP)")
    print("-" * 88)
    hdr = f"{'group':<8} {'2024 ours':>10} {'2024 ref':>10} {'d2024':>8}  " \
          f"{'2100 ours':>10} {'2100 ref':>10} {'d2100':>8}  " \
          f"{'Δours':>8} {'Δref':>8}"
    print(hdr)
    g5 = Z[f"g_km2_{OURS_SSP5}"] / MHA
    gr = Z["g_km2_REF"] / MHA
    for gi, gname in enumerate(GN):
        o0, o1 = g5[0, gi], g5[-1, gi]
        r0, r1 = gr[0, gi], gr[-1, gi]
        print(f"{gname:<8} {o0:10.3f} {r0:10.3f} {o0-r0:+8.2f}  "
              f"{o1:10.3f} {r1:10.3f} {o1-r1:+8.2f}  "
              f"{o1-o0:+8.2f} {r1-r0:+8.2f}")
    print(f"{'TOTAL':<8} {g5[0].sum():10.3f} {gr[0].sum():10.3f} "
          f"{g5[0].sum()-gr[0].sum():+8.2f}  "
          f"{g5[-1].sum():10.3f} {gr[-1].sum():10.3f} "
          f"{g5[-1].sum()-gr[-1].sum():+8.2f}")

    print("\n" + "=" * 88)
    print("C. Per-PFT area 2024 and 2100, ours SSP5 vs ref [Mha]  (PFTs with >0.05 Mha either side)")
    print("-" * 88)
    p5 = Z[f"pft_km2_{OURS_SSP5}"] / MHA
    pr = Z["pft_km2_REF"] / MHA
    print(f"{'j':>3} {'2024 ours':>10} {'2024 ref':>10} {'2100 ours':>10} {'2100 ref':>10} "
          f"{'Δours':>8} {'Δref':>8}")
    for j in range(17):
        if max(p5[0, j], pr[0, j], p5[-1, j], pr[-1, j]) < 0.05:
            continue
        print(f"{j:3d} {p5[0, j]:10.3f} {pr[0, j]:10.3f} {p5[-1, j]:10.3f} {pr[-1, j]:10.3f} "
              f"{p5[-1, j]-p5[0, j]:+8.2f} {pr[-1, j]-pr[0, j]:+8.2f}")
    print(f"(years {int(years[0])} -> {int(years[-1])})")


def plot() -> None:
    Z = _load()
    _print_tables(Z)
    years = Z["years"]
    lat, lon = Z["lat"], Z["lon"]
    ext = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    figdir = OUTDIR / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    mask = Z["ours_nv_km2"] > 0
    mask_r = Z["ref_nv_km2"] > 0

    g = {s: Z[f"g_km2_{s}"] / MHA for s in SCEN}
    g["REF"] = Z["g_km2_REF"] / MHA

    # ---- fig 1: trajectories ----
    fig = plt.figure(figsize=(18, 5.2))
    gs = GridSpec(1, 5, figure=fig, wspace=0.32)
    for gi, gname in enumerate(GN):
        ax = fig.add_subplot(gs[0, gi])
        for s in SCEN:
            lw = 2.4 if s == OURS_SSP5 else 1.3
            ax.plot(years, g[s][:, gi], color=SCOL[s], lw=lw, label=SLAB[s],
                    alpha=1.0 if s == OURS_SSP5 else 0.7)
        ax.plot(years, g["REF"][:, gi], color=SCOL["REF"], lw=2.2, ls="--",
                label=SLAB["REF"])
        ax.set_title(gname, fontsize=12)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25, lw=0.5)
        if gi == 0:
            ax.set_ylabel("SEUS area [Mha]", fontsize=9)
            ax.legend(fontsize=6.5, loc="best")
    fig.suptitle("SEUS functional-group area, 2024-2100\n"
                 "solid: ours at 0.5° (SSP5 bold)   dashed: E3SM 0.5° RCP8.5",
                 fontsize=13, y=1.04)
    p1 = figdir / "fig_cmp_halfdeg_trajectory.png"
    fig.savefig(p1, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p1}")

    # ---- fig 2: static NATVEG ----
    fig, axs = plt.subplots(1, 3, figsize=(14.5, 4.2), constrained_layout=True)
    nv_o = np.where(mask, Z["ours_natveg_pct"], np.nan)
    nv_r = np.where(mask_r, Z["ref_natveg_pct"], np.nan)
    dnv = np.where(mask | mask_r, Z["ours_natveg_pct"] - Z["ref_natveg_pct"], np.nan)
    im0 = axs[0].imshow(nv_o, origin="lower", extent=ext, cmap="YlGn", vmin=0, vmax=100,
                        interpolation="nearest")
    axs[0].set_title("ours SSP5  PCT_NATVEG % of cell")
    im1 = axs[1].imshow(nv_r, origin="lower", extent=ext, cmap="YlGn", vmin=0, vmax=100,
                        interpolation="nearest")
    axs[1].set_title("E3SM 0.5° RCP8.5  PCT_NATVEG % of cell")
    vmax = np.nanpercentile(np.abs(dnv), 98)
    vmax = max(float(vmax), 5.0)
    im2 = axs[2].imshow(dnv, origin="lower", extent=ext, cmap="BrBG",
                        norm=TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax),
                        interpolation="nearest")
    axs[2].set_title("ours − E3SM")
    for ax in axs:
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im0, ax=axs[0], shrink=0.78, label="%")
    fig.colorbar(im1, ax=axs[1], shrink=0.78, label="%")
    fig.colorbar(im2, ax=axs[2], shrink=0.78, label="pp")
    fig.suptitle("Static PCT_NATVEG on the 0.5° SEUS grid", fontsize=13)
    p2 = figdir / "fig_cmp_halfdeg_natveg.png"
    fig.savefig(p2, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p2}")

    # ---- fig 3: Tree / Grass / Crop  % of cell, 2024 | 2100 | Δ ----
    rows = [("Tree", 1), ("Grass", 3), ("Crop", 4)]
    fig = plt.figure(figsize=(17.5, 11.0))
    gs = GridSpec(len(rows), 8, figure=fig,
                  width_ratios=[1, 1, 1, 1, 1, 1, 0.05, 0.05],
                  hspace=0.22, wspace=0.08)
    p5 = Z[f"pcell_{OURS_SSP5}"]
    pr = Z["pcell_REF"]
    for ri, (name, gi) in enumerate(rows):
        a24, a00 = p5[0, gi], p5[1, gi]
        b24, b00 = pr[0, gi], pr[1, gi]
        da, db = a00 - a24, b00 - b24
        vmax_s = max(np.nanpercentile(np.abs(np.stack([a24, a00, b24, b00])), 98), 5)
        vmax_d = max(np.nanpercentile(np.abs(np.stack([da, db])), 98), 1)
        panels = [
            (a24, f"ours 2024 {name}", "YlGn", 0, vmax_s),
            (b24, f"E3SM 2024 {name}", "YlGn", 0, vmax_s),
            (a00, f"ours 2100 {name}", "YlGn", 0, vmax_s),
            (b00, f"E3SM 2100 {name}", "YlGn", 0, vmax_s),
            (da, f"ours Δ {name}", "BrBG", -vmax_d, vmax_d),
            (db, f"E3SM Δ {name}", "BrBG", -vmax_d, vmax_d),
        ]
        ims = []
        for ci, (field, title, cmap, vmin, vmax) in enumerate(panels):
            ax = fig.add_subplot(gs[ri, ci])
            kw = dict(origin="lower", extent=ext, cmap=cmap, interpolation="nearest")
            if cmap == "BrBG":
                im = ax.imshow(np.where(mask | mask_r, field, np.nan),
                               norm=TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax), **kw)
            else:
                im = ax.imshow(np.where(mask | mask_r, field, np.nan),
                               vmin=vmin, vmax=vmax, **kw)
            ax.set_title(title, fontsize=8)
            ax.set_xticks([]); ax.set_yticks([])
            ims.append(im)
        fig.colorbar(ims[0], cax=fig.add_subplot(gs[ri, 6]), label="% of cell")
        fig.colorbar(ims[-1], cax=fig.add_subplot(gs[ri, 7]), label="Δ pp")
    fig.suptitle("Group cover as % of the 0.5° cell  (ours SSP5-8.5 vs E3SM RCP8.5)\n"
                 "Δ = 2100 − 2024", fontsize=13, y=0.995)
    p3 = figdir / "fig_cmp_halfdeg_groups.png"
    fig.savefig(p3, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {p3}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compute", action="store_true")
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()
    run_all = not args.compute and not args.plot
    if args.compute or run_all:
        compute()
    if args.plot or run_all:
        plot()


if __name__ == "__main__":
    main()
