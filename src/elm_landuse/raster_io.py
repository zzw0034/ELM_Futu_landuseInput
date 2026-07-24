"""Helpers for locating and reading Chen2022 PFT GeoTIFFs.

Default ``DATA_ROOT`` is the repo folder ``data/external/chen2022_1km/``
(resolved from this package location: ``src/elm_landuse`` → repo root).

Expected layout under that directory:

    global_PFT_2015.tif                              # 2015 historical
    SSP{1-5}_RCP{19,26,34,45,60,70,85}/
        global_PFT_SSP{x}_RCP{y}_{YEAR}.tif          # YEAR in 2020..2100 step 5
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds


HERE = Path(__file__).resolve().parent
# Package lives at <repo>/src/elm_landuse/; Chen Zenodo rasters live per FOLDERS.md.
_REPO_ROOT = HERE.parent.parent
DATA_ROOT = _REPO_ROOT / "data" / "external" / "chen2022_1km"

SCENARIOS: tuple[str, ...] = (
    "SSP1_RCP19",
    "SSP1_RCP26",
    "SSP2_RCP45",
    "SSP3_RCP70",
    "SSP4_RCP34",
    "SSP4_RCP60",
    "SSP5_RCP34",
    "SSP5_RCP85",
)

_FUTURE_RE = re.compile(r"global_PFT_(SSP\d_RCP\d+)_(\d{4})\.tif$")


def find_tif(scenario: str | None, year: int, data_root: Path | None = None) -> Path:
    """Locate the Chen2022 .tif for a given scenario/year.

    Use `scenario=None` (or `"historical"`) with `year=2015` for the baseline
    `global_PFT_2015.tif` file at the top level.
    """
    root = Path(data_root) if data_root else DATA_ROOT
    if scenario in (None, "", "historical", "hist"):
        if year != 2015:
            raise ValueError("only year=2015 exists for historical baseline")
        p = root / "global_PFT_2015.tif"
    else:
        if scenario not in SCENARIOS:
            raise ValueError(
                f"unknown scenario {scenario!r}; expected one of {SCENARIOS}"
            )
        p = root / scenario / f"global_PFT_{scenario}_{year}.tif"
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def list_available(data_root: Path | None = None) -> dict[str, list[int]]:
    """Return {scenario: sorted list of years} actually present on disk."""
    root = Path(data_root) if data_root else DATA_ROOT
    out: dict[str, list[int]] = {}
    if (root / "global_PFT_2015.tif").exists():
        out["historical"] = [2015]
    for sc in SCENARIOS:
        d = root / sc
        if not d.is_dir():
            continue
        years: list[int] = []
        for f in d.glob("global_PFT_*.tif"):
            m = _FUTURE_RE.search(f.name)
            if m and m.group(1) == sc:
                years.append(int(m.group(2)))
        if years:
            out[sc] = sorted(set(years))
    return out


def read_window_for_bbox(
    tif_path: Path,
    bbox_lonlat: tuple[float, float, float, float],
    pad_pixels: int = 8,
) -> tuple[np.ndarray, "rasterio.Affine", "rasterio.crs.CRS"]:
    """Read just the window of `tif_path` covering a lon/lat bbox.

    Parameters
    ----------
    tif_path
        Path to a Chen2022 .tif (CRS is EPSG:6933 equal-area, 1 km).
    bbox_lonlat
        (west, south, east, north) in degrees (EPSG:4326).
    pad_pixels
        Extra source pixels around the window for safe reprojection.

    Returns
    -------
    arr : np.ndarray, shape (H, W), int8
        Raster values in source EPSG:6933.
    transform : rasterio.Affine
        Affine for the returned window in source CRS.
    src_crs : rasterio.crs.CRS
        Source CRS (EPSG:6933).
    """
    west, south, east, north = bbox_lonlat
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"invalid bbox_lonlat: {bbox_lonlat}")

    with rasterio.open(tif_path) as ds:
        src_crs = ds.crs
        # Project the lon/lat bbox into source CRS to find the source window.
        l, b, r, t = transform_bounds(
            "EPSG:4326", src_crs, west, south, east, north, densify_pts=21
        )
        win = (
            from_bounds(l, b, r, t, transform=ds.transform)
            .round_offsets()
            .round_lengths()
        )
        win = Window(
            col_off=max(int(win.col_off) - pad_pixels, 0),
            row_off=max(int(win.row_off) - pad_pixels, 0),
            width=int(win.width) + 2 * pad_pixels,
            height=int(win.height) + 2 * pad_pixels,
        )
        win = win.intersection(Window(0, 0, ds.width, ds.height))
        arr = ds.read(1, window=win)
        transform = ds.window_transform(win)
    return arr, transform, src_crs


def iter_scenario_years(
    scenarios: Iterable[str],
    years: Iterable[int],
    data_root: Path | None = None,
) -> Iterable[tuple[str, int, Path]]:
    """Yield (scenario, year, path) tuples that exist on disk."""
    avail = list_available(data_root)
    for sc in scenarios:
        present = set(avail.get(sc, ()))
        for y in years:
            if y in present:
                yield sc, y, find_tif(sc if sc != "historical" else None, y, data_root)


__all__ = [
    "DATA_ROOT",
    "SCENARIOS",
    "find_tif",
    "list_available",
    "read_window_for_bbox",
    "iter_scenario_years",
]
