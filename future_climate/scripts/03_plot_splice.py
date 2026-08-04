#!/usr/bin/env python
"""Is there a discontinuity where the historical forcing hands off to the future?

Historical  Daymet_ERA5_TESSFA2 cpl_bypass, 2000-2023
Future      CanESM5 <ssp> DBCCA Daymet TESSFA2, 2015-2100

Both series are domain-mean annual TBOT and PRECTmms over the same TESSFA2
grid, computed from the same 3-hourly variables (scripts 01 and 02).

A single 2023->2024 step cannot on its own distinguish a real discontinuity
from ordinary interannual variability, so this reports three things:

  1. the step itself, 2023 (hist) -> 2024 (future)
  2. the 2015-2023 OVERLAP bias, future minus historical, same years --
     nine paired years, which is what actually measures the offset
  3. both expressed in units of the historical interannual sigma (2000-2023)

An offset in the overlap is expected and not by itself a defect: the future
is a bias-corrected GCM realization, not a reanalysis, so its individual years
are its own weather, not the observed weather of those years.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/"
           "future_climate/outputs")
SCEN = ["ssp119", "ssp245", "ssp370", "ssp585"]
SLAB = {"ssp119": "SSP1-1.9", "ssp245": "SSP2-4.5",
        "ssp370": "SSP3-7.0", "ssp585": "SSP5-8.5"}
SCOL = {"ssp119": "#1a9850", "ssp245": "#2c7fb8",
        "ssp370": "#7b3294", "ssp585": "#d73027"}
SPLICE = 2024               # first future year actually used
OVL0, OVL1 = 2015, 2023     # overlap years present in both records

VARS = [("tbot", "TBOT", "domain-mean annual temperature [$^\\circ$C]"),
        ("prect", "PRECT", "domain-mean annual precipitation [mm yr$^{-1}$]")]


def load():
    h = dict(np.load(OUT / "hist_annual_means.npz", allow_pickle=True))
    f = {s: dict(np.load(OUT / f"future_annual_means_{s}.npz", allow_pickle=True))
         for s in SCEN}
    return h, f


def series(d, which):
    if which == "tbot":
        return d["tbot_K"] - 273.15
    return d["prect_mm_yr"]


def main():
    h, F = load()
    hy = h["years"].astype(int)
    figdir = OUT / "figures"; figdir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(17, 9.5),
                             gridspec_kw=dict(width_ratios=[1.9, 1.0]))
    stats = {}

    for r, (key, name, ylab) in enumerate(VARS):
        hv = series(h, key)
        hsig = float(np.std(hv, ddof=1))
        hmask_ovl = (hy >= OVL0) & (hy <= OVL1)

        for ax, xlim in ((axes[r, 0], (2000, 2100)), (axes[r, 1], (2013, 2036))):
            ax.plot(hy, hv, color="k", lw=2.0, marker="o", ms=3,
                    label="historical (Daymet+ERA5)", zorder=5)
            for s in SCEN:
                fy = F[s]["years"].astype(int)
                fv = series(F[s], key)
                fut = fy >= SPLICE
                ax.plot(fy[fut], fv[fut], color=SCOL[s], lw=1.6, label=SLAB[s])
                ovl = (fy >= OVL0) & (fy <= OVL1)
                ax.plot(fy[ovl], fv[ovl], color=SCOL[s], lw=1.2, ls=":", alpha=0.9)
            ax.axvspan(OVL0, OVL1, color="0.85", alpha=0.5, zorder=0)
            ax.axvline(SPLICE - 0.5, color="k", ls="--", lw=1.1)
            ax.set_xlim(*xlim)
            ax.grid(alpha=0.25, lw=0.5)
            ax.set_xlabel("year")
        axes[r, 0].set_ylabel(ylab, fontsize=10)
        axes[r, 0].legend(fontsize=8, ncol=2, loc="best")
        axes[r, 0].set_title(f"{name} — full record (dotted = future model's own "
                             f"2015-2023, shaded = overlap)", fontsize=11)
        axes[r, 1].set_title(f"{name} — zoom on the {SPLICE-1}/{SPLICE} handoff",
                             fontsize=11)

        # numbers
        st = {}
        h2023 = float(hv[hy == SPLICE - 1][0])
        st["hist_2023"] = h2023
        st["hist_sigma"] = hsig
        st["hist_ovl_mean"] = float(np.mean(hv[hmask_ovl]))
        for s in SCEN:
            fy = F[s]["years"].astype(int)
            fv = series(F[s], key)
            f2024 = float(fv[fy == SPLICE][0])
            fovl = float(np.mean(fv[(fy >= OVL0) & (fy <= OVL1)]))
            st[s] = dict(f2024=f2024, step=f2024 - h2023,
                         step_sigma=(f2024 - h2023) / hsig,
                         ovl_mean=fovl, ovl_bias=fovl - st["hist_ovl_mean"],
                         ovl_bias_sigma=(fovl - st["hist_ovl_mean"]) / hsig)
        stats[key] = st

    fig.suptitle("TESSFA2 forcing continuity across the historical → future handoff "
                 "(domain mean, 3-hourly TBOT and PRECTmms in both records)",
                 fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    p = figdir / "fig_climate_splice_2023_2024.png"
    fig.savefig(p, dpi=130, bbox_inches="tight")
    print(f"wrote {p}\n")

    # ---- tables -----------------------------------------------------------
    for key, name, _ in VARS:
        st = stats[key]
        u = "degC" if key == "tbot" else "mm/yr"
        print("=" * 92)
        print(f"{name}   [{u}]")
        print(f"  historical 2023 = {st['hist_2023']:.3f}   "
              f"interannual sigma 2000-2023 = {st['hist_sigma']:.3f}")
        print(f"  historical {OVL0}-{OVL1} mean = {st['hist_ovl_mean']:.3f}")
        print("-" * 92)
        print(f"{'scenario':<11}{'2024':>10}{'step vs 2023':>15}{'in sigma':>11}"
              f"{'overlap bias':>15}{'in sigma':>11}")
        for s in SCEN:
            d = st[s]
            print(f"{SLAB[s]:<11}{d['f2024']:>10.3f}{d['step']:>+15.3f}"
                  f"{d['step_sigma']:>+11.2f}{d['ovl_bias']:>+15.3f}"
                  f"{d['ovl_bias_sigma']:>+11.2f}")
        print()
    print("Reading these: the step mixes the real offset with one year of weather;")
    print("the overlap bias (9 paired years) is the offset. Anything within about")
    print("1 sigma is indistinguishable from ordinary interannual variability.")


if __name__ == "__main__":
    main()
