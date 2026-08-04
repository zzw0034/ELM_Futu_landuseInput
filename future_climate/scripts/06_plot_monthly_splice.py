#!/usr/bin/env python
"""Monthly view of the historical -> future forcing handoff.

Historical  Daymet_ERA5_TESSFA2 cpl_bypass,  2010-2023   (script 04)
Future      CanESM5 <ssp> DBCCA TESSFA2,     2015-2029   (script 05)

Three views, because each answers a different question:

  row 1  monthly series through the handoff -- does the seasonal cycle run on
         continuously, or is there a visible break at 2023/2024?
  row 2  climatological seasonal cycle, historical 2015-2023 vs future's own
         2015-2023 -- the overlap years are the only paired comparison, and a
         month-by-month offset here is the actual bias
  row 3  annual means around the splice, so the step can be read against the
         historical interannual spread

The future record is a bias-corrected GCM realization, so its 2015-2023 is the
model's own weather, not the observed weather of those years. Individual years
are not expected to match; a persistent offset in the CLIMATOLOGY is what
would matter.
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
SPLICE = 2024
OVL0, OVL1 = 2015, 2023
MON = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def flat(years, arr):
    """(nyr,12) -> (x as decimal year, values) for a continuous monthly line."""
    x = (years[:, None] + (np.arange(12)[None, :] + 0.5) / 12.0).ravel()
    return x, arr.ravel()


def main():
    h = dict(np.load(OUT / "hist_monthly_means.npz", allow_pickle=True))
    F = {s: dict(np.load(OUT / f"future_monthly_means_{s}.npz", allow_pickle=True))
         for s in SCEN}
    hy = h["years"].astype(int)
    figdir = OUT / "figures"; figdir.mkdir(parents=True, exist_ok=True)

    VARS = [("tbot", "temperature", "$^\\circ$C",
             lambda d: d["tbot_K"] - 273.15),
            ("prect", "precipitation", "mm month$^{-1}$",
             lambda d: d["prect_mm_mon"])]

    fig, axes = plt.subplots(3, 2, figsize=(18, 14),
                             gridspec_kw=dict(height_ratios=[1.15, 1.0, 1.0]))
    report = {}

    for c, (key, name, unit, get) in enumerate(VARS):
        hv = get(h)                                    # (nyr,12)
        hovl = (hy >= OVL0) & (hy <= OVL1)

        # ---- row 1: monthly series through the handoff ----
        ax = axes[0, c]
        x, y = flat(hy, hv)
        ax.plot(x, y, color="k", lw=1.5, label="historical (Daymet+ERA5)", zorder=5)
        for s in SCEN:
            fy = F[s]["years"].astype(int)
            fv = get(F[s])
            xf, yf = flat(fy, fv)
            use = xf >= SPLICE
            ax.plot(xf[use], yf[use], color=SCOL[s], lw=1.2, label=SLAB[s])
            ax.plot(xf[~use], yf[~use], color=SCOL[s], lw=1.0, ls=":", alpha=0.75)
        ax.axvspan(OVL0, OVL1 + 1, color="0.85", alpha=0.55, zorder=0)
        ax.axvline(SPLICE, color="k", ls="--", lw=1.3)
        ax.set_xlim(2010, 2030)
        ax.set_ylabel(f"monthly {name} [{unit}]", fontsize=10)
        ax.set_xlabel("year")
        ax.grid(alpha=0.25, lw=0.5)
        ax.legend(fontsize=7.5, ncol=2, loc="upper left")
        ax.set_title(f"{name}: monthly series across the handoff\n"
                     f"(shaded = {OVL0}-{OVL1} overlap, dotted = future model's own "
                     f"overlap years)", fontsize=11)

        # ---- row 2: seasonal cycle over the overlap ----
        ax = axes[1, c]
        hclim = hv[hovl].mean(axis=0)
        ax.plot(range(1, 13), hclim, color="k", lw=2.4, marker="o", ms=5,
                label=f"historical {OVL0}-{OVL1}", zorder=5)
        bias = {}
        for s in SCEN:
            fy = F[s]["years"].astype(int)
            fv = get(F[s])
            fclim = fv[(fy >= OVL0) & (fy <= OVL1)].mean(axis=0)
            ax.plot(range(1, 13), fclim, color=SCOL[s], lw=1.6, marker="s", ms=3.5,
                    label=f"{SLAB[s]} {OVL0}-{OVL1}")
            bias[s] = fclim - hclim
        ax.set_xticks(range(1, 13)); ax.set_xticklabels(MON)
        ax.set_ylabel(f"{name} [{unit}]", fontsize=10)
        ax.grid(alpha=0.25, lw=0.5); ax.legend(fontsize=7.5)
        ax.set_title(f"{name}: seasonal cycle over the {OVL0}-{OVL1} overlap "
                     f"(the paired comparison)", fontsize=11)

        # ---- row 3: annual means around the splice ----
        ax = axes[2, c]
        hann = hv.mean(axis=1) if key == "tbot" else hv.sum(axis=1)
        hsig = float(np.std(hann, ddof=1))
        ax.plot(hy, hann, color="k", lw=2.0, marker="o", ms=4, label="historical",
                zorder=5)
        step = {}
        for s in SCEN:
            fy = F[s]["years"].astype(int)
            fv = get(F[s])
            fann = fv.mean(axis=1) if key == "tbot" else fv.sum(axis=1)
            ax.plot(fy[fy >= SPLICE], fann[fy >= SPLICE], color=SCOL[s], lw=1.6,
                    marker="s", ms=3.5, label=SLAB[s])
            ax.plot(fy[fy < SPLICE], fann[fy < SPLICE], color=SCOL[s], lw=1.2,
                    ls=":", alpha=0.8)
            step[s] = float(fann[fy == SPLICE][0] - hann[hy == SPLICE - 1][0])
        ax.axvline(SPLICE - 0.5, color="k", ls="--", lw=1.2)
        ax.axhspan(hann.mean() - hsig, hann.mean() + hsig, color="0.85", alpha=0.6,
                   zorder=0, label="historical $\\pm1\\sigma$")
        ax.set_ylabel(f"annual {name} [{'°C' if key=='tbot' else 'mm yr$^{-1}$'}]",
                      fontsize=10)
        ax.set_xlabel("year"); ax.grid(alpha=0.25, lw=0.5)
        ax.legend(fontsize=7.5, ncol=2)
        ax.set_title(f"{name}: annual means, step read against historical "
                     f"$\\sigma$ = {hsig:.3g}", fontsize=11)

        report[key] = dict(name=name, unit=unit, hclim=hclim, bias=bias,
                           step=step, hsig=hsig,
                           h2023=float(hann[hy == SPLICE - 1][0]))

    fig.suptitle("TESSFA2 forcing: historical (Daymet+ERA5) → future (CanESM5 DBCCA) "
                 "handoff at 2023/2024 — domain mean, 3-hourly TBOT and PRECTmms",
                 fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    p = figdir / "fig_climate_splice_monthly.png"
    fig.savefig(p, dpi=130, bbox_inches="tight")
    print(f"wrote {p}\n")

    for key in ("tbot", "prect"):
        R = report[key]
        print("=" * 94)
        print(f"{R['name'].upper()}  [{R['unit']}]   historical 2023 annual = "
              f"{R['h2023']:.3f},  interannual sigma = {R['hsig']:.3f}")
        print("-" * 94)
        print(f"{'scenario':<11}{'2023->2024 step':>17}{'in sigma':>11}"
              f"{'overlap bias (annual)':>24}{'in sigma':>11}")
        for s in SCEN:
            b = R["bias"][s]
            ann_bias = b.mean() if key == "tbot" else b.sum()
            print(f"{SLAB[s]:<11}{R['step'][s]:>+17.3f}"
                  f"{R['step'][s]/R['hsig']:>+11.2f}"
                  f"{ann_bias:>+24.3f}{ann_bias/R['hsig']:>+11.2f}")
        print(f"\n  monthly bias, future {OVL0}-{OVL1} minus historical {OVL0}-{OVL1}:")
        print(f"  {'scen':<10}" + "".join(f"{m:>7}" for m in MON))
        for s in SCEN:
            print(f"  {SLAB[s]:<10}" + "".join(f"{v:>+7.2f}" for v in R["bias"][s]))
        print()


if __name__ == "__main__":
    main()
