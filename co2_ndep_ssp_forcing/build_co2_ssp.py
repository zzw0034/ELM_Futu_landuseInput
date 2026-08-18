#!/usr/bin/env python
"""Build CPL_BYPASS-compatible CO2 scalar forcing files for ssp119/245/370/585.

Splices NCAR CMIP6 historical global-mean CO2 (1750-2013, common to all
scenarios) with each SSP's ScenarioMIP future branch (2014-2501), then trims
to years 1765-2500 (736 annual records) to exactly match the schema of the
E3SM CPL_BYPASS reader's currently-used file
(fco2_datm_rcp4.5_1765-2500_c130312.nc): same dims/vars, same
'days since 1765-01-01' noleap time axis. Only the CO2 variable's values
differ per scenario; time/date/grid vars are copied verbatim from the
template so the reader's hardcoded yr-1764 index formula lines up exactly
as it does for the file already in production use.
"""
import os
import shutil
import numpy as np
import netCDF4 as nc

SRC_DIR = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/co2_ndep_ssp_forcing/src_ncar_co2"
TEMPLATE = "/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/CO2/fco2_datm_rcp4.5_1765-2500_c130312.nc"
OUT_DIR = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/co2_ndep_ssp_forcing/output"
os.makedirs(OUT_DIR, exist_ok=True)

HIST = os.path.join(SRC_DIR, "fco2_datm_global_simyr_1750-2014_CMIP6_c180929.nc")
FUTURE = {
    "ssp119": os.path.join(SRC_DIR, "fco2_datm_globalSSP1-1.9_simyr_2014-2501_CMIP6_c190514.nc"),
    "ssp245": os.path.join(SRC_DIR, "fco2_datm_globalSSP2-4.5__simyr_2014-2501_CMIP6_c190506.nc"),
    "ssp370": os.path.join(SRC_DIR, "fco2_datm_globalSSP3-7.0_simyr_1750-2501_CMIP6_c201101.nc"),
    "ssp585": os.path.join(SRC_DIR, "fco2_datm_globalSSP5-8.5__simyr_2014-2501_CMIP6_c190506.nc"),
}

# Historical: 265 annual records, years 1750-2014. Keep 1750-2013 (drop the
# last record, year 2014, since every future branch's own first record is
# also year 2014 with an identical value -- confirmed below).
with nc.Dataset(HIST) as ds:
    hist_co2_full = np.array(ds["CO2"][:]).reshape(-1)
assert hist_co2_full.shape[0] == 265, hist_co2_full.shape
hist_co2 = hist_co2_full[:264]  # years 1750-2013; drop 2014 (duplicated in every future branch)

TARGET_YEARS = np.arange(1765, 2501)  # 736 years, matches template exactly

for scen, path in FUTURE.items():
    if scen == "ssp370":
        # This one is already the full 1750-2501 concatenation (752 records)
        # built the same way by NCAR/CESM -- use it directly, no splice needed.
        with nc.Dataset(path) as ds:
            full = np.array(ds["CO2"][:]).reshape(-1)
        assert full.shape[0] == 752, full.shape
        years_full = np.arange(1750, 2502)
    else:
        with nc.Dataset(path) as ds:
            fut_co2 = np.array(ds["CO2"][:]).reshape(-1)
        assert fut_co2.shape[0] == 488, fut_co2.shape
        # sanity: future branch's own first record (year 2014) must match
        # historical's last (dropped) record within a tiny tolerance
        # (both trace the same underlying CMIP6 historical concentration).
        with nc.Dataset(HIST) as ds:
            hist_full = np.array(ds["CO2"][:]).reshape(-1)
        boundary_diff = abs(float(fut_co2[0]) - float(hist_full[-1]))
        assert boundary_diff < 0.01, f"{scen} boundary mismatch: {boundary_diff}"
        full = np.concatenate([hist_co2, fut_co2])  # 264 + 488 = 752, years 1750-2501
        years_full = np.arange(1750, 2502)

    assert full.shape[0] == 752
    # trim to 1765-2500 (736 records), matching template exactly
    i0 = int(np.where(years_full == 1765)[0][0])
    i1 = int(np.where(years_full == 2500)[0][0])
    co2_out = full[i0:i1 + 1]
    assert co2_out.shape[0] == 736, (scen, co2_out.shape)

    out_path = os.path.join(OUT_DIR, f"fco2_datm_{scen}_1765-2500_c260818.nc")
    shutil.copyfile(TEMPLATE, out_path)
    with nc.Dataset(out_path, "a") as ds:
        ds["CO2"][:] = co2_out.reshape(-1, 1, 1).astype(ds["CO2"].dtype)
        ds.history = (getattr(ds, "history", "") +
                      f"\nBuilt 2026-08-18: years 1765-2013 from NCAR CMIP6 "
                      f"historical (fco2_datm_global_simyr_1750-2014_CMIP6_"
                      f"c180929.nc), years 2014-2500 from NCAR ScenarioMIP "
                      f"{scen} (fco2_datm_global{{'SSP1-1.9','SSP2-4.5',"
                      f"'SSP3-7.0','SSP5-8.5'}}[{scen}]). Grid/time axis "
                      f"copied from fco2_datm_rcp4.5_1765-2500_c130312.nc "
                      f"template (same dims/vars, only CO2 replaced) so the "
                      f"CPL_BYPASS yr-1764 index formula lines up.")
    print(scen, "->", out_path,
          "yr1765:", round(float(co2_out[0]), 2),
          "yr2000:", round(float(co2_out[235]), 2),
          "yr2015:", round(float(co2_out[250]), 2),
          "yr2050:", round(float(co2_out[285]), 2),
          "yr2100:", round(float(co2_out[335]), 2),
          "yr2500:", round(float(co2_out[-1]), 2))
