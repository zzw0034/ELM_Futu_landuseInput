#!/usr/bin/env python
"""Build the raster arrays used by the comparison figures.

The *statistics* (script 20) are computed at each product's native resolution.
Maps are a different problem: 160000 x 105000 cannot be drawn, and a
difference map needs both products on one grid. So this script produces a
common **display grid** and is explicit about it:

  display grid = NLCD's own Albers CRS, decimated by exactly 40 -> 1200 m,
                 4000 x 2625 (40 divides both 160000 and 105000 exactly, so
                 every display cell is a clean 40x40 block of native pixels)

  * NLCD  : exact per-class counts of the 40x40 native block. No resampling
            filter is involved -- every 30 m pixel is counted. Yields both the
            majority class and the true sub-grid class fractions.
  * Chen  : 1 km EASE-Grid warped to the same 1200 m Albers grid (per-class
            indicator + Resampling.average -> fractions; both grids are
            equal-area so the average is the areal fraction).

Native resolution is preserved where it matters and where it can be seen: the
zoom panels (script 22) read both products at full native resolution over a
small window, with no decimation at all.

Writes outputs/interim/landcover_map_data.npz.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from elm_landuse.common_legend import (  # noqa: E402
    CHEN_NODATA,
    CHEN_TO_COMMON,
    COMMON_CLASSES,
    COMMON_NODATA,
    chen_lut,
    nlcd_lut,
)
from elm_landuse.raster_io import find_tif  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

_stats = import_module("20_landcover_native_stats")
nlcd_path = _stats.nlcd_path
build_conus_mask_on_chen = _stats.build_conus_mask_on_chen

FACTOR = 40  # 30 m * 40 = 1200 m
NCLS = len(COMMON_CLASSES)

_WORKER: dict = {}


def _init_worker(path: str) -> None:
    _WORKER["path"] = path
    _WORKER["lut"] = nlcd_lut()


def _count_block_rows(rows: tuple[int, int]) -> np.ndarray:
    """Exact per-common-class counts for one band of 1200 m display rows.

    Returns (NCLS, nrows_out, ncols_out) int16. Every native 30 m pixel in the
    band is counted; nothing is interpolated or sampled.
    """
    r0, r1 = rows  # native rows, multiples of FACTOR
    with rasterio.open(_WORKER["path"]) as ds:
        arr = ds.read(
            1, window=rasterio.windows.Window(0, r0, ds.width, r1 - r0)
        )
    codes = _WORKER["lut"][arr]
    nout_r = (r1 - r0) // FACTOR
    nout_c = arr.shape[1] // FACTOR
    out = np.empty((NCLS, nout_r, nout_c), dtype=np.int16)
    for c in range(NCLS):
        out[c] = (
            (codes == c)
            .reshape(nout_r, FACTOR, nout_c, FACTOR)
            .sum(axis=(1, 3), dtype=np.int16)
        )
    return out


def nlcd_display_counts(path: Path, workers: int) -> tuple[np.ndarray, Affine]:
    with rasterio.open(path) as ds:
        h, w = ds.height, ds.width
        transform = ds.transform * Affine.scale(FACTOR, FACTOR)
    if h % FACTOR or w % FACTOR:
        raise RuntimeError(f"FACTOR={FACTOR} must divide {h}x{w} exactly")

    rows_per_task = FACTOR * 20  # 800 native rows -> 20 display rows
    tasks = [(r, min(r + rows_per_task, h)) for r in range(0, h, rows_per_task)]
    out = np.zeros((NCLS, h // FACTOR, w // FACTOR), dtype=np.int16)

    t0 = time.time()
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(str(path),)
    ) as ex:
        for (r0, r1), block in zip(tasks, ex.map(_count_block_rows, tasks, chunksize=1)):
            out[:, r0 // FACTOR : r1 // FACTOR, :] = block
    print(f"    {path.name}: {time.time() - t0:.0f}s", flush=True)
    return out, transform


def chen_display_fracs(
    path: Path, win, win_transform, mask: np.ndarray, dst_shape, dst_transform, dst_crs
) -> np.ndarray:
    """Chen per-common-class areal fractions on the 1200 m Albers display grid."""
    with rasterio.open(path) as ds:
        arr = ds.read(1, window=win)
        src_crs = ds.crs

    codes = chen_lut()[arr.view(np.uint8)]
    codes[~mask] = COMMON_NODATA

    out = np.zeros((NCLS, *dst_shape), dtype=np.float32)
    for c in range(NCLS):
        ind = (codes == c).astype(np.float32)
        if not ind.any():
            continue
        reproject(
            source=ind,
            destination=out[c],
            src_transform=win_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.average,
            src_nodata=None,
            dst_nodata=None,
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument(
        "--out", type=Path, default=Path("outputs/interim/landcover_map_data.npz")
    )
    ap.add_argument("--years", nargs="+", default=["2015", "2020"])
    ap.add_argument(
        "--chen",
        nargs="+",
        default=[
            "2015:historical",
            "2020:SSP1_RCP19",
            "2020:SSP2_RCP45",
            "2020:SSP4_RCP60",
            "2020:SSP5_RCP85",
        ],
    )
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    store: dict[str, np.ndarray] = {}

    print("[1/3] NLCD -> exact 1200 m block counts from native 30 m ...", flush=True)
    for y in args.years:
        counts, dst_transform = nlcd_display_counts(nlcd_path(int(y)), args.workers)
        valid = counts.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(valid > 0, counts / np.maximum(valid, 1), 0.0).astype(
                np.float32
            )
        dom = np.where(valid > 0, counts.argmax(axis=0), COMMON_NODATA).astype(np.uint8)
        store[f"nlcd_{y}_frac"] = frac
        store[f"nlcd_{y}_dom"] = dom
        store[f"nlcd_{y}_valid"] = (valid / (FACTOR * FACTOR)).astype(np.float32)

    with rasterio.open(nlcd_path(int(args.years[0]))) as ds:
        dst_crs = ds.crs
        dst_shape = (ds.height // FACTOR, ds.width // FACTOR)
        dst_transform = ds.transform * Affine.scale(FACTOR, FACTOR)
    store["display_transform"] = np.array(dst_transform.to_gdal(), dtype=np.float64)
    store["display_crs_wkt"] = np.array([dst_crs.to_wkt()])

    print("[2/3] CONUS mask on Chen native grid ...", flush=True)
    geo = build_conus_mask_on_chen(nlcd_path(int(args.years[0])), find_tif(None, 2015))

    print("[3/3] Chen -> 1200 m display fractions ...", flush=True)
    for spec in args.chen:
        y, sc = spec.split(":")
        p = find_tif(None if sc == "historical" else sc, int(y))
        frac = chen_display_fracs(
            p,
            geo["window"],
            geo["transform"],
            geo["mask"],
            dst_shape,
            dst_transform,
            dst_crs,
        )
        store[f"chen_{y}_{sc}_frac"] = frac
        tot = frac.sum(axis=0)
        store[f"chen_{y}_{sc}_dom"] = np.where(
            tot > 0.5, frac.argmax(axis=0), COMMON_NODATA
        ).astype(np.uint8)
        store[f"chen_{y}_{sc}_valid"] = tot.astype(np.float32)
        print(f"    {spec} done", flush=True)

    np.savez_compressed(args.out, **store)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
