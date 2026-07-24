#!/usr/bin/env python
"""fig16 -- dominant PFT maps for a visual check: (NLCD | Chen) x (2015 | 2020).

Straight `argmax` over the 17-PFT axis is not honest here: *both* products carry
a 50/50 split of a source class they could not resolve, so over large regions
two PFTs tie exactly for the maximum and the winner would be decided by numpy's
lower-index tie-break rather than by data.

  NLCD  PFT 9 == PFT 10 (Shrub/Scrub split 50/50)      -> 20.0% of natveg cells
        99.4% of its ties; the Great Basin / Southwest shrublands, which a
        plain argmax would render entirely as `broadleaf_evergreen_shrub`.
  Chen  PFT 13 == PFT 14 (Mixed C3/C4 grass split 50/50, REFERENCE.md 3)
        -> 11.1% of natveg cells, 99.9% of its ties; the Great Plains.

Each product's artifact therefore lands in a *different* region, so ties are
detected and split into their own categories rather than silently broken. They
are coloured by growth form (the map still reads ecologically) but named as ties
in the legend. Everything else is a plain dominant-PFT map, both products on
their shared 1/24 deg grid, no regridding.

Reads outputs/interim/elmpft_compare.npz (script 30).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from elm_landuse.chen_classes import ELM_PFT_NAMES  # noqa: E402

REP = "SSP2_RCP45"
REP_LAB = "SSP2-RCP4.5"
EXTENT = (-125.0, -65.0, 25.0, 50.0)

# Grouped by growth form so the map reads at a glance: greens = trees,
# golds = shrubs, pale yellows = grass, brown = crop.
PFT_COLORS = [
    "#9e9e9e",  # 0  Bare_Ground
    "#1b5e20",  # 1  needleleaf_evergreen_temperate_tree
    "#00695c",  # 2  needleleaf_evergreen_boreal_tree
    "#4db6ac",  # 3  needleleaf_deciduous_boreal_tree
    "#003d00",  # 4  broadleaf_evergreen_tropical_tree
    "#2e7d32",  # 5  broadleaf_evergreen_temperate_tree
    "#7cb342",  # 6  broadleaf_deciduous_tropical_tree
    "#8bc34a",  # 7  broadleaf_deciduous_temperate_tree
    "#c5e1a5",  # 8  broadleaf_deciduous_boreal_tree
    "#ff8f00",  # 9  broadleaf_evergreen_shrub
    "#d4a017",  # 10 broadleaf_deciduous_temperate_shrub
    "#ffe082",  # 11 broadleaf_deciduous_boreal_shrub
    "#b39ddb",  # 12 c3_arctic_grass
    "#ede7a6",  # 13 c3_non-arctic_grass
    "#ffd54f",  # 14 c4_grass
    "#a1552a",  # 15 crop
    "#c98a5e",  # 16 irrigated_crop (never populated; kept off the red/pink used for ties)
]
NP = len(ELM_PFT_NAMES)

# Tie categories. Deliberately loud red/pink -- NOT a growth-form hue. A tie is
# not ecology, it is the product failing to resolve a class, so it should read
# as an alarm rather than as vegetation. Earlier attempts to keep these in the
# shrub/grass hue (first midway between the tied PFTs, then a darker version)
# both let the artifact blend into the real classes, which is precisely what
# this figure exists to prevent.
TIE_SHRUB = NP  # PFT 9 == 10, the NLCD Shrub/Scrub 50/50 split
TIE_GRASS = NP + 1  # PFT 13 == 14, the Chen Mixed C3/C4 50/50 split
TIE_OTHER = NP + 2  # incidental ties, <1% in both products
NODATA = NP + 3

TIE_COLORS = ["#e53935", "#ff4fa3", "#7b1fa2"]  # red, hot pink, purple
NODATA_COLOR = "#ffffff"
CMAP = ListedColormap(PFT_COLORS + TIE_COLORS + [NODATA_COLOR])


def dominant_pft(natveg, pft, conus):
    """argmax over natpft, with ties for the maximum split out, not broken.

    Returns int16 (ny, nx): 0..16 = that PFT dominates outright; TIE_SHRUB /
    TIE_GRASS / TIE_OTHER = tied for the maximum; NODATA = no natveg.
    """
    mx = pft.max(axis=0)
    at_max = pft == mx[None, :, :]
    n_at_max = at_max.sum(axis=0)
    d = pft.argmax(axis=0).astype(np.int16)

    tied = n_at_max > 1
    d[tied] = TIE_OTHER
    only = lambda a, b: tied & (n_at_max == 2) & at_max[a] & at_max[b]  # noqa: E731
    d[only(9, 10)] = TIE_SHRUB
    d[only(13, 14)] = TIE_GRASS

    d[~(conus & (natveg > 0) & (mx > 0))] = NODATA
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", type=Path, default=Path("outputs/interim/elmpft_compare.npz"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/figures"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    z = np.load(args.npz, allow_pickle=True)
    conus = z["conus"]

    panels = {
        ("NLCD-derived", 2015): (z["nlcd_2015_natveg"], z["nlcd_2015_pft"]),
        ("NLCD-derived", 2020): (z["nlcd_2020_natveg"], z["nlcd_2020_pft"]),
        ("Chen2022", 2015): (z["chen_2015_natveg"], z["chen_2015_pft"]),
        ("Chen2022", 2020): (z[f"chen_2020_{REP}_natveg"], z[f"chen_2020_{REP}_pft"]),
    }
    dom = {k: dominant_pft(*v, conus) for k, v in panels.items()}

    names = list(ELM_PFT_NAMES) + [
        "TIE shrub 9≡10", "TIE grass 13≡14", "TIE other",
    ]
    # Report what actually shows up, so the legend can be read against numbers.
    print("dominant-PFT composition (% of CONUS natveg cells):")
    for k in panels:
        d = dom[k][conus & (dom[k] < NODATA)]
        parts = [
            f"{names[c]} {100 * (d == c).sum() / d.size:.1f}%"
            for c in np.unique(d)
            if 100 * (d == c).sum() / d.size >= 0.05
        ]
        print(f"  {k[0]} {k[1]}: " + ", ".join(parts))

    fig, axes = plt.subplots(2, 2, figsize=(15, 8.0), layout="constrained")
    for r, yr in enumerate((2015, 2020)):
        for c, prod in enumerate(("NLCD-derived", "Chen2022")):
            ax = axes[r, c]
            ax.imshow(dom[(prod, yr)], origin="lower", extent=EXTENT, cmap=CMAP,
                      vmin=0, vmax=NODATA, interpolation="nearest")
            sub = f" ({REP_LAB})" if prod == "Chen2022" and yr == 2020 else ""
            ax.set_title(f"{prod} {yr}{sub}", fontsize=12)
            ax.set_xticks([])
            ax.set_yticks([])

    used = set()
    for d in dom.values():
        used.update(np.unique(d[d < NODATA]).tolist())
    handles = [
        mpatches.Patch(facecolor=PFT_COLORS[k], edgecolor="0.4",
                       label=f"{k} {ELM_PFT_NAMES[k]}")
        for k in range(NP) if k in used
    ]
    tie_labels = {
        TIE_SHRUB: "TIE shrub: PFT 9≡10 — NLCD's Shrub/Scrub 50/50 split",
        TIE_GRASS: "TIE grass: PFT 13≡14 — Chen's Mixed C3/C4 50/50 split",
        TIE_OTHER: "TIE other (incidental, <1%)",
    }
    for code, lab in tie_labels.items():
        if code in used:
            handles.append(
                mpatches.Patch(facecolor=TIE_COLORS[code - NP], edgecolor="0.2",
                               hatch="///", label=lab)
            )
    handles.append(
        mpatches.Patch(facecolor=NODATA_COLOR, edgecolor="0.4", label="no natveg")
    )
    fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False,
               fontsize=9)
    fig.suptitle(
        "Dominant natural PFT — visual check, both products, both years "
        "(shared 1/24° grid, no regridding)\n"
        "RED / PINK = no PFT actually dominates: two tie exactly, from each "
        "product's own 50/50 split of a class it could not resolve\n"
        "NLCD ties on 20% of cells (red — the western shrublands); Chen on 11% "
        "(pink — the Plains grass). Different artifacts, different regions.",
        fontsize=11.5,
    )
    p = args.outdir / "fig16_dominant_pft_2015_2020.png"
    fig.savefig(p, dpi=135)
    plt.close(fig)
    print(f"\n  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
