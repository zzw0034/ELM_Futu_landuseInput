#!/usr/bin/env python
"""Quick-look maps from a Chen2022-derived ELM landuse NetCDF.

Plots PCT_NATVEG, PCT_CROP, PCT_URBAN, PCT_LAKE, PCT_GLACIER and the dominant
natural PFT for the first time slice (--time-index) of the input file.

Example
-------
$PY scripts/plot_elm_landuse_maps.py \\
    --in  outputs/interim/chen2022_landuse_SEUS_2015_0p5deg.nc \\
    --out outputs/figures/chen2022_landuse_SEUS_2015_0p5deg.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


def _imshow(ax, da, title, vmin=0, vmax=100, cmap="viridis"):
    extent = (float(da["lon"].min()), float(da["lon"].max()),
              float(da["lat"].min()), float(da["lat"].max()))
    im = ax.imshow(da.values, origin="lower", extent=extent,
                   vmin=vmin, vmax=vmax, cmap=cmap, aspect="auto")
    ax.set_title(title)
    ax.set_xlabel("lon")
    ax.set_ylabel("lat")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="inp", required=True, help="input NetCDF")
    p.add_argument("--out", required=True, help="output figure (.png)")
    p.add_argument("--time-index", type=int, default=0)
    args = p.parse_args(argv)

    ds = xr.open_dataset(args.inp)
    t = args.time_index

    fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
    _imshow(axes[0, 0], ds["PCT_NATVEG"].isel(time=t), "PCT_NATVEG")
    _imshow(axes[0, 1], ds["PCT_CROP"].isel(time=t), "PCT_CROP")
    _imshow(axes[0, 2], ds["PCT_URBAN"].isel(time=t), "PCT_URBAN")
    _imshow(axes[1, 0], ds["PCT_LAKE"].isel(time=t), "PCT_LAKE")
    _imshow(axes[1, 1], ds["PCT_GLACIER"].isel(time=t), "PCT_GLACIER")

    pft = ds["PCT_NAT_PFT"].isel(time=t).values  # (npft, ny, nx)
    dom = np.argmax(pft, axis=0).astype(np.float32)
    dom_da = xr.DataArray(dom, coords={"lat": ds["lat"], "lon": ds["lon"]},
                          dims=("lat", "lon"))
    _imshow(axes[1, 2], dom_da,
            f"dominant natural PFT (t={int(ds['time'].isel(time=t))})",
            vmin=0, vmax=ds.sizes["natpft"] - 1, cmap="tab20")

    fig.suptitle(Path(args.inp).name, fontsize=11)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    print(f"[plot_quicklook] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
