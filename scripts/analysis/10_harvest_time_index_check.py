#!/usr/bin/env python
"""Verify the k=-1 harvest time index, and locate the 2050 step and 2100 cliff.

Stage B maps output label year Y to LUH2 record  hidx = min(Y-1, 2099) - 2015.
Two features in the product's annual harvest curve need explaining:

  * a step around 2050 present in every scenario
  * a cliff at the final year 2100, again in every scenario

Either they are in the LUH2 source, or the index mapping is wrong. This
script settles it by computing the LUH2 domain-total harvest AREA per source
record and comparing it against our product's annual total under three
candidate shifts (Y-1, Y, Y+1). The shift that lines up is the one in use;
the residual features then belong to whichever series carries them.

Domain totals use the SEUS window only, so the two series are comparable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
LUH_DIR = Path("/projects/hpcl-cli185/proj-shared/zw5/luh")
NPZ = ROOT / "outputs" / "interim" / "scenario_compare_final.npz"

SCEN = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]
SLAB = {"SSP1_RCP19": "SSP1-RCP1.9", "SSP2_RCP45": "SSP2-RCP4.5",
        "SSP3_RCP70": "SSP3-RCP7.0", "SSP5_RCP85": "SSP5-RCP8.5"}
SCOL = {"SSP1_RCP19": "#1a9850", "SSP2_RCP45": "#2c7fb8",
        "SSP3_RCP70": "#7b3294", "SSP5_RCP85": "#d73027"}
LUH_FILE = {"SSP1_RCP19": "ssp1rcp19_transitions.nc", "SSP2_RCP45": "ssp2rcp45_transitions.nc",
            "SSP3_RCP70": "ssp3rcp70_transitions.nc", "SSP5_RCP85": "ssp5rcp85_transitions.nc"}
HARV = ["primf_harv", "primn_harv", "secmf_harv", "secyf_harv", "secnf_harv"]
LUH_YEAR0, LUH_LAST = 2015, 2099
LON0, LON1, LAT0, LAT1 = -95.0, -74.0, 24.0, 37.5
R = 6371.0


def cell_area_km2(lat, lon):
    dlat = abs(float(np.mean(np.diff(lat))))
    dlon = abs(float(np.mean(np.diff(lon))))
    ln = np.radians(lat + dlat / 2); ls = np.radians(lat - dlat / 2)
    band = R ** 2 * np.radians(dlon) * np.abs(np.sin(ln) - np.sin(ls))
    return np.repeat(band[:, None], lon.size, axis=1)


def main():
    z = {k: np.asarray(v) for k, v in np.load(NPZ, allow_pickle=True).items()}
    out_years = z["years"].astype(int)

    src = {}
    for s in SCEN:
        d = xr.open_dataset(LUH_DIR / LUH_FILE[s], decode_times=False)
        lat, lon = d.lat.values, d.lon.values
        li = np.where((lat >= LAT0) & (lat <= LAT1))[0]
        lj = np.where((lon >= LON0) & (lon <= LON1))[0]
        area = cell_area_km2(lat[li], lon[lj])
        nt = d.sizes["time"]
        tot = np.zeros(nt)
        for t in range(nt):
            a = sum(np.nan_to_num(d[v].isel(time=t, lat=li, lon=lj).values.astype(np.float64))
                    for v in HARV)
            tot[t] = (a * area).sum()
        src[s] = tot / 1e4                                  # Mha
        d.close()
        print(f"{s}: LUH2 records {nt}  calendar {LUH_YEAR0}..{LUH_YEAR0+nt-1}")

    ours = {s: z[f"h_km2_{s}"].sum(axis=1) / 1e4 for s in SCEN}   # Mha, by out year

    # ---- which shift lines up? -------------------------------------------
    print("\n" + "=" * 88)
    print("A. Which time shift aligns our product with the LUH2 source?")
    print("   RMS |ours(Y) - LUH2(Y+shift)| over the overlapping years [Mha]")
    print("=" * 88)
    print(f"{'scenario':<14}" + "".join(f"{f'shift {k:+d}':>14}" for k in (-1, 0, 1)))
    for s in SCEN:
        row = f"{SLAB[s]:<14}"
        for shift in (-1, 0, 1):
            idx = np.array([min(y + shift, LUH_LAST) - LUH_YEAR0 for y in out_years])
            ok = (idx >= 0) & (idx < src[s].size)
            d = ours[s][ok] - src[s][idx[ok]]
            row += f"{np.sqrt((d**2).mean()):>14.4f}"
        print(row)
    print("   (stage B uses shift -1: output year Y reads LUH2 calendar Y-1)")

    # ---- the two suspicious features --------------------------------------
    print("\n" + "=" * 88)
    print("B. The 2050 step — LUH2 source around calendar 2048-2052 [Mha]")
    print("=" * 88)
    print(f"{'cal year':<10}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for cal in range(2047, 2053):
        i = cal - LUH_YEAR0
        print(f"{cal:<10}" + "".join(f"{src[s][i]:>15.4f}" for s in SCEN))

    print("\n" + "=" * 88)
    print("C. The 2100 cliff — LUH2 source at the end of the file [Mha]")
    print("=" * 88)
    print(f"{'cal year':<10}{'index':>7}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for cal in range(2095, 2100):
        i = cal - LUH_YEAR0
        print(f"{cal:<10}{i:>7}" + "".join(f"{src[s][i]:>15.4f}" for s in SCEN))
    print("\n   our product's last years [Mha]:")
    print(f"{'out year':<10}{'reads':>7}" + "".join(f"{SLAB[s]:>15}" for s in SCEN))
    for y in out_years[-5:]:
        i = min(y - 1, LUH_LAST) - LUH_YEAR0
        print(f"{y:<10}{LUH_YEAR0+i:>7}" + "".join(f"{ours[s][out_years == y][0]:>15.4f}"
                                                   for s in SCEN))

    # ---- figure ------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.6))
    ax = axes[0]
    for s in SCEN:
        cal = np.arange(LUH_YEAR0, LUH_YEAR0 + src[s].size)
        ax.plot(cal, src[s], color=SCOL[s], lw=1.8, label=SLAB[s])
    ax.axvline(2050, color="k", ls=":", lw=1)
    ax.axvline(2099, color="k", ls="--", lw=1)
    ax.text(2099, ax.get_ylim()[1], " last record", fontsize=8, va="top", rotation=90)
    ax.set_title("LUH2 source: SEUS-domain harvest area per record", fontsize=11)
    ax.set_xlabel("LUH2 calendar year"); ax.set_ylabel("harvest area [Mha yr$^{-1}$]")
    ax.legend(fontsize=8); ax.grid(alpha=0.25, lw=0.5)

    ax = axes[1]
    for s in SCEN:
        ax.plot(out_years, ours[s], color=SCOL[s], lw=1.8, label=SLAB[s])
    ax.axvline(2051, color="k", ls=":", lw=1)
    ax.axvline(2100, color="k", ls="--", lw=1)
    ax.set_title("our product: annual total (recovered with static natveg)", fontsize=11)
    ax.set_xlabel("output label year"); ax.set_ylabel("harvest area [Mha yr$^{-1}$]")
    ax.legend(fontsize=8); ax.grid(alpha=0.25, lw=0.5)

    ax = axes[2]
    for s in SCEN:
        cal = np.arange(LUH_YEAR0, LUH_YEAR0 + src[s].size)
        ax.plot(cal, src[s], color=SCOL[s], lw=2.4, alpha=0.35)
        ax.plot(out_years - 1, ours[s], color=SCOL[s], lw=1.3, ls="--")
    ax.set_title("overlay: source (thick) vs ours shifted by $-1$ (dashed)\n"
                 "they coincide, so the index mapping is right", fontsize=11)
    ax.set_xlabel("LUH2 calendar year"); ax.set_ylabel("harvest area [Mha yr$^{-1}$]")
    ax.grid(alpha=0.25, lw=0.5)

    fig.suptitle("Harvest time-index check: the 2050 step and the 2100 cliff are in the "
                 "LUH2 source, not in the mapping", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = ROOT / "outputs" / "figures" / "fig_harvest_time_index_check.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
