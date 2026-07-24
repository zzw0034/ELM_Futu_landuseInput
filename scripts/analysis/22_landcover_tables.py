#!/usr/bin/env python
"""Turn the native pixel counts (script 20) into comparable area tables.

Areas are exact: both products are on equal-area projections, so
``area = pixel_count * pixel_area`` with no resampling anywhere in the chain.

The domain is CONUS as delineated by the NLCD data footprint. NLCD's valid
footprint and the Chen CONUS mask agree to ~0.01%, so percentages of each
product's own domain total are directly comparable.

Writes CSVs to outputs/interim/ and prints the tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from elm_landuse.common_legend import (  # noqa: E402
    CHEN_NODATA,
    CHEN_TO_COMMON,
    COMMON_CLASSES,
    COMMON_NAMES,
    NLCD_CLASS_NAMES,
    NLCD_NODATA,
    NLCD_TO_COMMON,
)

SCENARIO_LABELS = {
    "2015_historical": "Chen2022 historical",
    "2020_SSP1_RCP19": "SSP1-RCP1.9",
    "2020_SSP2_RCP45": "SSP2-RCP4.5",
    "2020_SSP4_RCP60": "SSP4-RCP6.0",
    "2020_SSP5_RCP85": "SSP5-RCP8.5",
}


def nlcd_areas(entry: dict) -> tuple[dict[int, float], float]:
    """Common-class areas [km^2] from raw NLCD counts, plus the domain total."""
    px_km2 = entry["pixel_area_m2"] / 1e6
    out = {c: 0.0 for c in COMMON_CLASSES}
    unmapped = 0
    for v, n in entry["counts"].items():
        v = int(v)
        if v == NLCD_NODATA:
            continue
        if v not in NLCD_TO_COMMON:
            unmapped += n
            continue
        out[NLCD_TO_COMMON[v]] += n * px_km2
    if unmapped:
        raise RuntimeError(f"{unmapped} NLCD pixels outside the documented legend")
    return out, sum(out.values())


def chen_areas(entry: dict) -> tuple[dict[int, float], float, float]:
    """Common-class areas [km^2] from raw Chen counts, domain total, nodata area.

    Chen's nodata inside the CONUS mask is coastal/estuarine water that its
    land mask drops but NLCD maps as Open Water; it is reported separately
    rather than silently folded into Water.
    """
    px_km2 = entry["pixel_area_m2"] / 1e6
    out = {c: 0.0 for c in COMMON_CLASSES}
    nodata_km2 = 0.0
    for v, n in entry["counts"].items():
        v = int(v)
        if v == 255:  # outside the CONUS mask
            continue
        if v == (CHEN_NODATA & 0xFF):  # -128 seen through the uint8 view
            nodata_km2 += n * px_km2
            continue
        if v not in CHEN_TO_COMMON:
            raise RuntimeError(f"unexpected Chen class {v}")
        out[CHEN_TO_COMMON[v]] += n * px_km2
    return out, sum(out.values()) + nodata_km2, nodata_km2


def fmt_row(name, a, pa, b, pb) -> str:
    d = b - a
    rel = f"{d / a * 100:+7.1f}%" if a > 0 else ("    n/a" if d == 0 else "   +inf")
    return (
        f"{name:<14} {a:>10,.0f} {pa:>6.2f}%  {b:>10,.0f} {pb:>6.2f}%  "
        f"{d:>+10,.0f} {rel}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--counts",
        type=Path,
        default=Path("outputs/interim/landcover_native_counts.json"),
    )
    ap.add_argument("--outdir", type=Path, default=Path("outputs/interim"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    d = json.loads(args.counts.read_text())

    nl = {y: nlcd_areas(e) for y, e in d["nlcd"].items()}
    ch = {k: chen_areas(e) for k, e in d["chen"].items()}

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("=" * 78)
    emit("DOMAIN CHECK (CONUS, from the NLCD data footprint)")
    emit("=" * 78)
    for y, (_, tot) in nl.items():
        emit(f"  NLCD {y} valid footprint      : {tot:>12,.0f} km^2  (30 m native)")
    k0 = "2015_historical"
    emit(f"  Chen CONUS mask               : {ch[k0][1]:>12,.0f} km^2  (1 km native)")
    diff = ch[k0][1] - nl["2015"][1]
    emit(
        f"  difference                    : {diff:>+12,.0f} km^2  "
        f"({diff / nl['2015'][1] * 100:+.3f}%)"
    )
    emit()

    # ---- 2015 -------------------------------------------------------------
    a15, ta15 = nl["2015"]
    b15, tb15, nod15 = ch["2015_historical"]
    emit("=" * 78)
    emit("2015  --  NLCD (30 m) vs Chen2022 historical (1 km)")
    emit("=" * 78)
    emit(
        f"{'class':<14} {'NLCD km2':>10} {'NLCD %':>7}  {'Chen km2':>10} "
        f"{'Chen %':>7}  {'Chen-NLCD':>10} {'rel':>8}"
    )
    emit("-" * 78)
    for c in COMMON_CLASSES:
        emit(
            fmt_row(
                COMMON_NAMES[c], a15[c], a15[c] / ta15 * 100, b15[c], b15[c] / tb15 * 100
            )
        )
    emit(
        f"{'No data':<14} {0:>10,.0f} {0.0:>6.2f}%  {nod15:>10,.0f} "
        f"{nod15 / tb15 * 100:>6.2f}%  {nod15:>+10,.0f}     n/a"
    )
    emit("-" * 78)
    emit(f"{'TOTAL':<14} {ta15:>10,.0f} {100.0:>6.2f}%  {tb15:>10,.0f} {100.0:>6.2f}%")
    emit()
    emit("Notes:")
    emit(
        f"  * Chen has no wetland class: NLCD's {a15[9]:,.0f} km^2 of wetland has to be"
    )
    emit("    absorbed by Chen's forest/grass/water classes.")
    emit(
        f"  * Chen has no pasture class. Cropland, strict (NLCD 82 only): "
        f"NLCD {a15[8]:,.0f} vs Chen {b15[8]:,.0f} km^2 "
        f"({(b15[8] - a15[8]) / a15[8] * 100:+.1f}%)."
    )
    incl = a15[7] + a15[8]
    emit(
        f"    Cropland, inclusive (NLCD 81+82): NLCD {incl:,.0f} vs Chen "
        f"{b15[8]:,.0f} km^2 ({(b15[8] - incl) / incl * 100:+.1f}%)."
    )
    emit(
        f"  * Chen Water + No data = {b15[0] + nod15:,.0f} km^2 vs NLCD Water "
        f"{a15[0]:,.0f} km^2 ({(b15[0] + nod15 - a15[0]) / a15[0] * 100:+.1f}%):"
    )
    emit("    Chen's nodata inside CONUS is coastal water NLCD maps as Open Water.")
    emit()

    # ---- 2020 -------------------------------------------------------------
    a20, ta20 = nl["2020"]
    ssps = ["2020_SSP1_RCP19", "2020_SSP2_RCP45", "2020_SSP4_RCP60", "2020_SSP5_RCP85"]
    emit("=" * 78)
    emit("2020  --  NLCD (30 m) vs Chen2022 SSP scenarios (1 km)   [km^2]")
    emit("=" * 78)
    hdr = f"{'class':<14} {'NLCD':>10}"
    for s in ssps:
        hdr += f" {SCENARIO_LABELS[s]:>12}"
    emit(hdr)
    emit("-" * 78)
    for c in COMMON_CLASSES:
        row = f"{COMMON_NAMES[c]:<14} {a20[c]:>10,.0f}"
        for s in ssps:
            row += f" {ch[s][0][c]:>12,.0f}"
        emit(row)
    row = f"{'No data':<14} {0:>10,.0f}"
    for s in ssps:
        row += f" {ch[s][2]:>12,.0f}"
    emit(row)
    emit("-" * 78)
    row = f"{'TOTAL':<14} {ta20:>10,.0f}"
    for s in ssps:
        row += f" {ch[s][1]:>12,.0f}"
    emit(row)
    emit()

    emit("Spread across the four SSPs at 2020 (max - min), largest first:")
    spread = []
    for c in COMMON_CLASSES:
        vals = [ch[s][0][c] for s in ssps]
        spread.append((max(vals) - min(vals), COMMON_NAMES[c], min(vals), max(vals)))
    for sp, name, lo, hi in sorted(spread, reverse=True):
        if sp <= 0:
            continue
        emit(f"  {name:<14} {sp:>9,.0f} km^2   ({lo:,.0f} .. {hi:,.0f})")
    emit()
    emit(
        "  For scale, the NLCD-vs-Chen gap for Forest alone is "
        f"{abs(b15[4] - a15[4]):,.0f} km^2 -- an order of magnitude"
    )
    emit("  larger than any spread among the SSPs five years after their 2015 start.")

    # ---- CSVs -------------------------------------------------------------
    p1 = args.outdir / "landcover_areas_2015.csv"
    with p1.open("w") as f:
        f.write("class,nlcd_2015_km2,nlcd_2015_pct,chen_2015_km2,chen_2015_pct\n")
        for c in COMMON_CLASSES:
            f.write(
                f"{COMMON_NAMES[c]},{a15[c]:.1f},{a15[c] / ta15 * 100:.4f},"
                f"{b15[c]:.1f},{b15[c] / tb15 * 100:.4f}\n"
            )
        f.write(f"No data,0.0,0.0,{nod15:.1f},{nod15 / tb15 * 100:.4f}\n")

    p2 = args.outdir / "landcover_areas_2020.csv"
    with p2.open("w") as f:
        f.write("class,nlcd_2020_km2," + ",".join(f"{s}_km2" for s in ssps) + "\n")
        for c in COMMON_CLASSES:
            f.write(
                f"{COMMON_NAMES[c]},{a20[c]:.1f},"
                + ",".join(f"{ch[s][0][c]:.1f}" for s in ssps)
                + "\n"
            )
        f.write("No data,0.0," + ",".join(f"{ch[s][2]:.1f}" for s in ssps) + "\n")

    p3 = args.outdir / "landcover_tables.txt"
    p3.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {p1}\nwrote {p2}\nwrote {p3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
