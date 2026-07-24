"""Area-weighted aggregation of Chen2022 1 km PFT rasters to a target lat/lon grid.

The Chen2022 raster is in EPSG:6933 (NSIDC EASE-Grid 2.0 Global), where every
1 km source pixel has the same area. For each Chen class c we therefore build
a binary indicator at 1 km, then reproject onto the target lat/lon grid using
`Resampling.average`. The destination value is the mean of the contributing
source pixels, which (because source pixels are equal-area) is the fractional
area of class c inside that destination cell.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from .chen_classes import CHEN_CLASSES


@dataclass(frozen=True)
class TargetGrid:
    """Regular lat/lon grid in EPSG:4326.

    Cell centers are at (lon_min + (i+0.5)*dx, lat_min + (j+0.5)*dy).
    Latitudes increase northward; we store them ascending and flip on write.
    """

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float
    dx: float
    dy: float

    @property
    def nx(self) -> int:
        n = int(round((self.lon_max - self.lon_min) / self.dx))
        if n <= 0:
            raise ValueError(
                f"non-positive nx (lon range {self.lon_min}..{self.lon_max}, dx={self.dx})"
            )
        return n

    @property
    def ny(self) -> int:
        n = int(round((self.lat_max - self.lat_min) / self.dy))
        if n <= 0:
            raise ValueError(
                f"non-positive ny (lat range {self.lat_min}..{self.lat_max}, dy={self.dy})"
            )
        return n

    @property
    def lon_centers(self) -> np.ndarray:
        return self.lon_min + (np.arange(self.nx) + 0.5) * self.dx

    @property
    def lat_centers(self) -> np.ndarray:
        return self.lat_min + (np.arange(self.ny) + 0.5) * self.dy

    @property
    def transform_north_up(self) -> Affine:
        """Affine for a north-up array (row 0 = northernmost row)."""
        return Affine(self.dx, 0.0, self.lon_min, 0.0, -self.dy, self.lat_max)

    def shape_north_up(self) -> tuple[int, int]:
        return (self.ny, self.nx)

    @classmethod
    def from_centers(cls, lat: np.ndarray, lon: np.ndarray) -> "TargetGrid":
        """Build a grid whose cell centers reproduce `lat`/`lon` exactly.

        `lat`/`lon` are 1-D cell-center coordinates with constant spacing, as
        read from a reference file. Because the constructor takes cell EDGES,
        the bounds are the centers expanded by half a cell — get this wrong and
        the output is silently offset by half a cell from the reference.
        """
        lat = np.asarray(lat, dtype=np.float64)
        lon = np.asarray(lon, dtype=np.float64)
        if lat.ndim != 1 or lon.ndim != 1 or lat.size < 2 or lon.size < 2:
            raise ValueError("lat/lon must be 1-D cell-center arrays of length >= 2")

        dy = float(np.mean(np.diff(lat)))
        dx = float(np.mean(np.diff(lon)))
        if dy <= 0 or dx <= 0:
            raise ValueError("lat/lon centers must be strictly ascending")
        for name, a, d in (("lat", lat, dy), ("lon", lon, dx)):
            if not np.allclose(np.diff(a), d, rtol=0, atol=1e-9):
                raise ValueError(f"{name} spacing is not constant (got {np.diff(a)})")

        return cls(
            lon_min=float(lon[0]) - 0.5 * dx,
            lat_min=float(lat[0]) - 0.5 * dy,
            lon_max=float(lon[-1]) + 0.5 * dx,
            lat_max=float(lat[-1]) + 0.5 * dy,
            dx=dx,
            dy=dy,
        )


def aggregate_class_fractions(
    src_arr: np.ndarray,
    src_transform: Affine,
    src_crs: "rasterio.crs.CRS",
    target: TargetGrid,
    classes: tuple[int, ...] = CHEN_CLASSES,
    nodata_value: int = -128,
) -> np.ndarray:
    """Return shape (n_classes, ny, nx) float32 of fractional coverage in [0, 1].

    Pixels equal to `nodata_value` are excluded both from numerator and
    denominator. The slices along axis 0 follow the order of `classes`.
    """
    if src_arr.ndim != 2:
        raise ValueError(f"src_arr must be 2-D, got shape {src_arr.shape}")

    dst_shape = target.shape_north_up()
    dst_transform = target.transform_north_up
    dst_crs = "EPSG:4326"

    valid_src = (src_arr != nodata_value).astype(np.float32)

    # Coverage of valid (non-nodata) pixels in each destination cell.
    valid_cov = np.zeros(dst_shape, dtype=np.float32)
    reproject(
        source=valid_src,
        destination=valid_cov,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.average,
        src_nodata=None,
        dst_nodata=None,
    )

    out = np.zeros((len(classes), *dst_shape), dtype=np.float32)
    for i, c in enumerate(classes):
        mask = ((src_arr == c) & (src_arr != nodata_value)).astype(np.float32)
        if not mask.any():
            continue  # leave zeros
        reproject(
            source=mask,
            destination=out[i],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.average,
            src_nodata=None,
            dst_nodata=None,
        )

    # Renormalize by valid coverage so fractions sum to 1 over valid land+water.
    # Cells without any valid source coverage are left as zeros (will mask later).
    with np.errstate(invalid="ignore", divide="ignore"):
        scale = np.where(valid_cov > 0, 1.0 / valid_cov, 0.0).astype(np.float32)
    out *= scale[None, :, :]

    np.clip(out, 0.0, 1.0, out=out)
    return out


def fractions_to_elm_columns(
    frac: np.ndarray,
    classes: tuple[int, ...] = CHEN_CLASSES,
) -> dict[str, np.ndarray]:
    """Convert per-class fractions to ELM column percentages.

    Parameters
    ----------
    frac : (n_classes, ny, nx) float32 in [0, 1]
    classes : Chen class IDs aligned with axis 0 of `frac`

    Returns
    -------
    dict with keys:
        PCT_LAKE, PCT_URBAN, PCT_GLACIER, PCT_CROP, PCT_NATVEG, PCT_WETLAND :
            (ny, nx) float32 in [0, 100]
        PCT_NAT_PFT : (NPFT, ny, nx) float32 in [0, 100], summing to 100 within natveg

    Note: Chen2022 has no wetland class; PCT_WETLAND is therefore always 0
    (kept for ELM schema compatibility).
    """
    from elm_landuse.chen_classes import CHEN_TO_ELM, NPFT

    cls_to_idx = {c: i for i, c in enumerate(classes)}

    ny, nx = frac.shape[1], frac.shape[2]

    special = {
        k: np.zeros((ny, nx), dtype=np.float32)
        for k in ("PCT_LAKE", "PCT_URBAN", "PCT_GLACIER", "PCT_CROP")
    }
    natveg = np.zeros((ny, nx), dtype=np.float32)
    pft_in_natveg = np.zeros((NPFT, ny, nx), dtype=np.float32)

    for c, m in CHEN_TO_ELM.items():
        if c not in cls_to_idx:
            continue
        f = frac[cls_to_idx[c]]
        if m.special is not None:
            special[m.special] += f
        else:
            natveg += f
            for i, w in enumerate(m.pft_weights):
                if w != 0.0:
                    pft_in_natveg[i] += w * f

    columns: dict[str, np.ndarray] = {k: 100.0 * v for k, v in special.items()}
    columns["PCT_NATVEG"] = 100.0 * natveg
    columns["PCT_WETLAND"] = np.zeros((ny, nx), dtype=np.float32)

    pct_pft = np.zeros_like(pft_in_natveg)
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = np.where(natveg > 0, natveg, np.nan)
        pct_pft[:] = 100.0 * pft_in_natveg / denom[None, :, :]
    pct_pft = np.where(np.isfinite(pct_pft), pct_pft, 0.0).astype(np.float32)

    # If natveg is zero, default PFT distribution to 100% bare so downstream
    # codes don't divide by zero on totals.
    no_natveg = natveg == 0
    if no_natveg.any():
        pct_pft[0][no_natveg] = (
            100.0  # Safe as long as pct_pft is only used where natveg > 0
        )
        # (i.e., gated by natveg; ignored when PCT_NATVEG == 0).

    columns["PCT_NAT_PFT"] = pct_pft
    return columns


def remap_boreal_ndt_by_lat(
    pct_nat_pft: np.ndarray,
    lat: np.ndarray,
    lat_threshold: float = 45.0,
) -> np.ndarray:
    """Reassign PFT 3 (needleleaf deciduous boreal) to PFT 1 (needleleaf evergreen
    temperate) for grid cells south of lat_threshold.

    Chen class 9 (Needleleaf deciduous tree) has no climate-zone distinction, so
    aggregate_class_fractions maps it all to ELM PFT 3 (boreal). That is wrong at
    mid/low latitudes (e.g. SEUS). Below lat_threshold the boreal label is
    implausible, so we move the fraction into the nearest temperate equivalent.

    Parameters
    ----------
    pct_nat_pft : (NPFT, ny, nx) float32, percent within PCT_NATVEG
    lat         : (ny,) latitude of cell centers, ascending
    lat_threshold : cells with lat < this value get remapped (default 45.0°N)

    Returns
    -------
    (NPFT, ny, nx) float32 with PFT 3 zeroed and its value added to PFT 1
    south of lat_threshold.
    """
    out = pct_nat_pft.copy()
    low_lat = (lat < lat_threshold)[:, None]  # (ny, 1) broadcasts over nx
    out[1] = np.where(low_lat, out[1] + out[3], out[1])
    out[3] = np.where(low_lat, 0.0, out[3])
    return out


__all__ = [
    "TargetGrid",
    "aggregate_class_fractions",
    "fractions_to_elm_columns",
    "remap_boreal_ndt_by_lat",
]
