#!/usr/bin/env python
"""2020-only comparison: NLCD-derived vs Chen2022-derived ELM PFT.

Scope, per request: PCT_NATVEG and PCT_NAT_PFT only, year 2020 only.

  NLCD-derived  elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc  (time index 170)
  Chen2022      the four SSP files at their 2020 slice (time index 1)

Note `chen2022_landuse_CONUS_2015_1_24deg.nc` carries 2015 only and therefore
cannot enter a 2020 comparison; the 2020 Chen state comes from the SSP files.
All five scenarios share Chen's 2015 start, so at 2020 they are only five years
apart — that is the point of the spread panels.

Reads the cached arrays from script 30 (outputs/interim/elmpft_compare.npz);
run 30 first. Both products are on the identical 1/24 deg grid, so every
number here is a cell-by-cell comparison with no regridding.

See REFERENCE.md 11 for why the 17-PFT axis is not directly comparable and
must be aggregated to functional groups before being quoted.
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
REP = "SSP2_RCP45"  # representative scenario for the maps (a real one, not a mean)
GROUPS = {
    "Bare": [0],
    "Tree": [1, 2, 3, 4, 5, 6, 7, 8],
    "Shrub": [9, 10, 11],
    "Grass": [12, 13, 14],
    "Crop": [15, 16],
}
EXTENT = (-125.0, -65.0, 25.0, 50.0)
COLS = ["#f6c026", "#d9822b", "#c0392b", "#7d3c98"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--npz", type=Path, default=Path("outputs/interim/elmpft_compare.npz"))
    ap.add_argument("--outdir", type=Path, default=Path("outputs/figures"))
    ap.add_argument("--tabdir", type=Path, default=Path("outputs/interim"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    z = np.load(args.npz, allow_pickle=True)
    conus, area = z["conus"], z["area"]
    names = [str(x) for x in z["names"]]

    nl_nv = z["nlcd_2020_natveg"]
    nl_pf = z["nlcd_2020_pft"]
    ch_nv = {s: z[f"chen_2020_{s}_natveg"] for s in SSPS}
    ch_pf = {s: z[f"chen_2020_{s}_pft"] for s in SSPS}

    w_nl = np.where(conus, nl_nv, 0.0) / 100.0 * area
    w_ch = {s: np.where(conus, ch_nv[s], 0.0) / 100.0 * area for s in SSPS}

    def pft_areas(pft, w):
        return (pft / 100.0 * w[None, :, :]).sum(axis=(1, 2))

    nl_p = pft_areas(nl_pf, w_nl)
    ch_p = {s: pft_areas(ch_pf[s], w_ch[s]) for s in SSPS}

    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit("=" * 80)
    emit("2020  --  NLCD-derived vs Chen2022-derived ELM PFT")
    emit("        shared 1/24 deg grid (601 x 1441), cell by cell, no regridding")
    emit(f"        CONUS domain: {int(conus.sum()):,} cells, "
         f"{float(area[conus].sum()):,.0f} km^2 grid-cell area")
    emit("=" * 80)
    emit()

    # ---- PCT_NATVEG -------------------------------------------------------
    nl_a = float(w_nl.sum())
    emit("PCT_NATVEG  [km^2]   (% of whole grid cell in both products)")
    emit("-" * 80)
    emit(f"  {'NLCD-derived 2020':<26} {nl_a:>12,.0f}")
    for s in SSPS:
        a = float(w_ch[s].sum())
        emit(f"  {'Chen ' + SSP_LAB[s]:<26} {a:>12,.0f}  "
             f"{a - nl_a:>+10,.0f}  ({(a - nl_a) / nl_a * 100:+.1f}%)")
    sp = max(float(w_ch[s].sum()) for s in SSPS) - min(float(w_ch[s].sum()) for s in SSPS)
    emit(f"  {'spread across 4 SSPs':<26} {sp:>12,.0f}   "
         f"<- vs a ~{abs(np.mean([float(w_ch[s].sum()) for s in SSPS]) - nl_a):,.0f} product gap")
    emit()

    # ---- per PFT ----------------------------------------------------------
    emit("PCT_NAT_PFT  --  area per PFT [km^2]")
    emit("  (= cell_area * PCT_NATVEG/100 * PCT_NAT_PFT/100)")
    emit("-" * 80)
    emit(f"{'':<38} {'NLCD':>10}" + "".join(f" {SSP_LAB[s]:>11}" for s in SSPS))
    for k, nm in enumerate(names):
        flag = ""
        if k in (9, 10):
            flag = "  <- NLCD 50/50 split artifact"
        elif k in (2, 3, 4, 5, 6, 8, 11, 12, 16) and nl_p[k] == 0:
            flag = "  <- zero by construction (NLCD)"
        emit(f"{k:>2} {nm:<35} {nl_p[k]:>10,.0f}"
             + "".join(f" {ch_p[s][k]:>11,.0f}" for s in SSPS) + flag)
    emit("-" * 80)
    emit(f"{'   TOTAL':<38} {nl_p.sum():>10,.0f}"
         + "".join(f" {ch_p[s].sum():>11,.0f}" for s in SSPS))
    emit()
    emit("  NLCD PFT 9 and PFT 10 are elementwise identical fields (max|diff| = 0.0):")
    emit("  the NLCD product splits NLCD's single Shrub/Scrub class 50/50. Comparing")
    emit("  either one alone is meaningless -- only PFT 9+10+11 (Shrub) is real.")
    emit("  NLCD populates 8 of 17 PFTs; Chen populates 14. Aggregate before quoting.")
    emit()

    # ---- functional groups ------------------------------------------------
    def garea(pft, w, idx):
        return float((pft[idx].sum(axis=0) / 100.0 * w).sum())

    g = list(GROUPS)
    nl_g = {k: garea(nl_pf, w_nl, GROUPS[k]) for k in g}
    ch_g = {s: {k: garea(ch_pf[s], w_ch[s], GROUPS[k]) for k in g} for s in SSPS}

    emit("PCT_NAT_PFT aggregated to functional groups [km^2]  <- quote this")
    emit("-" * 80)
    emit(f"{'group':<8} {'NLCD':>11}" + "".join(f" {SSP_LAB[s]:>11}" for s in SSPS)
         + f" {'gap':>10} {'spread':>9}")
    for k in g:
        vals = np.array([ch_g[s][k] for s in SSPS])
        gap = vals.mean() - nl_g[k]
        emit(f"{k:<8} {nl_g[k]:>11,.0f}"
             + "".join(f" {ch_g[s][k]:>11,.0f}" for s in SSPS)
             + f" {gap:>+10,.0f} {vals.max() - vals.min():>9,.0f}")
    emit("-" * 80)
    emit()
    emit("  'gap'    = Chen(mean of the 4 SSPs) - NLCD   : disagreement between products")
    emit("  'spread' = max - min across the 4 SSPs       : disagreement between scenarios")
    emit()
    ratios = []
    for k in g:
        vals = np.array([ch_g[s][k] for s in SSPS])
        spr = vals.max() - vals.min()
        gap = abs(vals.mean() - nl_g[k])
        ratios.append((gap / spr if spr > 0 else np.inf, k, gap, spr))
    for r, k, gap, spr in sorted(ratios, reverse=True):
        emit(f"    {k:<8} product gap is {r:>5.1f}x the scenario spread "
             f"({gap:,.0f} vs {spr:,.0f} km^2)")
    emit()

    (args.tabdir / "elmpft_2020_tables.txt").write_text("\n".join(lines) + "\n")

    # ---- fig10: PCT_NATVEG ------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.4), layout="constrained")
    a = np.where(conus, nl_nv, np.nan)
    b = np.where(conus, ch_nv[REP], np.nan)
    for ax, arr, ttl, kw in (
        (axes[0, 0], a, "NLCD-derived 2020", dict(cmap="YlGn", vmin=0, vmax=100)),
        (axes[0, 1], b, f"Chen2022 {SSP_LAB[REP]} 2020",
         dict(cmap="YlGn", vmin=0, vmax=100)),
        (axes[1, 0], b - a, f"Chen {SSP_LAB[REP]} − NLCD",
         dict(cmap="RdBu_r", vmin=-50, vmax=50)),
    ):
        im = ax.imshow(arr, origin="lower", extent=EXTENT, **kw)
        ax.set_title(ttl, fontsize=11)
        cb = fig.colorbar(im, ax=ax, fraction=0.028, pad=0.015, shrink=0.85)
        cb.set_label("% of grid cell" if "cmap" in kw and kw["cmap"] == "YlGn"
                     else "Chen − NLCD [% of cell]", fontsize=8)
        cb.ax.tick_params(labelsize=8)
    stack = np.stack([np.where(conus, ch_nv[s], np.nan) for s in SSPS])
    spread_map = np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)
    im = axes[1, 1].imshow(spread_map, origin="lower", extent=EXTENT, cmap="magma_r",
                           vmin=0, vmax=50)
    axes[1, 1].set_title("spread across the 4 SSPs (max − min)", fontsize=11)
    cb = fig.colorbar(im, ax=axes[1, 1], fraction=0.028, pad=0.015, shrink=0.85)
    cb.set_label("% of cell", fontsize=8)
    cb.ax.tick_params(labelsize=8)
    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(
        "PCT_NATVEG 2020 — the product gap (bottom left) dwarfs the scenario "
        "spread (bottom right)",
        fontsize=13,
    )
    p = args.outdir / "fig10_elmpft_natveg_2020.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    # ---- fig11: 17 PFT bars ----------------------------------------------
    x = np.arange(17)
    w = 0.16
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.bar(x - 2 * w, nl_p / 1e3, w, label="NLCD-derived 2020", color="#2c6fbb")
    for i, s in enumerate(SSPS):
        ax.bar(x + (i - 1) * w, ch_p[s] / 1e3, w, label=f"Chen {SSP_LAB[s]} 2020",
               color=COLS[i])
    ax.set_xticks(x)
    ax.set_xticklabels([f"{k} {n}" for k, n in enumerate(names)], rotation=40,
                       ha="right", fontsize=8)
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "PCT_NAT_PFT — area per PFT, 2020. Two of the biggest gaps are mapping "
        "conventions, not land cover.",
        fontsize=12,
    )
    ax.annotate(
        "NLCD splits Shrub/Scrub 50/50 →\nPFT 9 and PFT 10 are *identical* fields.\n"
        "Only their sum is meaningful.",
        xy=(9.3, nl_p[9] / 1e3), xytext=(3.6, nl_p.max() / 1e3 * 0.95),
        fontsize=8.5, color="#8a1a1a",
        arrowprops=dict(arrowstyle="->", color="#8a1a1a", lw=1),
    )
    ax.annotate(
        "boreal/arctic PFTs: zero by construction on the NLCD side\n"
        "(NLCD populates 8 of 17 PFTs; Chen populates 14)",
        xy=(2.0, 120), xytext=(0.3, nl_p.max() / 1e3 * 0.62), fontsize=8.5, color="#333",
        arrowprops=dict(arrowstyle="->", color="#555", lw=0.8),
    )
    fig.tight_layout()
    p = args.outdir / "fig11_elmpft_per_pft_2020.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    # ---- fig12: groups + gap vs spread -----------------------------------
    xg = np.arange(len(g))
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 9.5))
    ax.bar(xg - 2 * w, [nl_g[k] / 1e3 for k in g], w, label="NLCD-derived 2020",
           color="#2c6fbb")
    for i, s in enumerate(SSPS):
        ax.bar(xg + (i - 1) * w, [ch_g[s][k] / 1e3 for k in g], w,
               label=f"Chen {SSP_LAB[s]} 2020", color=COLS[i])
    for i, k in enumerate(g):
        vals = np.array([ch_g[s][k] for s in SSPS])
        ax.annotate(f"{(vals.mean() - nl_g[k]) / nl_g[k] * 100:+.0f}%",
                    (i, max(nl_g[k], vals.max()) / 1e3), ha="center", va="bottom",
                    fontsize=9,
                    color="#c0392b" if abs(vals.mean() - nl_g[k]) / nl_g[k] > 0.1
                    else "#27ae60")
    ax.set_xticks(xg)
    ax.set_xticklabels(g)
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False, fontsize=9, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "PCT_NAT_PFT by functional group, 2020 — NLCD vs the four Chen2022 SSPs "
        "(% = Chen mean vs NLCD)",
        fontsize=12,
    )

    gaps = [abs(np.mean([ch_g[s][k] for s in SSPS]) - nl_g[k]) for k in g]
    sprs = [max(ch_g[s][k] for s in SSPS) - min(ch_g[s][k] for s in SSPS) for k in g]
    ax2.bar(xg - 0.2, [v / 1e3 for v in gaps], 0.4, color="#34495e",
            label="|Chen(mean of SSPs) − NLCD| : product disagreement")
    ax2.bar(xg + 0.2, [v / 1e3 for v in sprs], 0.4, color="#e67e22",
            label="max − min across the 4 SSPs : scenario spread")
    for i in range(len(g)):
        if sprs[i] > 0:
            r = gaps[i] / sprs[i]
            ax2.annotate(f"{r:.1f}×", (i, max(gaps[i], sprs[i]) / 1e3),
                         ha="center", va="bottom", fontsize=9,
                         color="#c0392b" if r < 1 else "#333")
    ax2.set_xticks(xg)
    ax2.set_xticklabels(g)
    ax2.set_ylabel("area  [10³ km²]")
    ax2.legend(frameon=False, fontsize=9)
    ax2.grid(axis="y", alpha=0.3)
    ax2.set_title(
        "At 2020 the choice of dataset dominates the choice of scenario "
        "(× = ratio)",
        fontsize=11,
    )
    fig.tight_layout()
    p = args.outdir / "fig12_elmpft_groups_2020.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    # ---- fig13: group difference maps ------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(14, 7.2), layout="constrained")
    for ax, gname in zip(axes.ravel(), ["Tree", "Shrub", "Grass", "Crop"]):
        idx = GROUPS[gname]
        aa = nl_nv * nl_pf[idx].sum(axis=0) / 100.0
        bb = ch_nv[REP] * ch_pf[REP][idx].sum(axis=0) / 100.0
        d = np.where(conus, bb - aa, np.nan)
        im = ax.imshow(d, origin="lower", extent=EXTENT, cmap="RdBu_r", vmin=-60, vmax=60)
        ax.set_title(gname, fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, fraction=0.028, pad=0.015, shrink=0.85)
        cb.set_label("Chen − NLCD  [% of cell]", fontsize=8)
        cb.ax.tick_params(labelsize=8)
    fig.suptitle(
        f"PCT_NAT_PFT by functional group, 2020 — Chen2022 {SSP_LAB[REP]} minus NLCD\n"
        "(red = Chen has more; the other three SSPs look the same at this scale)",
        fontsize=13,
    )
    p = args.outdir / "fig13_elmpft_group_diff_2020.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")

    print(f"\nwrote {args.tabdir / 'elmpft_2020_tables.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
