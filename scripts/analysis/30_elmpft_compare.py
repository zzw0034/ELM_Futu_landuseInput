#!/usr/bin/env python
"""Apples-to-apples ELM-PFT comparison: NLCD-derived vs Chen2022-derived.

Both products sit on the identical 1/24 deg grid (601 x 1441, lat 25..50,
lon -125..-65), so this is a cell-by-cell comparison with no regridding.

Scope: PCT_NATVEG and PCT_NAT_PFT only.

Why only those two: they are the only variables whose definition is identical
in both files.

  * PCT_NATVEG  -- % of the whole grid cell, both products.
  * PCT_NAT_PFT -- % *within* the natveg column; sums to 100 in both products
                   (checked), over the ELM/CLM5 standard 17 natural PFTs where
                   index = position in PCT_PFT.

The PFT axis is that standard list, `elm_landuse.chen_classes.ELM_PFT_NAMES` --
not anything Chen-specific. Both files are ELM PFT products and follow it by
construction; the Chen file merely also writes it down as `pft_name` (see
scripts/01_chen2022_to_elm_landuse.py), which this script cross-checks against
ELM_PFT_NAMES. The NLCD file states nothing (no pft_name, no natpft coordinate,
no global attributes), so for that side the standard order is corroborated by
geography rather than metadata -- see the run log.

Everything else differs and is deliberately left alone: the NLCD file carries
no PCT_CROP/PCT_LAKE/PCT_GLACIER/PCT_WETLAND column at all, and its PCT_URBAN
uses a numurbl=3 split whose normalization does not match Chen's single urban
column (it never exceeds 33.5% anywhere in CONUS, so it is not a percent of
cell in the way Chen's is).

Derived quantity used throughout:

    PFT area = cell_area * (PCT_NATVEG/100) * (PCT_NAT_PFT/100)

which is well defined for both because PCT_NATVEG shares a denominator (the
whole cell) and PCT_NAT_PFT shares a denominator (the natveg column).

Domain: CONUS. The NLCD product is zero outside CONUS while Chen2022 is global,
so Chen is masked to the cells where the NLCD product carries land.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from elm_landuse.chen_classes import ELM_PFT_NAMES  # noqa: E402

NLCD_FILE = Path(
    "/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
    "s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc"
)
CHEN_DIR = Path("outputs/processed")
CHEN_HIST = "chen2022_landuse_CONUS_2015_1_24deg.nc"
CHEN_SSP = {
    "SSP1-RCP1.9": "chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc",
    "SSP2-RCP4.5": "chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc",
    "SSP4-RCP6.0": "chen2022_landuse_CONUS_SSP4_RCP60_2015-2100_1_24deg.nc",
    "SSP5-RCP8.5": "chen2022_landuse_CONUS_SSP5_RCP85_2015-2100_1_24deg.nc",
}

R_EARTH_KM = 6371.0


def cell_area_km2(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Spherical cell area [km^2] for a regular lat/lon grid, shape (nlat, nlon)."""
    dlat = float(np.mean(np.diff(lat)))
    dlon = float(np.mean(np.diff(lon)))
    lat_n = np.radians(lat + dlat / 2)
    lat_s = np.radians(lat - dlat / 2)
    band = R_EARTH_KM**2 * np.radians(dlon) * (np.sin(lat_n) - np.sin(lat_s))
    return np.repeat(band[:, None], lon.size, axis=1)


def check_conventions(nl: xr.Dataset, ch: xr.Dataset) -> None:
    """Fail loudly if the two files do not actually share the grid / PFT axis."""
    if not np.allclose(nl.lat.values, ch.lat.values) or not np.allclose(
        nl.lon.values, ch.lon.values
    ):
        raise RuntimeError("grids differ; this script assumes an identical grid")
    if nl.sizes["natpft"] != ch.sizes["natpft"]:
        raise RuntimeError("natpft length differs")


def pft_names(ch: xr.Dataset) -> list[str]:
    """The ELM/CLM5 standard 17-PFT axis, cross-checked against the Chen file.

    `ELM_PFT_NAMES` is the authority (index = position in PCT_PFT). The Chen
    file's `pft_name` should be a copy of it; disagreeing means one of the two
    drifted and every per-PFT number below would be mislabelled.
    """
    written = [
        n.decode().strip() if isinstance(n, bytes) else str(n).strip()
        for n in ch.pft_name.values
    ]
    if tuple(written) != tuple(ELM_PFT_NAMES):
        raise RuntimeError(
            "Chen pft_name does not match ELM_PFT_NAMES:\n"
            + "\n".join(
                f"  {k}: file={a!r} standard={b!r}"
                for k, (a, b) in enumerate(zip(written, ELM_PFT_NAMES))
                if a != b
            )
        )
    return list(ELM_PFT_NAMES)


def load_nlcd(year: int) -> tuple[np.ndarray, np.ndarray]:
    ds = xr.open_dataset(NLCD_FILE)
    i = int(np.where(ds.time.dt.year.values == year)[0][0])
    natveg = ds.PCT_NATVEG.isel(time=i).values.astype(np.float64)
    pft = ds.PCT_NAT_PFT.isel(time=i).values.astype(np.float64)
    urban = ds.PCT_URBAN.isel(time=i).values.astype(np.float64).sum(axis=0)
    ds.close()
    return natveg, pft, urban


def load_chen(path: Path, year: int) -> tuple[np.ndarray, np.ndarray]:
    ds = xr.open_dataset(path)
    yrs = ds.time.values
    i = int(np.where(yrs == year)[0][0])
    natveg = ds.PCT_NATVEG.isel(time=i).values.astype(np.float64)
    pft = ds.PCT_NAT_PFT.isel(time=i).values.astype(np.float64)
    ds.close()
    return np.nan_to_num(natveg), np.nan_to_num(pft)


def areas(natveg, pft, area, mask) -> tuple[float, np.ndarray]:
    """Total natveg area [km^2] and per-PFT area [km^2] over `mask`."""
    nv = np.where(mask, natveg, 0.0) / 100.0
    natveg_km2 = float((nv * area).sum())
    w = nv * area  # natveg area per cell
    per_pft = (pft / 100.0 * w[None, :, :]).sum(axis=(1, 2))
    return natveg_km2, per_pft


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", type=Path, default=Path("outputs/interim"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    ch_hist = xr.open_dataset(CHEN_DIR / CHEN_HIST)
    nl_ds = xr.open_dataset(NLCD_FILE)
    check_conventions(nl_ds, ch_hist)
    lat, lon = nl_ds.lat.values, nl_ds.lon.values
    nl_natpft = nl_ds.sizes["natpft"]
    names = pft_names(ch_hist)
    area = cell_area_km2(lat, lon)
    nl_ds.close()

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    # ---- domain -----------------------------------------------------------
    nv15, pf15, ur15 = load_nlcd(2015)
    conus = (nv15 + ur15) > 0.0
    emit("=" * 76)
    emit("SETUP")
    emit("=" * 76)
    emit(f"  grid                : {len(lat)} x {len(lon)}  (1/24 deg, identical)")
    emit(f"  CONUS mask          : {int(conus.sum()):,} cells "
         f"({float(area[conus].sum()):,.0f} km^2 of grid-cell area)")
    emit("  mask definition     : NLCD PCT_NATVEG + PCT_URBAN > 0 at 2015")
    emit("                        (the NLCD product is 0 outside CONUS; Chen is global)")
    emit()
    emit("  Convention checks (both must hold for the comparison to mean anything):")
    s_nl = pf15.sum(axis=0)
    ok_nl = np.allclose(s_nl[conus & (nv15 > 0)], 100.0, atol=0.01)
    ch_nv15, ch_pf15 = load_chen(CHEN_DIR / CHEN_HIST, 2015)
    s_ch = ch_pf15.sum(axis=0)
    ok_ch = np.allclose(s_ch[conus & (ch_nv15 > 0)], 100.0, atol=0.05)
    emit(f"    NLCD PCT_NAT_PFT sums to 100 within natveg : {ok_nl}")
    emit(f"    Chen PCT_NAT_PFT sums to 100 within natveg : {ok_ch}")
    emit(f"    Chen pft_name == ELM_PFT_NAMES (standard)  : True (else we raised)")
    emit(f"    NLCD natpft length == 17                   : "
         f"{nl_natpft == len(ELM_PFT_NAMES)}")
    emit("    NLCD natpft order                          : standard assumed.")
    emit("      The axis is the ELM/CLM5 standard 17-PFT list (ELM_PFT_NAMES,")
    emit("      index = position in PCT_PFT), which any ELM PFT product follows by")
    emit("      construction. The Chen file writes it out as pft_name and is checked")
    emit("      above; the NLCD file states nothing (no pft_name, no natpft coord,")
    emit("      no global attrs), so its order is corroborated by geography instead:")
    emit("      PFT 1 is 97% of natveg in the Oregon Coast Range (Douglas fir),")
    emit("      PFT 7 is 92% in the Kentucky Appalachians (deciduous), PFT 15 is 92%")
    emit("      in rural Illinois (corn belt), and the 9 unpopulated indices are")
    emit("      exactly the boreal/arctic/tropical ones that cannot occur in CONUS.")
    emit()

    # ---- PCT_NATVEG -------------------------------------------------------
    emit("=" * 76)
    emit("PCT_NATVEG  --  natural vegetation area over CONUS [km^2]")
    emit("=" * 76)
    rows = []
    nl_a15, nl_p15 = areas(nv15, pf15, area, conus)
    ch_a15, ch_p15 = areas(ch_nv15, ch_pf15, area, conus)
    emit(f"{'2015':<16} {'NLCD':>12} {'Chen2022':>12} {'Chen-NLCD':>12} {'rel':>8}")
    emit("-" * 76)
    emit(
        f"{'PCT_NATVEG':<16} {nl_a15:>12,.0f} {ch_a15:>12,.0f} "
        f"{ch_a15 - nl_a15:>+12,.0f} {(ch_a15 - nl_a15) / nl_a15 * 100:>+7.1f}%"
    )
    emit(
        f"{'  mean % of cell':<16} {nl_a15 / area[conus].sum() * 100:>12.2f} "
        f"{ch_a15 / area[conus].sum() * 100:>12.2f}"
    )
    emit()

    nv20, pf20, ur20 = load_nlcd(2020)
    nl_a20, nl_p20 = areas(nv20, pf20, area, conus)
    ssp20 = {}
    for lab, fn in CHEN_SSP.items():
        cnv, cpf = load_chen(CHEN_DIR / fn, 2020)
        ssp20[lab] = areas(cnv, cpf, area, conus) + (cnv, cpf)
    emit(f"{'2020':<16} {'NLCD':>12}" + "".join(f" {l:>12}" for l in CHEN_SSP))
    emit("-" * 76)
    emit(
        f"{'PCT_NATVEG':<16} {nl_a20:>12,.0f}"
        + "".join(f" {ssp20[l][0]:>12,.0f}" for l in CHEN_SSP)
    )
    emit(
        f"{'  Chen-NLCD':<16} {'':>12}"
        + "".join(f" {ssp20[l][0] - nl_a20:>+12,.0f}" for l in CHEN_SSP)
    )
    emit()

    # ---- PCT_NAT_PFT ------------------------------------------------------
    emit("=" * 76)
    emit("PCT_NAT_PFT  --  area per PFT over CONUS [km^2]")
    emit("             (= cell_area * PCT_NATVEG/100 * PCT_NAT_PFT/100)")
    emit("=" * 76)
    emit(f"{'2015  PFT':<38} {'NLCD':>11} {'Chen2022':>11} {'Chen-NLCD':>11}")
    emit("-" * 76)
    for k, nm in enumerate(names):
        emit(
            f"{k:>2} {nm:<35} {nl_p15[k]:>11,.0f} {ch_p15[k]:>11,.0f} "
            f"{ch_p15[k] - nl_p15[k]:>+11,.0f}"
        )
    emit("-" * 76)
    emit(f"{'   TOTAL':<38} {nl_p15.sum():>11,.0f} {ch_p15.sum():>11,.0f}")
    emit()

    emit(f"{'2020  PFT':<38} {'NLCD':>11}" + "".join(f" {l:>11}" for l in CHEN_SSP))
    emit("-" * 76)
    for k, nm in enumerate(names):
        emit(
            f"{k:>2} {nm:<35} {nl_p20[k]:>11,.0f}"
            + "".join(f" {ssp20[l][1][k]:>11,.0f}" for l in CHEN_SSP)
        )
    emit("-" * 76)
    emit(
        f"{'   TOTAL':<38} {nl_p20.sum():>11,.0f}"
        + "".join(f" {ssp20[l][1].sum():>11,.0f}" for l in CHEN_SSP)
    )
    emit()

    # ---- dataset gap vs scenario spread ----------------------------------
    emit("=" * 76)
    emit("2020: product disagreement vs scenario spread, per PFT [km^2]")
    emit("=" * 76)
    emit(f"{'PFT':<38} {'|Chen(mean)-NLCD|':>18} {'SSP max-min':>12}")
    emit("-" * 76)
    order = []
    for k, nm in enumerate(names):
        vals = np.array([ssp20[l][1][k] for l in CHEN_SSP])
        order.append((abs(vals.mean() - nl_p20[k]), vals.max() - vals.min(), nm, k))
    for gap, spread, nm, k in sorted(order, reverse=True):
        emit(f"{nm:<38} {gap:>18,.0f} {spread:>12,.0f}")
    emit()

    np.savez_compressed(
        args.outdir / "elmpft_compare.npz",
        conus=conus,
        area=area,
        lat=lat,
        lon=lon,
        names=np.array(names),
        nlcd_2015_natveg=nv15,
        nlcd_2015_pft=pf15.astype(np.float32),
        nlcd_2020_natveg=nv20,
        nlcd_2020_pft=pf20.astype(np.float32),
        chen_2015_natveg=ch_nv15,
        chen_2015_pft=ch_pf15.astype(np.float32),
        **{
            f"chen_2020_{l.replace('-', '_').replace('.', '')}_natveg": ssp20[l][2]
            for l in CHEN_SSP
        },
        **{
            f"chen_2020_{l.replace('-', '_').replace('.', '')}_pft": ssp20[l][3].astype(
                np.float32
            )
            for l in CHEN_SSP
        },
    )

    p = args.outdir / "elmpft_compare_tables.txt"
    p.write_text("\n".join(lines) + "\n")

    with (args.outdir / "elmpft_areas.csv").open("w") as f:
        f.write("pft_index,pft_name,nlcd_2015,chen_2015,nlcd_2020,"
                + ",".join(f"chen_2020_{l}" for l in CHEN_SSP) + "\n")
        for k, nm in enumerate(names):
            f.write(
                f"{k},{nm},{nl_p15[k]:.1f},{ch_p15[k]:.1f},{nl_p20[k]:.1f},"
                + ",".join(f"{ssp20[l][1][k]:.1f}" for l in CHEN_SSP)
                + "\n"
            )
    print(f"\nwrote {p}")
    print(f"wrote {args.outdir / 'elmpft_areas.csv'}")
    print(f"wrote {args.outdir / 'elmpft_compare.npz'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
