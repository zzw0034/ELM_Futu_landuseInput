#!/usr/bin/env python
"""Build the 12 management-scenario landuse.timeseries files: Reforestation
(RF), Deforestation counterfactual (DF), Reduced-Harvest (RH), x 4 SSPs
(SSP1_RCP19, SSP2_RCP45, SSP3_RCP70, SSP5_RCP85).

Definitions locked 2026-08-19 -- see project memory
seus_management_scenarios_rf_df_rh.md for the full derivation/rationale.
This SUPERSEDES the 2026-08-18 PRESERVE / HALFHARVEST_SSP370 / REFOREST1850
version. That version did run successfully on 2026-08-19 and produced 3
valid files, but none of them corresponds to any scenario here (PRESERVE is
conceptually the opposite of DF; HALFHARVEST used the wrong ratio and only
one SSP; REFOREST1850 lacked the grass-only cap and used a different ramp
and sub-PFT allocation), nothing referenced them, and they were deleted
2026-08-19 to avoid confusion with this version's 12 outputs in the same
directory. The old script remains recoverable at git commit dd82b07.

  RF: reforest currently-existing GRASS ONLY (never cropland) in cells where
      1850 forest exceeded 2023 forest, ramped linearly 2024->2050, held as
      Default + fixed increment for 2051-2100. Restricted to grass because
      the proposal frames RF as something "potentially used for carbon
      offset projects" -- it needs to be a credible, implementable
      intervention (real programs target marginal/abandoned land, not
      productive cropland). Forest gained is split across the 8 tree
      sub-PFTs by each cell's own 1850 forest composition; grass given up is
      split across the 3 grass sub-PFTs by each cell's own 2023 grass
      composition.
  DF: NOT frozen/protected forest -- the opposite: instantaneously clear
      ALL forest every year from 2024, route it to grass (by the same local
      2023 grass-composition weights), lock at zero through 2100 (never
      regrows), and zero out HARVEST_*. This is a deliberate, unrestricted
      theoretical upper bound used only via Default-DF ("avoiding
      deforestation" accounting) -- it is not itself an implementable
      scenario, so it does not get RF's credibility constraint.
  RH: all 5 HARVEST_* variables HALVED (x0.5) for all years 2024-2100.
      This is a deliberate departure from the proposal's literal wording
      ("extend the interval of wood harvest by 50%", which would be a
      divide-by-1.5 / 33% rate reduction): the project chose to define RH
      directly as a halved harvest rate instead. Note the rotation-interval
      equivalent of halving the rate is *doubling* the interval (a 100%
      extension), not the proposal's 50% -- describe it as a halved rate,
      or as a doubled rotation interval, but never as the proposal's "50%
      longer interval".

Output format follows the fix already proven for this pipeline: build each
output as a brand-new NETCDF3_64BIT_OFFSET (classic, unchunked,
uncompressed) file, writing every variable once in a single full-array
assignment. Never open a compressed/chunked NetCDF4 template with 'r+' and
edit in place -- that corrupts the file (same failure class as
future_climate/README_cpl_bypass_future.md sec 6.1; see
harvest_scenarios/HARVEST_SCENARIOS.md sec 3 for this project's own case).
"""
import os
import numpy as np
import netCDF4 as nc4

HIST = ("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
        "surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc")
DEFAULT_DIR = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed"
OUT_DIR = os.path.join(DEFAULT_DIR, "harvest_scenarios")
os.makedirs(OUT_DIR, exist_ok=True)

# SSP4_RCP60 deliberately excluded -- no matching climate forcing exists in
# TESSFA, SSP3-7.0 already substitutes for it project-wide (see
# seus_task_backlog memory).
SSPS = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]

HARVEST_VARS = ["HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"]

TREE_PFT = list(range(1, 9))     # natpft 1..8
GRASS_PFT = [12, 13, 14]         # c3_arctic_grass, c3_non-arctic_grass, c4_grass

RAMP_START_YEAR = 2024
RAMP_END_YEAR = 2050             # 27-yr ramp, aligned to 2050 net-zero horizon

# RH: harvest rate multiplier. 0.5 = halved rate (equivalently, a doubled
# rotation interval). Deliberately NOT 1/1.5, which is what the proposal's
# literal "extend the interval by 50%" would imply.
RH_SCALE = 0.5

# SEUS area-weighted fallback C3/C4 split (grass-holding 2023 cells), used
# only for the ~5 forested cells (0.01% of 76,558) that have zero 2023
# grass -- see memory doc for the empirical count.
FALLBACK_GRASS_SPLIT = {12: 0.0, 13: 0.85, 14: 0.15}


def clone_structure(src_path, out_path, overrides, global_note):
    """Create a fresh classic-format (NETCDF3_64BIT_OFFSET) copy of src_path,
    with every dim/var/attr copied, except variable names in `overrides`
    (dict: varname -> new ndarray) get the override data instead of the
    source's own data. No compression, no chunking, one write per variable."""
    src = nc4.Dataset(src_path)
    dst = nc4.Dataset(out_path, "w", format="NETCDF3_64BIT_OFFSET")

    for name, dim in src.dimensions.items():
        dst.createDimension(name, (None if dim.isunlimited() else len(dim)))

    for name, var in src.variables.items():
        newvar = dst.createVariable(name, var.dtype, var.dimensions)
        newvar.setncatts({k: var.getncattr(k) for k in var.ncattrs()})
        if name in overrides:
            newvar[:] = overrides[name]
        else:
            newvar[:] = var[:]

    dst.setncatts({k: src.getncattr(k) for k in src.ncattrs()})
    dst.setncattr("scenario_note", global_note)
    dst.close()
    src.close()


def group_sum(pft, idx):
    """pft: (..., natpft, lat, lon) -> sum over given natpft indices -> (..., lat, lon)."""
    return pft[..., idx, :, :].sum(axis=-3)


def safe_div(numer, denom):
    out = np.zeros_like(numer)
    mask = denom > 0
    out[mask] = numer[mask] / denom[mask]
    return out


def ramp(years):
    a = (years.astype(float) - RAMP_START_YEAR) / (RAMP_END_YEAR - RAMP_START_YEAR)
    return np.clip(a, 0.0, 1.0)


# ================================================================== historical anchors (shared across all 4 SSPs)
with nc4.Dataset(HIST) as ds:
    year_hist = np.array(ds["YEAR"][:])
    i1850 = int(np.where(year_hist == 1850)[0][0])
    i2023 = int(np.where(year_hist == 2023)[0][0])
    pft_1850 = np.array(ds["PCT_NAT_PFT"][i1850, :, :, :])   # (natpft, lat, lon)
    pft_2023 = np.array(ds["PCT_NAT_PFT"][i2023, :, :, :])

forest_1850 = group_sum(pft_1850, TREE_PFT)     # (lat, lon), % units
forest_2023 = group_sum(pft_2023, TREE_PFT)
grass_2023 = group_sum(pft_2023, GRASS_PFT)

deficit = np.clip(forest_1850 - forest_2023, 0.0, None)
full_increment = np.minimum(deficit, grass_2023)   # RF target, % of gridcell, (lat, lon)

# RF tree sub-PFT weights: local 1850 forest composition. Always defined
# where full_increment>0 (that requires forest_1850>0).
w_tree = {k: safe_div(pft_1850[k], forest_1850) for k in TREE_PFT}

# Grass sub-PFT weights (used by both RF's grass debit and DF's forest->grass
# credit): local 2023 grass composition, with SEUS-wide fallback where
# grass_2023==0. Note this fallback is exercised by DF but not by RF: RF's
# full_increment is min(deficit, grass_2023), which is forced to 0 wherever
# grass_2023==0, so RF never actually multiplies by the fallback weights.
grass_has = grass_2023 > 0
w_grass = {k: np.where(grass_has, safe_div(pft_2023[k], grass_2023), FALLBACK_GRASS_SPLIT[k])
           for k in GRASS_PFT}

n_fallback = int(((~grass_has) & (forest_2023 > 0)).sum())
print(f"[setup] grass-split fallback applies to {n_fallback} forested cells with zero 2023 grass "
      f"(exercised by DF only, not RF)")
print(f"[setup] RF target area (sum of full_increment, %-of-cell units): {full_increment.sum():.1f}")


for ssp in SSPS:
    print(f"\n=== {ssp} ===")
    default_path = os.path.join(DEFAULT_DIR, f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}_simyr2024-2100.nc")
    with nc4.Dataset(default_path) as ds:
        years = np.array(ds["YEAR"][:])
        default_pft = np.array(ds["PCT_NAT_PFT"][:])            # (time, natpft, lat, lon)
        default_harvest = {v: np.array(ds[v][:]) for v in HARVEST_VARS}
    ntime = years.size

    r = ramp(years)                                              # (time,)
    increment_target = full_increment[None, :, :] * r[:, None, None]   # (time, lat, lon), desired debit

    # ---------------- RF ----------------
    # Debit grass sub-PFTs first, clipped to what Default actually has that
    # year (guards against the rare case where Default's own SSP trajectory
    # has already shrunk a grass sub-PFT below its 2023 value by some future
    # year -- clipping here keeps PCT_NAT_PFT sum-to-100 exact by construction,
    # since forest only gains exactly what grass gives up).
    grass_removed = np.zeros((ntime,) + full_increment.shape)
    rf_pft = default_pft.copy()
    for k in GRASS_PFT:
        desired = increment_target * w_grass[k][None, :, :]
        removed_k = np.minimum(desired, default_pft[:, k, :, :])
        rf_pft[:, k, :, :] = default_pft[:, k, :, :] - removed_k
        grass_removed += removed_k
    n_clipped = int((grass_removed < increment_target - 1e-9).sum())
    if n_clipped:
        print(f"[RF] grass-debit clipped below target in {n_clipped} (cell,year) combos "
              f"-- Default's own grass fell short of the 2023-based target that year")
    for k in TREE_PFT:
        rf_pft[:, k, :, :] = default_pft[:, k, :, :] + grass_removed * w_tree[k][None, :, :]

    out_rf = os.path.join(OUT_DIR, f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}_RF_simyr2024-2100.nc")
    clone_structure(default_path, out_rf, {"PCT_NAT_PFT": rf_pft},
                     f"RF (reforestation): grass-only reforestation of the 1850-vs-2023 forest "
                     f"deficit, capped per-cell at min(deficit, 2023 grass). Ramped linearly "
                     f"{RAMP_START_YEAR}-{RAMP_END_YEAR}, then held through 2100 as Default plus "
                     f"that increment. Note the increment is additionally clipped each year to "
                     f"the grass Default actually has that year, so RF-Default is slightly below "
                     f"the nominal target where the SSP trajectory has already shrunk grass "
                     f"(forest is credited the actually-removed grass, keeping sum-to-100 exact). "
                     f"Tree sub-PFT split by 1850 local forest composition; grass "
                     f"debit split by 2023 local grass composition. HARVEST_* unchanged from "
                     f"Default. Built {os.path.basename(__file__)}, definitions locked 2026-08-19.")
    print(f"[RF] wrote {out_rf}")

    # ---------------- DF ----------------
    default_forest = group_sum(default_pft, TREE_PFT)   # (time, lat, lon)
    df_pft = default_pft.copy()
    for k in TREE_PFT:
        df_pft[:, k, :, :] = 0.0
    for k in GRASS_PFT:
        df_pft[:, k, :, :] = default_pft[:, k, :, :] + default_forest * w_grass[k][None, :, :]

    df_harvest = {v: np.zeros_like(default_harvest[v]) for v in HARVEST_VARS}
    overrides = {"PCT_NAT_PFT": df_pft}
    overrides.update(df_harvest)
    out_df = os.path.join(OUT_DIR, f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}_DF_simyr2024-2100.nc")
    clone_structure(default_path, out_df, overrides,
                     f"DF (deforestation counterfactual, NOT frozen/protected forest): all "
                     f"forest cleared instantaneously every year 2024-2100, routed to grass "
                     f"(2023 local composition, SEUS-wide C3=85%/C4=15% fallback where 2023 "
                     f"grass=0), locked at zero -- never regrows. HARVEST_* zeroed. This is a "
                     f"deliberate, unrestricted theoretical upper bound for Default-DF "
                     f"'avoiding deforestation' accounting -- not an implementable scenario. "
                     f"Built {os.path.basename(__file__)}, definitions locked 2026-08-19.")
    print(f"[DF] wrote {out_df}")

    # ---------------- RH ----------------
    rh_harvest = {v: default_harvest[v] * RH_SCALE for v in HARVEST_VARS}
    out_rh = os.path.join(OUT_DIR, f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}_RH_simyr2024-2100.nc")
    clone_structure(default_path, out_rh, rh_harvest,
                     f"RH (reduced harvest): all 5 HARVEST_* variables scaled by {RH_SCALE} "
                     f"(annual harvest rate halved) for all years. Deliberate departure from "
                     f"the proposal's literal 'extend the interval by 50%' (which would be "
                     f"/1.5); the equivalent rotation-interval statement for a halved rate is a "
                     f"DOUBLED interval, not a 50% longer one. PCT_NAT_PFT unchanged from "
                     f"Default. Built {os.path.basename(__file__)}, definitions locked "
                     f"2026-08-19 (RH ratio revised to 0.5 same day).")
    print(f"[RH] wrote {out_rh}")

    # ---------------- validation (read-back, must not error) ----------------
    for path, label in [(out_rf, "RF"), (out_df, "DF"), (out_rh, "RH")]:
        ds = nc4.Dataset(path)
        for v in ["PCT_NAT_PFT"] + HARVEST_VARS:
            arr = np.array(ds[v][:])
            assert not np.isnan(arr).any(), f"{label} {v}: NaN on read-back"
        s = np.array(ds["PCT_NAT_PFT"][:]).sum(axis=1)
        land = s > 0
        max_err = float(np.abs(s[land] - 100).max()) if land.any() else 0.0
        print(f"[{label}] read-back OK; PCT_NAT_PFT sum-to-100 max|err|={max_err:.6f}")
        ds.close()

    with nc4.Dataset(out_df) as ds:
        tree_check = group_sum(np.array(ds["PCT_NAT_PFT"][:]), TREE_PFT)
        print(f"[DF] max residual tree PFT after clearing: {float(tree_check.max()):.6f} (should be 0)")
        for v in HARVEST_VARS:
            print(f"[DF] {v} max|value|: {float(np.abs(ds[v][:]).max()):.6f} (should be 0)")

    with nc4.Dataset(default_path) as dso, nc4.Dataset(out_rh) as dsn:
        for v in HARVEST_VARS:
            so = float(np.nansum(dso[v][:]))
            sn = float(np.nansum(dsn[v][:]))
            ratio = sn / so if so != 0 else float("nan")
            print(f"[RH] {v}: default_total={so:.4f} new_total={sn:.4f} ratio={ratio:.6f} "
                  f"(expect {RH_SCALE})"
                  if so else f"[RH] {v}: default_total=0 (SEUS-wide zero, ratio undefined)")

print("\nAll 4 SSPs x 3 scenarios (12 files) written to", OUT_DIR)
