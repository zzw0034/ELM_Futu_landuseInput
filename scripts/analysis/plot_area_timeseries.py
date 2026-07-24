#!/usr/bin/env python
"""Plot total-area time series for each ELM column from a Chen2022-derived NetCDF.

For every grid cell the spherical-Earth area is

    A(i,j) = R^2 * dlon_rad * (sin(lat_top) - sin(lat_bot))     [km^2]

The total area covered by column variable V (which is in percent) for year t
is then sum( V(t,i,j) / 100 * A(i,j) ).

Outputs a 2x3 panel figure (one panel per column variable). Most useful on a
transient (multi-year) file; see REFERENCE.md §7.

Example
-------
$PY scripts/plot_area_timeseries.py \\
    --in  outputs/processed/chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc \\
    --out outputs/figures/area_timeseries_CONUS_SSP2_RCP45_2015-2100_1_24deg.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


EARTH_RADIUS_KM = 6371.0088   # mean Earth radius (CF-suggested)

PANEL_VARS: tuple[str, ...] = (
    "PCT_NATVEG", "PCT_CROP", "PCT_LAKE",
    "PCT_URBAN", "PCT_GLACIER", "PCT_WETLAND",
)


def cell_area_km2(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Area of every (lat, lon) cell on a regular lat/lon grid, in km^2.

    Assumes `lat` and `lon` are 1-D cell-CENTER coordinates with a constant
    spacing. Returns a 2-D array of shape (len(lat), len(lon)).
    """
    if lat.ndim != 1 or lon.ndim != 1:
        raise ValueError("lat and lon must be 1-D arrays of cell centers")

    dlat = float(abs(lat[1] - lat[0]))
    dlon = float(abs(lon[1] - lon[0]))
    dlon_rad = np.deg2rad(dlon)

    lat_top = np.deg2rad(lat + 0.5 * dlat)
    lat_bot = np.deg2rad(lat - 0.5 * dlat)
    band_area = (EARTH_RADIUS_KM ** 2) * dlon_rad * (np.sin(lat_top) - np.sin(lat_bot))
    return np.broadcast_to(band_area[:, None], (lat.size, lon.size)).copy()


def total_area_per_year(ds: xr.Dataset, var: str, area_km2: np.ndarray) -> np.ndarray:
    """Return shape (time,) total area in km^2 for a column variable in percent."""
    pct = ds[var].values  # (time, lat, lon)
    return (pct / 100.0 * area_km2[None, :, :]).sum(axis=(1, 2))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="inp", required=True, help="input NetCDF")
    p.add_argument("--out", required=True, help="output figure (.png)")
    p.add_argument("--units", choices=("km2", "Mkm2"), default="Mkm2",
                   help="y-axis units (default Mkm2 = millions of km^2)")
    args = p.parse_args(argv)

    ds = xr.open_dataset(args.inp)
    years = ds["time"].values.astype(int)
    lat = ds["lat"].values
    lon = ds["lon"].values
    area = cell_area_km2(lat, lon)

    scale, ylabel = (1.0, "total area [km$^2$]") if args.units == "km2" \
        else (1e-6, "total area [million km$^2$]")

    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharex=True,
                             constrained_layout=True)
    axes = axes.ravel()

    print(f"{'variable':12s}  {'year':>6s}  total area [{args.units}]")
    for ax, v in zip(axes, PANEL_VARS):
        ts = total_area_per_year(ds, v, area) * scale
        ax.plot(years, ts, "-o", color="tab:blue", lw=1.5, ms=3)
        ax.set_title(v)
        ax.set_xlabel("year")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        for y, val in zip(years, ts):
            print(f"  {v:12s}  {int(y):>6d}  {val:.4g}")
        # Make zero-only series legible (CROP / WETLAND are flat at 0)
        if np.allclose(ts, 0.0):
            ax.set_ylim(-1, 1)
            ax.text(0.5, 0.5, "all zero", transform=ax.transAxes,
                    ha="center", va="center", color="gray")

    bbox = ds.attrs.get("bbox_lonlat", "unknown")
    fig.suptitle(f"{Path(args.inp).name}\nbbox {bbox}; cell area via spherical Earth (R={EARTH_RADIUS_KM} km)",
                 fontsize=10)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    print(f"[plot_area_timeseries] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
