#!/usr/bin/env python
"""Figures for the ELM-PFT comparison (NLCD-derived vs Chen2022-derived).

  fig6  PCT_NATVEG: NLCD 2015 | Chen 2015 | difference
  fig7  PCT_NAT_PFT: area per PFT, all 17, 2015 -- with the mapping artifacts
        flagged, because two of them dominate the raw ranking
  fig8  PCT_NAT_PFT aggregated to plant functional groups (the level at which
        the two products are actually comparable), 2015 and 2020
  fig9  where they disagree: group cover fraction, Chen - NLCD

Read fig7 before fig8. The 17-PFT breakdown is *not* an apples-to-apples axis
even though both files nominally share it:

  * The NLCD product splits NLCD's single Shrub/Scrub class 50/50 into PFT 9
    (broadleaf_evergreen_shrub) and PFT 10 (broadleaf_deciduous_temperate
    shrub) -- the two fields are elementwise identical. PFT 9 alone therefore
    shows a -896,000 km^2 "disagreement" that is pure convention.
  * The NLCD product populates only 8 of 17 PFTs; Chen populates 14. Every
    boreal/arctic PFT is zero-by-construction on the NLCD side.
  * Chen splits its Mixed C3/C4 grass class 50/50 into PFT 13/14 (REFERENCE.md
    §3), so the C3-vs-C4 split is convention on that side.

Summing to functional groups (bare / tree / shrub / grass / crop) removes all
three, which is why fig8 is the one to quote.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

SSPS = ["SSP1_RCP19", "SSP2_RCP45", "SSP4_RCP60", "SSP5_RCP85"]
SSP_LAB = {
    "SSP1_RCP19": "SSP1-RCP1.9",
    "SSP2_RCP45": "SSP2-RCP4.5",
    "SSP4_RCP60": "SSP4-RCP6.0",
    "SSP5_RCP85": "SSP5-RCP8.5",
}
GROUPS = {
    "Bare": [0],
    "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
    "Shrub": [9, 10, 11],
    "Grass": [12, 13, 14],
    "Crop": [15, 16],
}
EXTENT = (-125.0, -65.0, 25.0, 50.0)


def group_pct_of_cell(natveg, pft, idx):
    """% of the whole grid cell covered by a PFT group."""
    return natveg * pft[idx].sum(axis=0) / 100.0


def fig6_natveg(z, outdir: Path) -> None:
    conus = z["conus"]
    a = np.where(conus, z["nlcd_2015_natveg"], np.nan)
    b = np.where(conus, z["chen_2015_natveg"], np.nan)
    fig, axes = plt.subplots(3, 1, figsize=(11, 13.5))
    for ax, arr, ttl in (
        (axes[0], a, "NLCD-derived ELM PFT — PCT_NATVEG 2015"),
        (axes[1], b, "Chen2022-derived — PCT_NATVEG 2015"),
    ):
        im = ax.imshow(arr, origin="lower", extent=EXTENT, cmap="YlGn", vmin=0, vmax=100)
        ax.set_title(ttl, fontsize=11)
        fig.colorbar(im, ax=ax, fraction=0.023, pad=0.02).set_label("% of grid cell")
    d = b - a
    im = axes[2].imshow(
        d, origin="lower", extent=EXTENT, cmap="RdBu_r", vmin=-50, vmax=50
    )
    axes[2].set_title(
        "Difference (Chen2022 − NLCD)  —  CONUS totals agree to +2.2%", fontsize=11
    )
    fig.colorbar(im, ax=axes[2], fraction=0.023, pad=0.02).set_label(
        "Chen − NLCD  [% of cell]"
    )
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(
        "PCT_NATVEG on the shared 1/24° grid — cell-by-cell, no regridding",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    p = outdir / "fig6_elmpft_natveg_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def fig7_pft_bars(z, areas_csv, outdir: Path) -> None:
    names = [str(x) for x in z["names"]]
    d = np.genfromtxt(areas_csv, delimiter=",", names=True, dtype=None, encoding="utf-8")
    nl = np.array([d["nlcd_2015"][k] for k in range(17)]) / 1e3
    ch = np.array([d["chen_2015"][k] for k in range(17)]) / 1e3

    x = np.arange(17)
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.bar(x - 0.2, nl, 0.4, label="NLCD-derived 2015", color="#2c6fbb")
    ax.bar(x + 0.2, ch, 0.4, label="Chen2022-derived 2015", color="#d9822b")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{k} {n}" for k, n in enumerate(names)], rotation=40, ha="right",
                       fontsize=8)
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "PCT_NAT_PFT — area per PFT, 2015. The two largest gaps are mapping "
        "conventions, not land cover.",
        fontsize=12,
    )
    ax.annotate(
        "NLCD Shrub/Scrub split 50/50 →\nPFT 9 and PFT 10 are *identical* fields.\n"
        "Only their sum is meaningful.",
        xy=(9.5, nl[9]), xytext=(4.2, max(nl.max(), ch.max()) * 0.82),
        fontsize=8.5, color="#8a1a1a",
        arrowprops=dict(arrowstyle="->", color="#8a1a1a", lw=1),
    )
    for k in (2, 3, 8, 11, 12):
        ax.annotate("", xy=(k + 0.2, ch[k]), xytext=(k + 0.2, ch[k] + 90),
                    arrowprops=dict(arrowstyle="->", color="#555", lw=0.8))
    ax.annotate(
        "boreal/arctic PFTs: zero by construction\non the NLCD side (8 of 17 PFTs "
        "populated vs Chen's 14)",
        xy=(3.0, 260), xytext=(0.3, max(nl.max(), ch.max()) * 0.55),
        fontsize=8.5, color="#333",
    )
    fig.tight_layout()
    p = outdir / "fig7_elmpft_per_pft_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def fig8_groups(z, outdir: Path) -> None:
    conus, area = z["conus"], z["area"]

    def garea(natveg, pft, idx):
        w = np.where(conus, natveg, 0.0) / 100.0 * area
        return float((pft[idx].sum(axis=0) / 100.0 * w).sum())

    g = list(GROUPS)
    nl15 = [garea(z["nlcd_2015_natveg"], z["nlcd_2015_pft"], GROUPS[k]) for k in g]
    ch15 = [garea(z["chen_2015_natveg"], z["chen_2015_pft"], GROUPS[k]) for k in g]
    nl20 = [garea(z["nlcd_2020_natveg"], z["nlcd_2020_pft"], GROUPS[k]) for k in g]
    ssp20 = {
        s: [
            garea(z[f"chen_2020_{s}_natveg"], z[f"chen_2020_{s}_pft"], GROUPS[k])
            for k in g
        ]
        for s in SSPS
    }

    x = np.arange(len(g))
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    ax.bar(x - 0.2, [v / 1e3 for v in nl15], 0.4, label="NLCD-derived 2015",
           color="#2c6fbb")
    ax.bar(x + 0.2, [v / 1e3 for v in ch15], 0.4, label="Chen2022-derived 2015",
           color="#d9822b")
    for i, (u, v) in enumerate(zip(nl15, ch15)):
        ax.annotate(f"{(v - u) / u * 100:+.0f}%", (i, max(u, v) / 1e3),
                    ha="center", va="bottom", fontsize=9,
                    color="#c0392b" if abs(v - u) / u > 0.1 else "#27ae60")
    ax.set_xticks(x)
    ax.set_xticklabels(g)
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "PCT_NAT_PFT aggregated to functional groups, 2015 — the level at which "
        "the two products are comparable",
        fontsize=12,
    )

    w = 0.16
    ax2.bar(x - 2 * w, [v / 1e3 for v in nl20], w, label="NLCD-derived 2020",
            color="#2c6fbb")
    cols = ["#f6c026", "#d9822b", "#c0392b", "#7d3c98"]
    for i, s in enumerate(SSPS):
        ax2.bar(x + (i - 1) * w, [v / 1e3 for v in ssp20[s]], w,
                label=f"Chen2022 {SSP_LAB[s]} 2020", color=cols[i])
    ax2.set_xticks(x)
    ax2.set_xticklabels(g)
    ax2.set_ylabel("area  [10³ km²]")
    ax2.legend(frameon=False, fontsize=9, ncol=2)
    ax2.grid(axis="y", alpha=0.3)
    ax2.set_title(
        "2020 — the four SSPs are indistinguishable at this scale; the gap to "
        "NLCD is not",
        fontsize=12,
    )
    fig.tight_layout()
    p = outdir / "fig8_elmpft_groups.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    print("\n  functional-group areas [km^2], 2015:")
    print(f"    {'group':<8} {'NLCD':>11} {'Chen':>11} {'diff':>11} {'rel':>7}")
    for i, k in enumerate(g):
        print(f"    {k:<8} {nl15[i]:>11,.0f} {ch15[i]:>11,.0f} "
              f"{ch15[i] - nl15[i]:>+11,.0f} {(ch15[i] - nl15[i]) / nl15[i] * 100:>+6.1f}%")


def fig9_group_diff_maps(z, outdir: Path) -> None:
    conus = z["conus"]
    show = ["Tree", "Shrub", "Grass", "Crop"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.2), layout="constrained")
    for ax, gname in zip(axes.ravel(), show):
        idx = GROUPS[gname]
        a = group_pct_of_cell(z["nlcd_2015_natveg"], z["nlcd_2015_pft"], idx)
        b = group_pct_of_cell(z["chen_2015_natveg"], z["chen_2015_pft"], idx)
        d = np.where(conus, b - a, np.nan)
        im = ax.imshow(d, origin="lower", extent=EXTENT, cmap="RdBu_r",
                       vmin=-60, vmax=60)
        ax.set_title(gname, fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, fraction=0.028, pad=0.015, shrink=0.85)
        cb.set_label("Chen − NLCD  [% of cell]", fontsize=8)
        cb.ax.tick_params(labelsize=8)
    fig.suptitle(
        "PCT_NAT_PFT by functional group, 2015 — Chen2022 minus NLCD\n"
        "(red = Chen has more; shared 1/24° grid, cell by cell)",
        fontsize=13,
    )
    p = outdir / "fig9_elmpft_group_diff_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", type=Path, default=Path("outputs/interim/elmpft_compare.npz"))
    ap.add_argument("--csv", type=Path, default=Path("outputs/interim/elmpft_areas.csv"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/figures"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    z = np.load(args.npz, allow_pickle=True)
    print("figures:")
    fig6_natveg(z, args.outdir)
    fig7_pft_bars(z, args.csv, args.outdir)
    fig8_groups(z, args.outdir)
    fig9_group_diff_maps(z, args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
