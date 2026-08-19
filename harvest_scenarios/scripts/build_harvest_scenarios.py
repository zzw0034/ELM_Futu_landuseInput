#!/usr/bin/env python
"""Build the 9 management-scenario landuse.timeseries files: one shared
Reforestation (RF) file plus per-SSP Deforestation counterfactual (DF) and
Reduced-Harvest (RH) files for SSP1_RCP19, SSP2_RCP45, SSP3_RCP70, SSP5_RCP85.

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

  RF: a SCENARIO-INDEPENDENT policy prescription, so ONE file serves all
      four SSP runs. Starting from the shared 2023 historical anchor, forest
      is restored toward the 1850 extent -- per cell by min(1850 deficit,
      2023 grass) -- linearly over 2024-2050, then held constant to 2100.
      GRASS ONLY: cropland is never converted, which closes 82.5% of the
      1850 DEFICIT (820075 of 994213), leaving RF at 96.9% of the 1850
      forest EXTENT itself; this keeps RF a credible offset-style
      intervention (real programs target marginal land, not productive
      cropland). All other PFTs are frozen at 2023, and all five HARVEST_*
      are ZERO -- restoring forest also means protecting it, and zeroing
      harvest is what removes the last scenario-specific field and makes a
      single shared file correct. Trees gained are split by each cell's 1850
      forest composition, grass given up by its 2023 grass composition.
      Interpretation caveats live in the scenario_note written into the file.
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

Usage:
    build_harvest_scenarios.py            # all 4 SSPs, sequentially
    build_harvest_scenarios.py 2          # only ALL_SSPS[2], for Slurm job arrays
    build_harvest_scenarios.py SSP2_RCP45 # same, by name
"""
import os
import sys
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
ALL_SSPS = ["SSP1_RCP19", "SSP2_RCP45", "SSP3_RCP70", "SSP5_RCP85"]

# Optional CLI arg selects a single SSP (index or name) so the 4 SSPs can be
# run as a Slurm job array -- the per-SSP loop body is fully independent
# (shared inputs are read-only, outputs have disjoint filenames). With no
# arg, all 4 run sequentially in one process.
if len(sys.argv) > 1:
    sel = sys.argv[1]
    if sel.isdigit():
        i = int(sel)
        if not 0 <= i < len(ALL_SSPS):
            sys.exit(f"SSP index {i} out of range 0..{len(ALL_SSPS)-1}")
        SSPS = [ALL_SSPS[i]]
    elif sel in ALL_SSPS:
        SSPS = [sel]
    else:
        sys.exit(f"unknown SSP {sel!r}; expected one of {ALL_SSPS} or an index 0..{len(ALL_SSPS)-1}")
else:
    SSPS = list(ALL_SSPS)
print(f"[setup] building scenarios for: {', '.join(SSPS)}")

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


def clone_structure(src_path, out_path, overrides, global_note, natveg_mask=None):
    """Create a fresh classic-format (NETCDF3_64BIT_OFFSET) copy of src_path,
    with every dim/var/attr copied, except variable names in `overrides`
    (dict: varname -> new ndarray) get the override data instead of the
    source's own data. No compression, no chunking, one write per variable.

    Writes to a temporary path, verifies the result reads back cleanly, and
    only then atomically renames it into place. A job killed mid-write (this
    workload peaks near 18GB, so an OOM kill is a realistic failure) must not
    be able to leave a half-written file sitting under the final name -- this
    project has already been burned once by a file that looked present but
    was unreadable. os.replace() is atomic within a directory, so the final
    name either does not exist or refers to a fully written, verified file.
    """
    tmp_path = f"{out_path}.tmp.{os.environ.get('SLURM_JOB_ID', os.getpid())}"
    src = nc4.Dataset(src_path)
    dst = nc4.Dataset(tmp_path, "w", format="NETCDF3_64BIT_OFFSET")

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

    # Integrity gate: every variable must read back without an HDF/NetCDF
    # error and without NaN, and PCT_NAT_PFT must still sum to 100 over the
    # natural-vegetation mask. Only then is the file promoted to its final
    # name. Note the mask comes from PCT_NATVEG (time-invariant, taken from
    # the source), NOT from "wherever PCT_NAT_PFT happens to be nonzero" --
    # the latter is self-referential and can never catch a cell that was
    # wrongly zeroed out, since such a cell would simply drop out of its own
    # mask.
    try:
        with nc4.Dataset(tmp_path) as chk:
            for name in chk.variables:
                arr = np.array(chk[name][:])
                if arr.dtype.kind == "f" and np.isnan(arr).any():
                    raise ValueError(f"{name} contains NaN")
            if natveg_mask is not None and "PCT_NAT_PFT" in chk.variables:
                s = np.array(chk["PCT_NAT_PFT"][:]).sum(axis=1)
                err = np.abs(s[np.broadcast_to(natveg_mask[None, :, :], s.shape)] - 100.0)
                if err.size and err.max() > 1e-3:
                    raise ValueError(f"PCT_NAT_PFT sum-to-100 max|err|={err.max():.6g} over natveg>0")
    except Exception:
        # Leave the tmp file for post-mortem; just never promote it.
        raise

    os.replace(tmp_path, out_path)


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


# ============================ RF (built once, shared by all four SSPs) ======
# RF is a SCENARIO-INDEPENDENT prescription, so exactly one file is produced
# and every SSP's RF run points at it. This is safe: the four Default files
# were verified to differ ONLY in PCT_NAT_PFT and the five HARVEST_* fields
# (everything else, GRAZING included, is bit-identical), and RF overrides
# precisely those -- so the result does not depend on which file is used as
# the structural template.
#
# HARVEST_* is set to ZERO. Reforestation here means restoring AND protecting
# forest, so no wood is harvested. Note what that implies for interpretation:
# the harvest ban applies to ALL forest, including the ~4.65e6 (%-of-cell
# units) already standing in 2023, not only the ~8.2e5 newly planted -- about
# 6.7x more area. So RF-Default measures reforestation PLUS a region-wide
# harvest ban, not reforestation alone, and it overlaps RH (which halves the
# same harvest). Report it as "forest restoration and protection". The
# project's decision (2026-08-19) is to claim only the COMBINED effect and
# not to split it: a clean split needs an extra NH scenario (Default PFT +
# zero harvest) and the compute budget does not allow it. Note that
# (RF-Default) - 2*(RH-Default) is a sensitivity check at best, NOT a
# decomposition -- the carbon response is not linear, and RH's harvest acts
# on Default's forest area while RF's acts on the restored area.
# This also makes RF and DF a symmetric pair of bookends: maximum forest
# carbon vs zero forest carbon, both unharvested, with Default in between.
rf_template = os.path.join(DEFAULT_DIR,
                           f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ALL_SSPS[0]}_simyr2024-2100.nc")
with nc4.Dataset(rf_template) as ds:
    years = np.array(ds["YEAR"][:])
    natveg_mask = np.array(ds["PCT_NATVEG"][:]) > 0
ntime = years.size
r = ramp(years)
increment_target = full_increment[None, :, :] * r[:, None, None]

if ALL_SSPS[0] in SSPS:
    # RF's land cover is SCENARIO-INDEPENDENT by design: it is a policy
    # prescription ("restore forest toward the 1850 extent by 2050, then hold
    # it"), not a perturbation layered on each SSP's own land trajectory. So
    # PCT_NAT_PFT is built from the 2023 historical anchor and evolves only
    # through the forest<->grass exchange; every other PFT stays frozen at
    # 2023. The result is byte-identical across all four SSPs.
    #
    # Why not "Default + increment" (the earlier design): there, each SSP's
    # own trajectory competed for the same grass, so the delivered increment
    # decayed after the ramp (measured: only 71.6-95.2% of nominal by 2100,
    # scenario-dependent). A policy target should not shrink because the
    # baseline world happens to reforest on its own. Note the consequence:
    # RF - Default now mixes the intervention with the removal of that SSP's
    # own land-use drift, and that drift is large and sign-varying across
    # scenarios (2100 forest vs 2023: SSP2-4.5 +635671, SSP3-7.0 -190237).
    # Both must be reported; see HARVEST_SCENARIOS.md.
    #
    # No clipping is possible here, by construction: the debit from grass PFT
    # k is full_increment * ramp * w_grass_k <= grass_2023 * w_grass_k =
    # p_2023[k], so RF grass can reach zero but never goes negative, and the
    # trees gain exactly what the grass gives up (sum-to-100 exact).
    #
    # HARVEST_* is zeroed (see the section header): restoring forest also
    # means protecting it. Zeroing rather than inheriting is also what makes
    # a single shared file correct -- harvest is the only remaining field
    # that differs between the four Defaults (HARVEST_SH1 totals 44992 /
    # 63829 / 51579 / 60317 for ssp119/245/370/585, a 42% spread), so once
    # it is zero, nothing scenario-specific is left.
    rf_pft = np.broadcast_to(pft_2023[None, :, :, :], (ntime,) + pft_2023.shape).copy()
    for k in GRASS_PFT:
        rf_pft[:, k, :, :] = pft_2023[k][None, :, :] - increment_target * w_grass[k][None, :, :]
    for k in TREE_PFT:
        rf_pft[:, k, :, :] = pft_2023[k][None, :, :] + increment_target * w_tree[k][None, :, :]
    neg = float(rf_pft.min())
    if neg < -1e-9:
        raise ValueError(f"RF produced a negative PFT fraction ({neg:g}) -- check the weights")
    # Cells where grass is fully consumed land on 0 but can come out at -7e-15
    # from the subtraction. Harmless numerically, but do not hand ELM a
    # negative area fraction; the clip costs ~1e-14 of sum-to-100.
    np.clip(rf_pft, 0.0, None, out=rf_pft)

    out_rf = os.path.join(OUT_DIR, "landuse.timeseries_SEUS_1_24deg_nlcd2elm_RF_simyr2024-2100.nc")
    rf_overrides = {"PCT_NAT_PFT": rf_pft}
    rf_overrides.update({v: np.zeros((ntime,) + full_increment.shape) for v in HARVEST_VARS})
    clone_structure(rf_template, out_rf, rf_overrides,
                     f"RF (reforestation): a SCENARIO-INDEPENDENT policy prescription. "
                     f"PCT_NAT_PFT starts from the 2023 historical anchor and restores forest "
                     f"toward the 1850 extent, per cell by min(1850 deficit, 2023 grass), "
                     f"linearly over {RAMP_START_YEAR}-{RAMP_END_YEAR}, then HELD CONSTANT to "
                     f"2100. Grass-only: cropland is never converted, so the target closes "
                     f"82.5% of the 1850 DEFICIT (820075 of 994213 in %-of-cell units), which "
                     f"puts the 2050+ plateau at 5469839 = 96.9% of the 1850 forest EXTENT "
                     f"(5643976). Do not conflate those two denominators. "
                     f"All non-tree, non-grass PFTs are frozen at their 2023 values, "
                     f"and ALL FIVE HARVEST_* fields are ZERO -- restoring forest also means "
                     f"protecting it. This single file is therefore shared by all four SSP "
                     f"runs; nothing scenario-specific remains. "
                     f"TWO CAUTIONS for interpretation. (1) The harvest ban covers ALL forest, "
                     f"including the ~4.65e6 already standing in 2023, not just the ~8.2e5 "
                     f"newly planted (~6.7x more area), so RF-Default measures reforestation "
                     f"PLUS a region-wide harvest ban and overlaps RH, which halves the same "
                     f"harvest; report it as 'forest restoration and protection' and claim only "
                     f"the COMBINED effect -- a clean split would need an extra NH (Default PFT, "
                     f"zero harvest) scenario, which this project does not run, and "
                     f"2x(RH-Default) is a sensitivity check, not a decomposition. "
                     f"(2) RF replaces "
                     f"rather than perturbs the SSP land trajectory, so RF-Default also absorbs "
                     f"that SSP's own land-use drift (2100 forest vs 2023: SSP1 +314760, "
                     f"SSP2 +635671, SSP3 -190237, SSP5 +127547). "
                     f"Tree sub-PFT split by 1850 local forest composition; grass debit by 2023 "
                     f"local grass composition. Built {os.path.basename(__file__)}, "
                     f"RF redefined 2026-08-19.",
                     natveg_mask=natveg_mask)
    print(f"[RF] wrote {out_rf}")

    del rf_pft, rf_overrides
else:
    print(f"[RF] skipped -- RF is scenario-independent and is built by the "
          f"{ALL_SSPS[0]} task; run --array=0 (or no argument) to produce it")

for ssp in SSPS:
    print(f"\n=== {ssp} ===")
    default_path = os.path.join(DEFAULT_DIR, f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{ssp}_simyr2024-2100.nc")
    with nc4.Dataset(default_path) as ds:
        years = np.array(ds["YEAR"][:])
        default_pft = np.array(ds["PCT_NAT_PFT"][:])            # (time, natpft, lat, lon)
        default_harvest = {v: np.array(ds[v][:]) for v in HARVEST_VARS}
        # Independent, time-invariant validation mask (see clone_structure).
        natveg_mask = np.array(ds["PCT_NATVEG"][:]) > 0
    ntime = years.size

    r = ramp(years)                                              # (time,)
    increment_target = full_increment[None, :, :] * r[:, None, None]   # (time, lat, lon)

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
                     f"Built {os.path.basename(__file__)}, definitions locked 2026-08-19.",
                     natveg_mask=natveg_mask)
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
                     f"2026-08-19 (RH ratio revised to 0.5 same day).",
                     natveg_mask=natveg_mask)
    print(f"[RH] wrote {out_rh}")

    # ---------------- validation ----------------
    # Read-back integrity and sum-to-100 (under the PCT_NATVEG mask) are
    # already enforced inside clone_structure, which refuses to promote a
    # file that fails them. What follows is scenario-specific semantics.

    # RF vs THIS baseline. The RF trajectory itself is met exactly by
    # construction, so the number worth printing is the gap to each SSP's own
    # baseline -- that is what the paper has to interpret, and it differs a
    # lot between scenarios because the baselines drift in opposite
    # directions. Read from the shared RF file, which every SSP run uses.
    shared_rf = os.path.join(OUT_DIR, "landuse.timeseries_SEUS_1_24deg_nlcd2elm_RF_simyr2024-2100.nc")
    if os.path.exists(shared_rf):
        with nc4.Dataset(shared_rf) as ds:
            rf_forest = group_sum(np.array(ds["PCT_NAT_PFT"][:]), TREE_PFT)
        default_forest_chk = group_sum(default_pft, TREE_PFT)
        f2023 = float(group_sum(pft_2023, TREE_PFT).sum())
        print(f"[RF] prescribed target {full_increment.sum():.1f} on a 2023 base of "
              f"{f2023:.1f} -> plateau {f2023 + full_increment.sum():.1f} from {RAMP_END_YEAR}")
        for y in (RAMP_END_YEAR, int(years[-1])):
            i = int(np.where(years == y)[0][0])
            rf_y = float(rf_forest[i].sum())
            df_y = float(default_forest_chk[i].sum())
            print(f"[RF] {y}: RF forest {rf_y:.1f} | {ssp} baseline {df_y:.1f} | "
                  f"RF-baseline {rf_y - df_y:+.1f}")
        del rf_forest, default_forest_chk
    else:
        print(f"[RF] shared RF file not present yet; run the {ALL_SSPS[0]} task to build it")

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

n_rf = 1 if ALL_SSPS[0] in SSPS else 0
print(f"\nDone: {len(SSPS)} SSP(s) x 2 per-SSP scenarios (DF, RH) + {n_rf} shared RF "
      f"= {len(SSPS)*2 + n_rf} files written to {OUT_DIR}")
print("Full set is 4 SSP x 2 + 1 shared RF = 9 files.")
