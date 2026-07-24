#!/usr/bin/env python
"""Build an ELM-style land-use NetCDF from Chen2022 1 km PFT rasters.

Output variables (always percent, 0..100, dtype float32):

    PCT_NATVEG(time, lat, lon)                      - natural-veg column
    PCT_CROP(time, lat, lon)                        - cropland column
    PCT_LAKE(time, lat, lon)
    PCT_URBAN(time, lat, lon)
    PCT_GLACIER(time, lat, lon)
    PCT_NAT_PFT(time, natpft, lat, lon)             - sums to 100 within natveg
    PCT_WETLAND(time, lat, lon)                     - always 0 (Chen has no wetland class)

For a single-year output the time dimension has length 1.

Run from the project root with the `elm_landuse` package on PYTHONPATH; see
REFERENCE.md §6-7.

    export PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
    export PYTHONPATH=$PWD/src

Examples
--------
# 2015 historical, Southeast US at 1/24 deg (~4 km)
$PY scripts/01_chen2022_to_elm_landuse.py --scenario historical --years 2015 \\
    --bbox -95 24 -74 37.5 --resolution 0.0416666666666667 \\
    --out outputs/processed/chen2022_landuse_SEUS_2015_1_24deg.nc

# Full transient SSP2_RCP45, 2015 historical slice + 2020..2100 step 5
$PY scripts/01_chen2022_to_elm_landuse.py --scenario SSP2_RCP45 --years 2015 \\
    --extra-years 2020:2100:5 \\
    --bbox -95 24 -74 37.5 --resolution 0.0416666666666667 \\
    --out outputs/processed/chen2022_landuse_SEUS_SSP2_RCP45_1_24deg.nc
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

import numpy as np
import xarray as xr

from elm_landuse.chen_classes import CHEN_CLASSES, ELM_PFT_NAMES, NPFT
from elm_landuse.raster_io import find_tif, read_window_for_bbox
from elm_landuse.aggregate import (
    TargetGrid,
    aggregate_class_fractions,
    fractions_to_elm_columns,
    remap_boreal_ndt_by_lat,
)


def _parse_year_range(spec: str) -> list[int]:
    """Parse "start:stop:step" (inclusive of stop) or comma-separated list."""
    if not spec:
        return []
    if ":" in spec:
        parts = spec.split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"bad year-range {spec!r}")
        start, stop = int(parts[0]), int(parts[1])
        step = int(parts[2]) if len(parts) == 3 else 1
        return list(range(start, stop + 1, step))
    return [int(x) for x in spec.split(",") if x.strip()]


def _process_one(
    scenario: str | None,
    year: int,
    bbox: tuple[float, float, float, float],
    target: TargetGrid,
) -> dict[str, np.ndarray]:
    """Process a single scenario/year and return ELM column dict."""
    tif = find_tif(scenario, year)
    arr, src_transform, src_crs = read_window_for_bbox(tif, bbox)
    fractions = aggregate_class_fractions(
        arr, src_transform, src_crs, target, classes=CHEN_CLASSES
    )
    result = fractions_to_elm_columns(fractions, classes=CHEN_CLASSES)
    result["PCT_NAT_PFT"] = remap_boreal_ndt_by_lat(
        result["PCT_NAT_PFT"], target.lat_centers[::-1],  # array is north-up here; flip lat to match rows
    )
    return result


def build_dataset(
    scenario: str,
    years: list[int],
    bbox: tuple[float, float, float, float],
    target: TargetGrid,
) -> xr.Dataset:
    if not years:
        raise ValueError("no years requested")

    nt = len(years)
    ny, nx = target.shape_north_up()

    pct_pft = np.zeros((nt, NPFT, ny, nx), dtype=np.float32)
    cols = {
        k: np.zeros((nt, ny, nx), dtype=np.float32)
        for k in (
            "PCT_NATVEG",
            "PCT_CROP",
            "PCT_LAKE",
            "PCT_URBAN",
            "PCT_GLACIER",
            "PCT_WETLAND",
        )
    }

    for it, year in enumerate(years):
        # The 2015 raster only exists as the historical baseline at the top
        # level. Future years (2020-2100, step 5) live under the per-scenario
        # subdirectory. So always use historical for 2015, and require a real
        # SSP-RCP scenario for any other year.
        if year == 2015:
            sc: str | None = None
        else:
            if scenario in ("historical", "hist", ""):
                raise ValueError(
                    f"year {year} requires a real SSP-RCP scenario "
                    f"(--scenario historical only supports year 2015)"
                )
            sc = scenario
        result = _process_one(sc, year, bbox, target)
        for k in cols:
            cols[k][it] = result[k]
        pct_pft[it] = result["PCT_NAT_PFT"]

    # Latitudes ascending in the file, so flip rows of north-up arrays.
    lat = target.lat_centers
    lon = target.lon_centers
    pct_pft = pct_pft[:, :, ::-1, :]
    for k in cols:
        cols[k] = cols[k][:, ::-1, :]

    ds = xr.Dataset(
        data_vars={
            "PCT_NATVEG": (("time", "lat", "lon"), cols["PCT_NATVEG"]),
            "PCT_CROP": (("time", "lat", "lon"), cols["PCT_CROP"]),
            "PCT_LAKE": (("time", "lat", "lon"), cols["PCT_LAKE"]),
            "PCT_URBAN": (("time", "lat", "lon"), cols["PCT_URBAN"]),
            "PCT_GLACIER": (("time", "lat", "lon"), cols["PCT_GLACIER"]),
            "PCT_WETLAND": (("time", "lat", "lon"), cols["PCT_WETLAND"]),
            "PCT_NAT_PFT": (("time", "natpft", "lat", "lon"), pct_pft),
        },
        coords={
            "time": ("time", np.array(years, dtype=np.int32)),
            "natpft": ("natpft", np.arange(NPFT, dtype=np.int32)),
            "lat": ("lat", lat.astype(np.float64)),
            "lon": ("lon", lon.astype(np.float64)),
        },
    )

    pft_name_arr = np.array([s.ljust(48) for s in ELM_PFT_NAMES], dtype="S48")
    ds["pft_name"] = (("natpft",), pft_name_arr)

    ds["time"].attrs.update(units="year", long_name="calendar year")
    ds["natpft"].attrs.update(long_name="ELM natural PFT index", units="1")
    ds["lat"].attrs.update(units="degrees_north", long_name="latitude")
    ds["lon"].attrs.update(units="degrees_east", long_name="longitude")

    pct_attrs = dict(units="%", valid_min=np.float32(0), valid_max=np.float32(100))
    for k in (
        "PCT_NATVEG",
        "PCT_CROP",
        "PCT_LAKE",
        "PCT_URBAN",
        "PCT_GLACIER",
        "PCT_WETLAND",
        "PCT_NAT_PFT",
    ):
        ds[k].attrs.update(pct_attrs)
    ds["PCT_NATVEG"].attrs["long_name"] = "natural vegetation cover"
    ds["PCT_CROP"].attrs["long_name"] = "cropland cover"
    ds["PCT_LAKE"].attrs["long_name"] = "lake / inland water cover"
    ds["PCT_URBAN"].attrs["long_name"] = "urban cover (sum over urban density classes)"
    ds["PCT_GLACIER"].attrs["long_name"] = "permanent snow / ice cover"
    ds["PCT_WETLAND"].attrs["long_name"] = (
        "wetland cover (always 0; Chen2022 has no wetland class)"
    )
    ds["PCT_NAT_PFT"].attrs["long_name"] = "natural PFT cover within PCT_NATVEG"
    ds["pft_name"].attrs["long_name"] = "natural PFT name (index = natpft)"

    ds.attrs.update(
        title=f"Chen2022 1km PFT projection regridded to lat/lon for ELM",
        scenario=str(scenario),
        bbox_lonlat=f"{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}",
        resolution_deg=f"{target.dx} x {target.dy}",
        source="Chen et al. 2022, global 1 km PFT-based land projection (EASE-Grid 2.0, EPSG:6933)",
        history=f"created {_dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')} by 01_chen2022_to_elm_landuse.py",
        Conventions="CF-1.8",
    )
    return ds


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--scenario",
        default="historical",
        help="historical | SSP1_RCP19 | SSP1_RCP26 | SSP2_RCP45 | "
        "SSP3_RCP70 | SSP4_RCP34 | SSP4_RCP60 | SSP5_RCP34 | SSP5_RCP85",
    )
    p.add_argument(
        "--years", default="2015", help="comma-separated list, e.g. '2015,2020,2050'"
    )
    p.add_argument(
        "--extra-years",
        default="",
        help="optional 'start:stop:step' range merged with --years",
    )
    p.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("W", "S", "E", "N"),
        default=(-95.0, 24.0, -74.0, 37.5),
        help="lon/lat bbox W S E N, as cell EDGES (default: SEUS SCRIP Surface domain)",
    )
    p.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="target dx=dy in degrees (default 0.5)",
    )
    p.add_argument(
        "--like",
        metavar="REF.nc",
        help="copy the target grid from a reference NetCDF's lat/lon cell centers; "
        "overrides --bbox/--resolution",
    )
    p.add_argument("--out", required=True, help="output NetCDF path")
    args = p.parse_args(argv)

    years = sorted(
        set(_parse_year_range(args.years) + _parse_year_range(args.extra_years))
    )
    if not years:
        p.error("no valid years parsed from --years/--extra-years")

    if args.like:
        ref = xr.open_dataset(args.like, decode_times=False)
        try:
            if "lat" in ref.variables and ref["lat"].ndim == 1:
                latc = ref["lat"].values
                lonc = ref["lon"].values
            elif "LATIXY" in ref.variables and "LONGXY" in ref.variables:
                # ELM surfdata / landuse.timeseries grid: dims lsmlat/lsmlon with
                # 2-D LATIXY(lsmlat,lsmlon) (lat varies down rows) and
                # LONGXY(lsmlat,lsmlon) (lon varies across cols). Take a row/col.
                latc = np.asarray(ref["LATIXY"].values)[:, 0]
                lonc = np.asarray(ref["LONGXY"].values)[0, :]
            else:
                raise ValueError(
                    f"--like {args.like}: found neither 1-D lat/lon nor LATIXY/LONGXY"
                )
            target = TargetGrid.from_centers(latc, lonc)
        finally:
            ref.close()
        print(f"[build_elm_landuse] grid from --like {args.like}")
    else:
        w, s, e, n = args.bbox
        target = TargetGrid(
            lon_min=w,
            lat_min=s,
            lon_max=e,
            lat_max=n,
            dx=args.resolution,
            dy=args.resolution,
        )

    # The source window is read for the target's own bounds, so --like and
    # --bbox stay consistent.
    bbox = (target.lon_min, target.lat_min, target.lon_max, target.lat_max)

    print(f"[build_elm_landuse] scenario={args.scenario} years={years}")
    print(f"[build_elm_landuse] bbox={bbox} resolution={target.dx} x {target.dy} deg")
    print(f"[build_elm_landuse] target shape (ny, nx) = {target.shape_north_up()}")

    ds = build_dataset(args.scenario, years, bbox, target)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = {
        v: {"zlib": True, "complevel": 4}
        for v in ds.data_vars
        if ds[v].dtype.kind in "fi"
    }
    ds.to_netcdf(out, encoding=enc)
    print(f"[build_elm_landuse] wrote {out}  ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
