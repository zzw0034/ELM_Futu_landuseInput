#!/usr/bin/env python
"""Side-by-side maps of both ELM-PFT products at 2015 and 2020.

  fig14  dominant functional group within natveg -- (NLCD | Chen) x (2015 | 2020)
  fig15  what each product says changed 2015 -> 2020

Maps are of the *functional group*, not the raw 17-PFT axis: PFT 9/10 are an
exact 50/50 tie on the NLCD side, so a per-PFT argmax would be decided by
tie-breaking rather than by data (REFERENCE.md 11).

fig15 is the interesting one. 2015->2020 is the single window where Chen's
projection overlaps observation, so it is the only chance to ask whether the
transient signal -- the thing Chen2022 is actually for -- matches reality.
Chen's 2015 comes from its own historical raster (identical to each SSP file's
2015 slice, their common start), so the delta is internal to each product and
free of the mean-state offset documented in 11.

Reads outputs/interim/elmpft_compare.npz (script 30).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

SSPS = ["SSP1_RCP19", "SSP2_RCP45", "SSP4_RCP60", "SSP5_RCP85"]
SSP_LAB = {
    "SSP1_RCP19": "SSP1-RCP1.9",
    "SSP2_RCP45": "SSP2-RCP4.5",
    "SSP4_RCP60": "SSP4-RCP6.0",
    "SSP5_RCP85": "SSP5-RCP8.5",
}
REP = "SSP2_RCP45"
GROUPS = {
    "Bare": [0],
    "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
    "Shrub": [9, 10, 11],
    "Grass": [12, 13, 14],
    "Crop": [15, 16],
}
GCOL = {
    "Bare": "#b3ac9f",
    "Tree": "#1c5f2c",
    "Shrub": "#ccb879",
    "Grass": "#dfdfc2",
    "Crop": "#ab6c28",
}
EXTENT = (-125.0, -65.0, 25.0, 50.0)
GN = list(GROUPS)
CMAP = ListedColormap([GCOL[g] for g in GN] + ["#ffffff"])


def dom_group(natveg, pft, conus):
    """Index of the dominant functional group within natveg; len(GN) = no data."""
    stack = np.stack([pft[GROUPS[g]].sum(axis=0) for g in GN])
    d = stack.argmax(axis=0).astype(np.int16)
    d[~(conus & (natveg > 0) & (stack.sum(axis=0) > 0))] = len(GN)
    return d


def group_area(pft, w, idx):
    return float((pft[idx].sum(axis=0) / 100.0 * w).sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", type=Path, default=Path("outputs/interim/elmpft_compare.npz"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/figures"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    z = np.load(args.npz, allow_pickle=True)
    conus, area = z["conus"], z["area"]

    panels = {
        ("NLCD-derived", 2015): (z["nlcd_2015_natveg"], z["nlcd_2015_pft"]),
        ("NLCD-derived", 2020): (z["nlcd_2020_natveg"], z["nlcd_2020_pft"]),
        ("Chen2022", 2015): (z["chen_2015_natveg"], z["chen_2015_pft"]),
        ("Chen2022", 2020): (z[f"chen_2020_{REP}_natveg"], z[f"chen_2020_{REP}_pft"]),
    }

    # ---- fig14: dominant functional group, 2x2 ---------------------------
    dom = {k: dom_group(*v, conus) for k, v in panels.items()}

    # Quantify the claim the title makes, rather than leaving it to the eye:
    # a dominant-class map amplifies near-ties, so small area changes can look
    # like large regional flips.
    valid = conus.copy()
    for d in dom.values():
        valid &= d < len(GN)
    n = int(valid.sum())

    def frac_diff(a, b):
        return 100.0 * float(((dom[a] != dom[b]) & valid).sum()) / n

    t_nl = frac_diff(("NLCD-derived", 2015), ("NLCD-derived", 2020))
    t_ch = frac_diff(("Chen2022", 2015), ("Chen2022", 2020))
    p15 = frac_diff(("NLCD-derived", 2015), ("Chen2022", 2015))
    p20 = frac_diff(("NLCD-derived", 2020), ("Chen2022", 2020))
    print(f"    dominant-group disagreement over {n:,} cells: "
          f"temporal NLCD {t_nl:.1f}%, Chen {t_ch:.1f}%; "
          f"product 2015 {p15:.1f}%, 2020 {p20:.1f}%")

    fig, axes = plt.subplots(2, 2, figsize=(14, 7.4), layout="constrained")
    for r, yr in enumerate((2015, 2020)):
        for c, prod in enumerate(("NLCD-derived", "Chen2022")):
            ax = axes[r, c]
            ax.imshow(dom[(prod, yr)], origin="lower", extent=EXTENT,
                      cmap=CMAP, vmin=0, vmax=len(GN), interpolation="nearest")
            sub = f" ({SSP_LAB[REP]})" if prod == "Chen2022" and yr == 2020 else ""
            ax.set_title(f"{prod} {yr}{sub}", fontsize=11)
            ax.set_xticks([])
            ax.set_yticks([])
    fig.legend(
        handles=[mpatches.Patch(facecolor=GCOL[g], edgecolor="0.3", label=g) for g in GN]
        + [mpatches.Patch(facecolor="#ffffff", edgecolor="0.3", label="no natveg")],
        loc="outside lower center", ncol=6, frameon=False, fontsize=10,
    )
    fig.suptitle(
        "Dominant plant functional group within PCT_NATVEG — shared 1/24° grid\n"
        f"Left↔right (product) disagrees on {p15:.0f}% of cells; "
        f"top↔bottom (2015→2020) on only {t_nl:.0f}% (NLCD) and {t_ch:.0f}% (Chen)"
        " — the product gap is ~10× the 5-year signal",
        fontsize=12,
    )
    p = args.outdir / "fig14_elmpft_dominant_group_2015_2020.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    # ---- fig15: 2015 -> 2020 change --------------------------------------
    d_nl = np.where(conus, z["nlcd_2020_natveg"] - z["nlcd_2015_natveg"], np.nan)
    d_ch = np.where(conus, z[f"chen_2020_{REP}_natveg"] - z["chen_2015_natveg"], np.nan)

    # CONUS is ~2.4:1, so the map row needs far less height than the bar row --
    # give it less, or the panels float in whitespace.
    fig = plt.figure(figsize=(13, 7.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[0.62, 1], hspace=0.10, wspace=0.10)
    for j, (d, ttl) in enumerate(
        ((d_nl, "NLCD-derived: 2020 − 2015 (observed)"),
         (d_ch, f"Chen2022 {SSP_LAB[REP]}: 2020 − 2015 (projected)")),
    ):
        ax = fig.add_subplot(gs[0, j])
        im = ax.imshow(d, origin="lower", extent=EXTENT, cmap="PuOr_r", vmin=-10, vmax=10)
        ax.set_title(ttl, fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label("Δ PCT_NATVEG [% of cell]", fontsize=8)
        cb.ax.tick_params(labelsize=8)

    # per-group change, each product against its own 2015
    w15_nl = np.where(conus, z["nlcd_2015_natveg"], 0.0) / 100.0 * area
    w20_nl = np.where(conus, z["nlcd_2020_natveg"], 0.0) / 100.0 * area
    w15_ch = np.where(conus, z["chen_2015_natveg"], 0.0) / 100.0 * area

    d_group = {"NLCD (observed)": [
        group_area(z["nlcd_2020_pft"], w20_nl, GROUPS[g])
        - group_area(z["nlcd_2015_pft"], w15_nl, GROUPS[g]) for g in GN]}
    for s in SSPS:
        w20 = np.where(conus, z[f"chen_2020_{s}_natveg"], 0.0) / 100.0 * area
        d_group[SSP_LAB[s]] = [
            group_area(z[f"chen_2020_{s}_pft"], w20, GROUPS[g])
            - group_area(z["chen_2015_pft"], w15_ch, GROUPS[g]) for g in GN]

    ax = fig.add_subplot(gs[1, :])
    x = np.arange(len(GN))
    wd = 0.16
    cols = ["#2c6fbb", "#f6c026", "#d9822b", "#c0392b", "#7d3c98"]
    for i, (lab, vals) in enumerate(d_group.items()):
        ax.bar(x + (i - 2) * wd, [v / 1e3 for v in vals], wd, label=lab, color=cols[i])
    ax.axhline(0, color="0.3", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(GN)
    ax.set_ylabel("Δ area 2015→2020  [10³ km²]")
    ax.legend(frameon=False, fontsize=9, ncol=5)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "Change per functional group, each product measured against its own 2015 — "
        "the 5-year signals disagree in sign for Tree, Grass and Crop",
        fontsize=11,
    )
    fig.suptitle(
        "2015 → 2020: what each product says changed\n"
        "(the one window where Chen2022's projection overlaps observation)",
        fontsize=13,
    )
    fig.subplots_adjust(top=0.86)
    p = args.outdir / "fig15_elmpft_change_2015_2020.png"
    fig.savefig(p, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  {p}")

    # ---- table ------------------------------------------------------------
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    emit()
    emit("=" * 78)
    emit("2015 -> 2020 change per functional group [km^2], each product vs its own 2015")
    emit("=" * 78)
    emit(f"{'group':<8}" + "".join(f" {k:>15}" for k in d_group))
    emit("-" * 78)
    for i, g in enumerate(GN):
        emit(f"{g:<8}" + "".join(f" {d_group[k][i]:>+15,.0f}" for k in d_group))
    emit("-" * 78)
    emit(f"{'TOTAL':<8}" + "".join(f" {sum(d_group[k]):>+15,.0f}" for k in d_group))
    emit()
    emit("Sign agreement between observed (NLCD) and projected (Chen) 2015->2020:")
    for i, g in enumerate(GN):
        o = d_group["NLCD (observed)"][i]
        signs = [np.sign(d_group[SSP_LAB[s]][i]) == np.sign(o) for s in SSPS]
        emit(f"  {g:<8} NLCD {o:>+10,.0f} | SSPs agreeing in sign: {sum(signs)}/4")
    emit()
    emit("Caveat: the two are not measuring the same thing. NLCD 2020-2015 is")
    emit("observed change in a 30 m product; Chen 2020-2015 is a 1 km projection")
    emit("stepping off its own 2015. Disagreement in sign over 5 years does not")
    emit("invalidate Chen's long-term trajectory, but it does mean the transient")
    emit("cannot be validated against NLCD at this lead time.")
    (Path("outputs/interim") / "elmpft_change_2015_2020.txt").write_text(
        "\n".join(lines) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
