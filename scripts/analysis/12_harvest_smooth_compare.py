#!/usr/bin/env python
"""Compare wood-harvest fields before/after the 2026-08-28 LUH2 pre-smoothing
fix to 02_harmonize_seus.py's downscale_harvest() (see FUTURE_LANDUSE_TIMESERIES.md
sec 11.4 for the "0.25 deg blocks" this fix targets, and s4_2_donwscale_LUH2harvest.py
for the smoothing method itself).

Generic over which pair of landuse.timeseries products is being compared: the
4 SSP Default files, or the 4 per-SSP RH (reduced-harvest) files. Which one is
selected by --old-dir/--new-dir/--suffix; nothing else in the script assumes
Default vs RH.

For each SSP this produces:
  1. A per-SSP map figure comparing old vs new vs (new-old) LUT harvest
     fraction (sum of the 5 HARVEST_* vars) at --years (default 2024/2064/2100):
       fig_harvest_smooth_old_vs_new_maps_<SSP><suffix>.png
  2. One shared time-series figure (one panel per SSP) of domain-total
     harvested area [km2/yr], converted from the LUT fraction via
         HARVEST_frac * (PCT_NATVEG_static/100) * LANDFRAC_PFT * AREA[km2]
     -- the same convention 02_harmonize_seus.py records in its own
     harvest_natveg_convention file attribute:
       fig_harvest_smooth_old_vs_new_timeseries<suffix>.png

Before plotting, prints a per-SSP summary: old/new cumulative domain-total
harvested area (km2, summed 2024..last year), their relative difference, and
the largest single-gridcell-year absolute physical difference.

Usage (Default comparison, using this script's own defaults):
    12_harvest_smooth_compare.py

Usage (RH comparison):
    12_harvest_smooth_compare.py \\
        --old-dir  .../outputs/processed/harvest_scenarios/archive_pre_smoothHARV_20260828 \\
        --new-dir  .../outputs/processed/harvest_scenarios \\
        --suffix _RH --label RH

Must run under Slurm, not the login node: reading 5 HARVEST_* vars x 77 years
x 324x504 from two files per SSP is not large by itself, but doing it for all
four SSPs plus building 5 matplotlib figures in one process is exactly the
kind of "Python analysis on a login node" AGENTS.md rules out.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import netCDF4 as nc4
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
DEFAULT_OLD_DIR = ROOT / "outputs" / "processed" / "archive_pre_smoothHARV_20260828"
DEFAULT_NEW_DIR = ROOT / "outputs" / "processed"
DEFAULT_OUTDIR = ROOT / "outputs" / "figures"

ALL_SSPS = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]
HARVEST_VARS = ["HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"]
DEFAULT_MAP_YEARS = [2024, 2064, 2100]  # 2024 + 40 = 2064; 2104 is past the file's
# 2100 end year, so 2100 stands in as the last-year representative.


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--old-dir", type=Path, default=DEFAULT_OLD_DIR,
        help=f"dir with the pre-smoothing (archived) files (default: {DEFAULT_OLD_DIR})",
    )
    p.add_argument(
        "--new-dir", type=Path, default=DEFAULT_NEW_DIR,
        help=f"dir with the smoothHARV (rebuilt) files (default: {DEFAULT_NEW_DIR})",
    )
    p.add_argument(
        "--outdir", type=Path, default=DEFAULT_OUTDIR,
        help=f"dir to write figures into (default: {DEFAULT_OUTDIR})",
    )
    p.add_argument(
        "--label", default="Default",
        help="scenario label used in titles/filenames-adjacent text, e.g. Default or RH",
    )
    p.add_argument(
        "--suffix", default="",
        help="filename suffix inserted before _simyr2024-2100.nc, e.g. _RH "
             "(also used verbatim in output figure filenames)",
    )
    p.add_argument("--ssps", nargs="+", default=ALL_SSPS, choices=ALL_SSPS)
    p.add_argument("--years", nargs="+", type=int, default=DEFAULT_MAP_YEARS)
    return p.parse_args()


def file_for(dir_: Path, ssp: str, suffix: str) -> Path:
    return dir_ / f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}{suffix}_simyr2024-2100.nc"


def load_fields(path: Path) -> dict:
    """Read one landuse.timeseries file's harvest-relevant fields.

    Returns years (nt,), frac_sum (nt,ny,nx) = sum of the 5 HARVEST_* [LUT
    fraction of vegetated unit], natveg_pct (ny,nx) static PCT_NATVEG [%],
    landfrac (ny,nx) LANDFRAC_PFT [0-1], area_km2 (ny,nx) AREA [km2],
    lat (ny,), lon (nx,) 1-D coordinate vectors (SEUS grid, no further
    cropping needed -- these files are already on the SEUS target grid).
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    with nc4.Dataset(path) as ds:
        years = np.asarray(ds.variables["YEAR"][:]).astype(int)
        frac_sum = np.zeros(
            (years.size,) + ds.variables[HARVEST_VARS[0]].shape[1:], dtype=np.float64
        )
        for v in HARVEST_VARS:
            frac_sum += np.nan_to_num(np.asarray(ds.variables[v][:], dtype=np.float64))
        natveg_pct = np.nan_to_num(np.asarray(ds.variables["PCT_NATVEG"][:], dtype=np.float64))
        landfrac = np.nan_to_num(np.asarray(ds.variables["LANDFRAC_PFT"][:], dtype=np.float64))
        area_km2 = np.nan_to_num(np.asarray(ds.variables["AREA"][:], dtype=np.float64))
        lat = np.asarray(ds.variables["LATIXY"][:])[:, 0]
        lon = np.asarray(ds.variables["LONGXY"][:])[0, :]
    return dict(
        years=years, frac_sum=frac_sum, natveg_pct=natveg_pct,
        landfrac=landfrac, area_km2=area_km2, lat=lat, lon=lon,
    )


def physical_km2_per_cell_year(fields: dict) -> np.ndarray:
    """(nt,ny,nx) LUT harvest fraction -> (nt,ny,nx) physical harvested
    area [km2] per cell per year, using the convention 02_harmonize_seus.py
    records in its harvest_natveg_convention attribute: ELM recovers
    harvested area as HARVEST_frac * PCT_NATVEG_static[%]/100 * LANDFRAC_PFT
    * AREA[km2]."""
    return (
        fields["frac_sum"]
        * (fields["natveg_pct"] / 100.0)[None, :, :]
        * fields["landfrac"][None, :, :]
        * fields["area_km2"][None, :, :]
    )


def make_map_figure(ssp: str, args, old: dict, new: dict) -> Path:
    years = old["years"]
    lat, lon = old["lat"], old["lon"]
    ext = (float(lon[0]), float(lon[-1]), float(lat[0]), float(lat[-1]))
    aspect = 1.0 / np.cos(np.deg2rad(0.5 * (lat[0] + lat[-1])))  # project convention

    idx = {int(y): int(np.where(years == y)[0][0]) for y in args.years}

    vmax = max(
        float(np.nanmax(old["frac_sum"][i])) if old["frac_sum"][i].size else 0.0
        for i in idx.values()
    )
    vmax = max(
        vmax,
        *(float(np.nanmax(new["frac_sum"][i])) for i in idx.values()),
    )
    dvmax = max(
        float(np.nanmax(np.abs(new["frac_sum"][i] - old["frac_sum"][i])))
        for i in idx.values()
    )
    dvmax = max(dvmax, 1e-12)  # avoid a degenerate 0..0 diverging norm

    nrow = len(args.years)
    fig, axes = plt.subplots(
        nrow, 3, figsize=(12.5, 3.6 * nrow), constrained_layout=True, squeeze=False
    )
    col_titles = [f"old {args.label}", f"new smoothHARV {args.label}", "new - old"]
    im_seq = im_diff = None
    for r, y in enumerate(args.years):
        i = idx[y]
        o = old["frac_sum"][i]
        n = new["frac_sum"][i]
        d = n - o
        for c, (field, cmap, vmin_, vmax_) in enumerate(
            [(o, "YlOrBr", 0.0, vmax), (n, "YlOrBr", 0.0, vmax), (d, "RdBu_r", -dvmax, dvmax)]
        ):
            ax = axes[r][c]
            im = ax.imshow(field, origin="lower", extent=ext, cmap=cmap,
                            vmin=vmin_, vmax=vmax_, interpolation="nearest")
            ax.set_aspect(aspect)
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(col_titles[c], fontsize=11)
            if c == 0:
                ax.set_ylabel(f"{y}", fontsize=11)
            if c < 2:
                im_seq = im
            else:
                im_diff = im
        # sum/max text annotations, matching the s4_2 orig-vs-smoothHARV precedent
        axes[r][0].text(
            0.02, 0.02, f"sum={float(np.nansum(o)):.2f}\nmax={float(np.nanmax(o)):.3f}",
            transform=axes[r][0].transAxes, fontsize=7, va="bottom", ha="left",
            bbox={"facecolor": "white", "edgecolor": "0.7", "alpha": 0.85, "pad": 2},
        )
        axes[r][1].text(
            0.02, 0.02, f"sum={float(np.nansum(n)):.2f}\nmax={float(np.nanmax(n)):.3f}",
            transform=axes[r][1].transAxes, fontsize=7, va="bottom", ha="left",
            bbox={"facecolor": "white", "edgecolor": "0.7", "alpha": 0.85, "pad": 2},
        )
    fig.colorbar(im_seq, ax=axes[:, :2], shrink=0.8,
                 label="Σ HARVEST_* [LUT fraction of vegetated unit]")
    fig.colorbar(im_diff, ax=axes[:, 2], shrink=0.8,
                 label="Δ Σ HARVEST_* [LUT fraction]")
    fig.suptitle(
        f"{ssp}: {args.label} wood-harvest LUT fraction (Σ of 5 HARVEST_* vars), "
        f"pre- vs post-smoothing LUH2 downscale",
        fontsize=12,
    )
    out = args.outdir / f"fig_harvest_smooth_old_vs_new_maps_{ssp}{args.suffix}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def make_timeseries_figure(ts_data: dict, args) -> Path:
    ssps = list(ts_data.keys())
    ncol = 2 if len(ssps) > 1 else 1
    nrow = int(np.ceil(len(ssps) / ncol))
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(6.5 * ncol, 4.0 * nrow), constrained_layout=True, squeeze=False
    )
    for k, ssp in enumerate(ssps):
        r, c = divmod(k, ncol)
        ax = axes[r][c]
        years, old_km2, new_km2 = ts_data[ssp]
        ax.plot(years, old_km2, label=f"old {args.label}", color="0.35", lw=1.6)
        ax.plot(years, new_km2, label=f"new smoothHARV {args.label}", color="#c1440e", lw=1.6)
        ax.set_title(ssp, fontsize=11)
        ax.set_xlabel("year")
        ax.set_ylabel("domain-total harvested area [km2/yr]")
        ax.legend(fontsize=8)
    for k in range(len(ssps), nrow * ncol):
        r, c = divmod(k, ncol)
        axes[r][c].axis("off")
    fig.suptitle(
        f"{args.label} domain-total wood harvest, old vs new smoothHARV LUH2\n"
        f"(area-weighted: HARVEST_* × PCT_NATVEG_static/100 × LANDFRAC_PFT × AREA)",
        fontsize=12,
    )
    out = args.outdir / f"fig_harvest_smooth_old_vs_new_timeseries{args.suffix}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    print(f"[compare] label={args.label!r} suffix={args.suffix!r}")
    print(f"[compare] old-dir={args.old_dir}")
    print(f"[compare] new-dir={args.new_dir}")
    print(f"[compare] map years={args.years}")

    ts_data = {}
    for ssp in args.ssps:
        old_path = file_for(args.old_dir, ssp, args.suffix)
        new_path = file_for(args.new_dir, ssp, args.suffix)
        old = load_fields(old_path)
        new = load_fields(new_path)

        if not np.array_equal(old["years"], new["years"]):
            raise RuntimeError(f"{ssp}: YEAR differs between old and new -- not comparable")
        if old["frac_sum"].shape != new["frac_sum"].shape:
            raise RuntimeError(f"{ssp}: grid shape differs between old and new -- not comparable")

        old_km2_cell = physical_km2_per_cell_year(old)
        new_km2_cell = physical_km2_per_cell_year(new)
        old_km2 = old_km2_cell.sum(axis=(1, 2))
        new_km2 = new_km2_cell.sum(axis=(1, 2))
        ts_data[ssp] = (old["years"], old_km2, new_km2)

        old_cum = float(old_km2.sum())
        new_cum = float(new_km2.sum())
        rel = (new_cum - old_cum) / old_cum if old_cum else float("nan")
        max_abs = float(np.nanmax(np.abs(new_km2_cell - old_km2_cell)))
        print(
            f"[{args.label}] {ssp}: old_total={old_cum:,.1f} km2 "
            f"({int(old['years'][0])}-{int(old['years'][-1])} cumulative)  "
            f"new_total={new_cum:,.1f} km2  rel_diff={rel:+.4%}  "
            f"max|delta per-cell-year|={max_abs:.4f} km2"
        )

        map_out = make_map_figure(ssp, args, old, new)
        print(f"  wrote {map_out}")

    ts_out = make_timeseries_figure(ts_data, args)
    print(f"wrote {ts_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
