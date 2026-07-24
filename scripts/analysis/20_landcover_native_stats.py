#!/usr/bin/env python
"""Native-resolution land-cover statistics for NLCD (30 m) vs Chen2022 (1 km).

Neither dataset is resampled. Both sit on equal-area projections, so the area
of a class is exactly ``pixel_count * pixel_area``:

  * NLCD      Albers Conical Equal Area, 30 m   -> 900 m^2 per pixel
  * Chen2022  EASE-Grid 2.0 (EPSG:6933), 1 km   -> 1e6 m^2 per pixel

NLCD is counted over every valid pixel of the CONUS product (nodata = 250).
Chen2022 is global, so it is counted over a CONUS mask built by reprojecting
the NLCD *data footprint* onto Chen's own 1 km grid. Only the domain mask is
reprojected -- the Chen class values themselves are read and counted at native
1 km. The two footprints agree to a fraction of a percent; the script reports
both total areas so the residual can be checked (see `total_area_km2`).

Writes one JSON of raw class counts to outputs/interim/. All interpretation
(crosswalk to the common legend, tables, figures) happens in the compare step.

Usage:
    $PY scripts/20_landcover_native_stats.py --workers 12 \
        --out outputs/interim/landcover_native_counts.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine, rowcol
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from elm_landuse.common_legend import CHEN_NODATA, NLCD_NODATA  # noqa: E402
from elm_landuse.raster_io import find_tif  # noqa: E402

NLCD_DIR = Path("/projects/hpcl-cli185/proj-shared/zdr/hires_data/landcover/NLCD")
NLCD_TEMPLATE = "Annual_NLCD_LndCov_{year}_CU_C1V0.tif"

# Footprint is reprojected from this decimation level of NLCD (~480 m). Fine
# enough that coastline placement on Chen's 1 km grid is sub-pixel; coarse
# enough to read in one shot.
FOOTPRINT_SHAPE = (6563, 10000)


def nlcd_path(year: int) -> Path:
    p = NLCD_DIR / NLCD_TEMPLATE.format(year=year)
    if not p.exists():
        raise FileNotFoundError(p)
    return p


# ---------------------------------------------------------------------------
# NLCD: full-resolution class histogram
# ---------------------------------------------------------------------------
_NLCD_WORKER_PATH: str | None = None


def _init_nlcd_worker(path: str) -> None:
    global _NLCD_WORKER_PATH
    _NLCD_WORKER_PATH = path


def _count_nlcd_rows(row_range: tuple[int, int]) -> np.ndarray:
    """Bincount one horizontal slab of the NLCD raster at native 30 m."""
    row0, row1 = row_range
    with rasterio.open(_NLCD_WORKER_PATH) as ds:
        win = Window(col_off=0, row_off=row0, width=ds.width, height=row1 - row0)
        arr = ds.read(1, window=win)
    return np.bincount(arr.ravel(), minlength=256).astype(np.int64)


def count_nlcd(path: Path, workers: int, rows_per_task: int = 256) -> dict:
    """Return raw NLCD class counts over the whole raster, read at native 30 m."""
    with rasterio.open(path) as ds:
        height, width = ds.height, ds.width
        pixel_w, pixel_h = abs(ds.transform.a), abs(ds.transform.e)

    tasks = [
        (r, min(r + rows_per_task, height)) for r in range(0, height, rows_per_task)
    ]
    total = np.zeros(256, dtype=np.int64)
    t0 = time.time()
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_nlcd_worker, initargs=(str(path),)
    ) as ex:
        for i, counts in enumerate(ex.map(_count_nlcd_rows, tasks, chunksize=1)):
            total += counts
            if (i + 1) % 50 == 0 or i + 1 == len(tasks):
                done = (i + 1) / len(tasks)
                print(
                    f"    {path.name}: {done:6.1%}  ({time.time() - t0:5.0f}s)",
                    flush=True,
                )

    counted = int(total.sum())
    if counted != height * width:
        raise RuntimeError(f"counted {counted} pixels, expected {height * width}")

    return {
        "path": str(path),
        "counts": {int(v): int(c) for v, c in enumerate(total) if c > 0},
        "pixel_area_m2": pixel_w * pixel_h,
        "nodata": NLCD_NODATA,
        "shape": [height, width],
    }


# ---------------------------------------------------------------------------
# Chen2022: CONUS mask + native 1 km class histogram
# ---------------------------------------------------------------------------
def build_conus_mask_on_chen(nlcd_ref: Path, chen_ref: Path) -> dict:
    """Reproject the NLCD data footprint onto Chen's native 1 km grid.

    Returns the window into the Chen raster covering CONUS, that window's
    transform, and a boolean mask (True = inside the NLCD footprint).

    Only the footprint is warped. Chen class values are never resampled.
    """
    with rasterio.open(nlcd_ref) as nds:
        nlcd_crs, nlcd_bounds = nds.crs, nds.bounds
        foot = nds.read(1, out_shape=FOOTPRINT_SHAPE, resampling=Resampling.nearest)
        valid = (foot != NLCD_NODATA).astype(np.float32)
        foot_transform = nds.transform * Affine.scale(
            nds.width / FOOTPRINT_SHAPE[1], nds.height / FOOTPRINT_SHAPE[0]
        )

    with rasterio.open(chen_ref) as cds:
        chen_crs = cds.crs
        # NLCD footprint bounds -> Chen CRS. densify so the Albers edges, which
        # are curved in EASE-Grid, are enclosed rather than chorded.
        l, b, r, t = transform_bounds(
            nlcd_crs, chen_crs, *nlcd_bounds, densify_pts=201
        )
        # Outward-rounded integer window, clamped to the raster.
        row0, col0 = rowcol(cds.transform, l, t, op=math.floor)
        row1, col1 = rowcol(cds.transform, r, b, op=math.ceil)
        col0 = max(0, min(int(col0), cds.width))
        col1 = max(0, min(int(col1), cds.width))
        row0 = max(0, min(int(row0), cds.height))
        row1 = max(0, min(int(row1), cds.height))
        if col1 <= col0 or row1 <= row0:
            raise RuntimeError("NLCD footprint does not intersect the Chen raster")
        win = Window(col0, row0, col1 - col0, row1 - row0)
        win_transform = cds.window_transform(win)

    cover = np.zeros((int(win.height), int(win.width)), dtype=np.float32)
    reproject(
        source=valid,
        destination=cover,
        src_transform=foot_transform,
        src_crs=nlcd_crs,
        dst_transform=win_transform,
        dst_crs=chen_crs,
        resampling=Resampling.average,
        src_nodata=None,
        dst_nodata=None,
    )
    mask = cover >= 0.5
    return {"window": win, "transform": win_transform, "mask": mask}


def count_chen(path: Path, mask: np.ndarray, window: Window) -> dict:
    """Return raw Chen class counts inside `mask`, read at native 1 km."""
    with rasterio.open(path) as ds:
        arr = ds.read(1, window=window)
        pixel_w, pixel_h = abs(ds.transform.a), abs(ds.transform.e)
    if arr.shape != mask.shape:
        raise RuntimeError(f"chen window {arr.shape} != mask {mask.shape}")

    # int8 -> uint8 view keeps every value a valid 256-LUT index; nodata (-128)
    # wraps to 128 and is excluded by the mask/LUT rather than by arithmetic.
    codes = arr.view(np.uint8).copy()
    codes[~mask] = 255  # outside CONUS -> excluded bin
    counts = np.bincount(codes.ravel(), minlength=256).astype(np.int64)

    return {
        "path": str(path),
        "counts": {int(v): int(c) for v, c in enumerate(counts) if c > 0},
        "pixel_area_m2": pixel_w * pixel_h,
        "nodata": CHEN_NODATA,
        "mask_pixels": int(mask.sum()),
        "shape": list(arr.shape),
    }


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument(
        "--out", type=Path, default=Path("outputs/interim/landcover_native_counts.json")
    )
    ap.add_argument(
        "--scenarios",
        nargs="+",
        default=["SSP1_RCP19", "SSP2_RCP45", "SSP4_RCP60", "SSP5_RCP85"],
    )
    ap.add_argument("--max-rows", type=int, default=None, help="debug: limit NLCD rows")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {"nlcd": {}, "chen": {}}

    chen_2015 = find_tif(None, 2015)

    print("[1/3] building CONUS mask on Chen's native 1 km grid ...", flush=True)
    t0 = time.time()
    geo = build_conus_mask_on_chen(nlcd_path(2015), chen_2015)
    mask, win = geo["mask"], geo["window"]
    print(
        f"    window={win}  mask={mask.sum():,} px "
        f"({mask.sum() * 1e6 / 1e6:,.0f} km^2)  ({time.time() - t0:.0f}s)",
        flush=True,
    )

    print("[2/3] counting Chen2022 at native 1 km ...", flush=True)
    result["chen"]["2015_historical"] = count_chen(chen_2015, mask, win)
    for sc in args.scenarios:
        p = find_tif(sc, 2020)
        result["chen"][f"2020_{sc}"] = count_chen(p, mask, win)
        print(f"    {sc} 2020 done", flush=True)

    print("[3/3] counting NLCD at native 30 m (full resolution) ...", flush=True)
    for year in (2015, 2020):
        result["nlcd"][str(year)] = count_nlcd(nlcd_path(year), args.workers)

    args.out.write_text(json.dumps(result, indent=2))
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
