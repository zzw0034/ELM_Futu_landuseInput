#!/usr/bin/env python
"""Is the dry bias a property of the whole CanESM5-DBCCA chain, or of the SSP files?

The SSP files run ~10-20% dry against Daymet_ERA5 over their 2015-2023 overlap.
Nine years is a short window to estimate a bias from, and it cannot say where
the bias comes from. CanESM5's own DBCCA historical member covers 1980-2014,
which overlaps Daymet_ERA5 for 35 years and is produced by the same downscaling
chain but is not an SSP file.

  bias present in 1980-2014 too  -> systematic to the CanESM5-DBCCA product;
                                    estimate correction factors from 35 years
  bias absent in 1980-2014       -> something specific to the SSP files, which
                                    is a question for whoever produced them,
                                    not something to patch downstream

Both series are domain-mean monthly over the same 117964 TESSFA2 land cells
(scripts 04 and 05, same masking).

Also emits the multiplicative monthly factors that would map the model
climatology onto the observed one, since that is the thing a correction would
actually use.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/"
           "future_climate/outputs")
OBS = "hist_monthly_means_1980-2014.npz"        # Daymet_ERA5
MOD = "future_monthly_means_historical.npz"     # CanESM5 DBCCA historical
SSP = ["ssp119", "ssp245", "ssp370", "ssp585"]
SLAB = {"ssp119": "SSP1-1.9", "ssp245": "SSP2-4.5",
        "ssp370": "SSP3-7.0", "ssp585": "SSP5-8.5"}
SCOL = {"ssp119": "#1a9850", "ssp245": "#2c7fb8",
        "ssp370": "#7b3294", "ssp585": "#d73027"}
MON = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]


def main():
    o = dict(np.load(OUT / OBS, allow_pickle=True))
    m = dict(np.load(OUT / MOD, allow_pickle=True))
    oy, my = o["years"].astype(int), m["years"].astype(int)
    lo, hi = max(oy.min(), my.min()), min(oy.max(), my.max())
    om = (oy >= lo) & (oy <= hi); mm = (my >= lo) & (my <= hi)
    print(f"common window {lo}-{hi}  ({om.sum()} yr obs, {mm.sum()} yr model)")

    oT = (o["tbot_K"] - 273.15)[om]; oP = o["prect_mm_mon"][om]
    mT = (m["tbot_K"] - 273.15)[mm]; mP = m["prect_mm_mon"][mm]

    oTc, mTc = oT.mean(axis=0), mT.mean(axis=0)
    oPc, mPc = oP.mean(axis=0), mP.mean(axis=0)
    dT, dP = mTc - oTc, mPc - oPc
    fac = np.where(mPc > 0, oPc / mPc, np.nan)      # multiply model by this

    oTa, mTa = oT.mean(axis=1).mean(), mT.mean(axis=1).mean()
    oPa, mPa = oP.sum(axis=1).mean(), mP.sum(axis=1).mean()

    # the 9-year SSP estimate, for comparison
    ssp_bias = {}
    for s in SSP:
        f = OUT / f"future_monthly_means_{s}.npz"
        if not f.exists():
            continue
        d = dict(np.load(f, allow_pickle=True))
        fy = d["years"].astype(int)
        sel = (fy >= 2015) & (fy <= 2023)
        ssp_bias[s] = dict(P=d["prect_mm_mon"][sel].sum(axis=1).mean(),
                           Pc=d["prect_mm_mon"][sel].mean(axis=0),
                           T=(d["tbot_K"] - 273.15)[sel].mean())

    # ---------------- report ----------------
    print("\n" + "=" * 88)
    print(f"CanESM5 DBCCA historical  vs  Daymet_ERA5   ({lo}-{hi}, {om.sum()} years)")
    print("=" * 88)
    print(f"  annual temperature   obs {oTa:8.3f}   model {mTa:8.3f}   "
          f"bias {mTa-oTa:+.3f} degC")
    print(f"  annual precipitation obs {oPa:8.1f}   model {mPa:8.1f}   "
          f"bias {mPa-oPa:+.1f} mm/yr  ({100*(mPa-oPa)/oPa:+.1f}%)")
    print("-" * 88)
    print(f"{'month':<7}{'obs T':>9}{'mod T':>9}{'dT':>8}"
          f"{'obs P':>10}{'mod P':>10}{'dP':>9}{'dP %':>8}{'factor':>9}")
    for i in range(12):
        print(f"{MON[i]:<7}{oTc[i]:>9.2f}{mTc[i]:>9.2f}{dT[i]:>+8.2f}"
              f"{oPc[i]:>10.1f}{mPc[i]:>10.1f}{dP[i]:>+9.1f}"
              f"{100*dP[i]/oPc[i]:>+8.1f}{fac[i]:>9.3f}")

    if ssp_bias:
        print("\n" + "=" * 88)
        print("Consistency: 35-yr historical estimate vs the 9-yr SSP overlap estimate")
        print("=" * 88)
        print(f"  {'source':<24}{'annual P [mm/yr]':>18}{'bias vs obs':>14}{'%':>9}")
        print(f"  {'Daymet_ERA5 (obs)':<24}{oPa:>18.1f}{'':>14}{'':>9}")
        print(f"  {'CanESM5 hist 1980-2014':<24}{mPa:>18.1f}"
              f"{mPa-oPa:>+14.1f}{100*(mPa-oPa)/oPa:>+9.1f}")
        for s, d in ssp_bias.items():
            print(f"  {SLAB[s]+' 2015-2023':<24}{d['P']:>18.1f}"
                  f"{d['P']-oPa:>+14.1f}{100*(d['P']-oPa)/oPa:>+9.1f}")
        print("\n  (the SSP rows use a different, wetter 9-year observed window, so")
        print("   compare the SIGN and rough magnitude, not the exact numbers)")

    np.savez(OUT / "canesm5_hist_bias.npz", months=np.arange(1, 13),
             obs_T=oTc, mod_T=mTc, obs_P=oPc, mod_P=mPc,
             dT=dT, dP=dP, prec_factor=fac, window=np.array([lo, hi]))
    print(f"\nwrote {OUT/'canesm5_hist_bias.npz'}")

    # ---------------- figure ----------------
    fig, ax = plt.subplots(2, 2, figsize=(16, 9))

    a = ax[0, 0]
    a.plot(range(1, 13), oTc, "k-o", lw=2.2, label=f"Daymet_ERA5 {lo}-{hi}")
    a.plot(range(1, 13), mTc, "-s", color="#d95f02", lw=1.8,
           label=f"CanESM5 DBCCA hist {lo}-{hi}")
    for s, d in ssp_bias.items():
        a.plot(range(1, 13), (d["T"],) * 12, alpha=0)   # keep colors in sync
    a.set_xticks(range(1, 13)); a.set_xticklabels(MON)
    a.set_ylabel("temperature [$^\\circ$C]"); a.legend(fontsize=8)
    a.grid(alpha=0.25, lw=0.5); a.set_title("seasonal cycle — temperature", fontsize=11)

    a = ax[0, 1]
    a.plot(range(1, 13), oPc, "k-o", lw=2.2, label=f"Daymet_ERA5 {lo}-{hi}")
    a.plot(range(1, 13), mPc, "-s", color="#d95f02", lw=1.8,
           label=f"CanESM5 DBCCA hist {lo}-{hi}")
    for s, d in ssp_bias.items():
        a.plot(range(1, 13), d["Pc"], color=SCOL[s], lw=1.1, ls=":",
               label=f"{SLAB[s]} 2015-2023")
    a.set_xticks(range(1, 13)); a.set_xticklabels(MON)
    a.set_ylabel("precipitation [mm month$^{-1}$]"); a.legend(fontsize=7.5)
    a.grid(alpha=0.25, lw=0.5); a.set_title("seasonal cycle — precipitation", fontsize=11)

    a = ax[1, 0]
    a.bar(range(1, 13), dT, color="#d95f02")
    a.axhline(0, color="k", lw=0.8)
    a.set_xticks(range(1, 13)); a.set_xticklabels(MON)
    a.set_ylabel("model $-$ obs [$^\\circ$C]"); a.grid(axis="y", alpha=0.25, lw=0.5)
    a.set_title(f"temperature bias, annual {mTa-oTa:+.3f} $^\\circ$C", fontsize=11)

    a = ax[1, 1]
    a.bar(range(1, 13), dP, color="#d95f02")
    a.axhline(0, color="k", lw=0.8)
    a.set_xticks(range(1, 13)); a.set_xticklabels(MON)
    a.set_ylabel("model $-$ obs [mm month$^{-1}$]")
    a.grid(axis="y", alpha=0.25, lw=0.5)
    a.set_title(f"precipitation bias, annual {mPa-oPa:+.1f} mm/yr "
                f"({100*(mPa-oPa)/oPa:+.1f}%)", fontsize=11)

    fig.suptitle(f"Is the dry bias in the SSP files or in the whole CanESM5-DBCCA "
                 f"chain?  —  {lo}-{hi} historical overlap, TESSFA2 land cells",
                 fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p = OUT / "figures" / "fig_canesm5_hist_bias.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=130, bbox_inches="tight")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
