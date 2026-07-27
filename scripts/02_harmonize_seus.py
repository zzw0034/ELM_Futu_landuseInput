#!/usr/bin/env python
"""Harmonize NLCD-derived history + Chen2022 scenario trend over SEUS.

Implements HARMONIZATION_SEUS_PILOT.md (REFERENCE.md §13):
  base state  = NLCD (elmpft_from_nlcd_frac_pred), observed through 2023
  trend       = Chen2022 SSP1-RCP1.9, interpolated to annual, applied from 2024
  anchor      = NLCD 2023
  quantity    = p(j) = PCT_NATVEG * PCT_NAT_PFT(j)/100   [% of whole cell]
  altitude    = functional group (Chen sets group totals), re-split to 17 PFT by
                NLCD's frozen 2023 within-group proportions
  formula     = Chen2022 eq.(1) min-footprint, marched annually (§13.5)

Only PCT_NATVEG and PCT_NAT_PFT are produced. Region = SEUS bbox.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
import xarray as xr

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src")
from elm_landuse.chen_classes import ELM_PFT_NAMES, NPFT  # noqa: E402

NL = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
          "s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
# Chen scenario -> processed file (the 4 available SSPs)
CHEN = {
    "SSP1_RCP19": "chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc",
    "SSP2_RCP45": "chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc",
    "SSP4_RCP60": "chen2022_landuse_CONUS_SSP4_RCP60_2015-2100_1_24deg.nc",
    "SSP5_RCP85": "chen2022_landuse_CONUS_SSP5_RCP85_2015-2100_1_24deg.nc",
}
SEUS = dict(lon0=-95.0, lon1=-74.0, lat0=24.0, lat1=37.5)

ANCHOR = 2023
END = 2100
# PFT 16 (irrigated_crop) is 0 in both products (NLCD never populates it and no
# Chen class maps to it), so it belongs to no functional group here. It is parked
# in group 0 by GRP_OF_PFT below (harmless: its p(j)=0) and force-zeroed on output
# (FORCE_ZERO). Removing it from Crop does not change any number, only bookkeeping.
GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8], "Shrub": [9, 10, 11],
          "Grass": [12, 13, 14], "Crop": [15]}
GN = list(GROUPS)
NG = len(GN)
# length-NPFT map; PFTs not assigned to any group (e.g. 16) default to group 0.
GRP_OF_PFT = np.zeros(NPFT, dtype=int)
for _gi, _g in enumerate(GN):
    for _j in GROUPS[_g]:
        GRP_OF_PFT[_j] = _gi
FORCE_ZERO = [2, 3, 6, 8, 11, 12, 16]   # boreal/arctic/tropical + irrigated_crop: 0 in SEUS (§13.8)
R_EARTH = 6371.0


def cell_area_km2(lat, lon):
    dlat = float(np.mean(np.diff(lat))); dlon = float(np.mean(np.diff(lon)))
    ln = np.radians(lat + dlat/2); ls = np.radians(lat - dlat/2)
    band = R_EARTH**2 * np.radians(dlon) * (np.sin(ln) - np.sin(ls))
    return np.repeat(band[:, None], lon.size, axis=1)


def group_sum(p):
    """(NPFT,...) -> (NG,...) sum over each functional group's members."""
    return np.stack([p[GROUPS[g]].sum(axis=0) for g in GN])


# ============================================================================
# Stage B: LUH2 wood-harvest downscaling to the target grid, reusing s4_2's
# method (area-conserving, forest-weighted). Weight = our harmonized future tree
# cover x the annual harmonized natveg; harvest source = the matching-scenario LUH2
# v2f transitions in /luh. Annual (not static) natveg is used for both the weight
# and the LUT denominator, matching s4_2 -- see downscale_harvest's docstring.
# Helper functions (_safe_float32, _fraction_if_percent, _build_hr_to_coarse_index,
# _distribute_conservatively) are copied verbatim from s4_2_donwscale_LUH2harvest.py.
# ============================================================================

LUH_DIR = Path("/projects/hpcl-cli185/proj-shared/zw5/luh")
LUH_FILE = {"SSP1_RCP19": "ssp1rcp19_transitions.nc",
            "SSP2_RCP45": "ssp2rcp45_transitions.nc",
            "SSP4_RCP60": "ssp4rcp60_transitions.nc",
            "SSP5_RCP85": "ssp5rcp85_transitions.nc"}
HARVEST_VAR_MAP = {"primf_harv": "HARVEST_VH1", "primn_harv": "HARVEST_VH2",
                   "secmf_harv": "HARVEST_SH1", "secyf_harv": "HARVEST_SH2",
                   "secnf_harv": "HARVEST_SH3"}
TREE_PFT_IDXS = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=np.int64)
LUH_SSP_YEAR0 = 2015          # LUH2 v2f SSP transitions start at calendar 2015
LUH_SSP_LAST = 2099           # ... and end at calendar 2099


def _safe_float32(arr):
    out = np.asarray(arr, dtype=np.float32)
    np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return out


def _build_hr_to_coarse_index(lat_hr, lon_hr, lat_coarse, lon_coarse):
    """Map each high-res cell to its coarse-cell id (s4_2)."""
    nlat_c, nlon_c = lat_coarse.size, lon_coarse.size
    dlat = float(np.median(np.diff(lat_coarse)))
    dlon = float(np.median(np.diff(lon_coarse)))
    lat0 = float(lat_coarse[0] - 0.5 * dlat)
    lon0 = float(lon_coarse[0] - 0.5 * dlon)
    lat_idx = np.floor((lat_hr - lat0) / dlat).astype(np.int64)
    lon_idx = np.floor((lon_hr - lon0) / dlon).astype(np.int64)
    lat_ok = (lat_idx >= 0) & (lat_idx < nlat_c)
    lon_ok = (lon_idx >= 0) & (lon_idx < nlon_c)
    inside_2d = lat_ok[:, None] & lon_ok[None, :]
    coarse_id_2d = (lat_idx[:, None] * nlon_c + lon_idx[None, :]).astype(np.int64)
    coarse_id_2d[~inside_2d] = 0
    return coarse_id_2d, inside_2d, np.array([nlat_c, nlon_c], dtype=np.int64)


def _distribute_conservatively(coarse_2d, weights_2d, area_2d, coarse_id_2d, inside_2d, ncoarse):
    """frac_i = F * w_i * sum(area) / sum(w*area), conserving harvested AREA (s4_2)."""
    coarse_flat = _safe_float32(coarse_2d).reshape(-1)
    w_flat = _safe_float32(weights_2d).reshape(-1)
    a_flat = _safe_float32(area_2d).reshape(-1).astype(np.float64)
    id_flat = coarse_id_2d.reshape(-1)
    inside_flat = inside_2d.reshape(-1)
    w_flat = np.where(inside_flat, w_flat, 0.0)
    a_flat = np.where(inside_flat, a_flat, 0.0)
    sum_wa = np.bincount(id_flat, weights=w_flat * a_flat, minlength=ncoarse)
    sum_a = np.bincount(id_flat, weights=a_flat, minlength=ncoarse)
    hr_flat = np.zeros_like(w_flat, dtype=np.float32)
    denom = sum_wa[id_flat]
    valid = inside_flat & (denom > 0.0)
    hr_flat[valid] = (coarse_flat[id_flat[valid]] * sum_a[id_flat[valid]]
                      * w_flat[valid] / denom[valid]).astype(np.float32)
    coarse_area_sums = np.bincount(id_flat, weights=hr_flat.astype(np.float64) * a_flat,
                                   minlength=ncoarse)
    return hr_flat.reshape(weights_2d.shape), coarse_area_sums, sum_a, id_flat, a_flat, inside_flat


def downscale_harvest(scenario, latc, lonc, tree_comp_pct, natveg_pct, out_years):
    """Downscale LUH2 harvest to the target grid, weighted by our harmonized forest.

    tree_comp_pct : (nout,ny,nx)  tree share of natveg [%] per out year (harmonized)
    natveg_pct    : (nout,ny,nx)  ANNUAL harmonized natveg [%] per out year, matching
                                  s4_2's historical convention (dynamic natveg in both
                                  the weight and the LUT denominator). NOTE: this is
                                  deliberately NOT the static PCT_NATVEG written to the
                                  output file -- see build_landuse_timeseries.
    Returns dict out_name -> (nout,ny,nx) float32 [LUT units, fraction of veg unit],
    plus a list of per-year area-conservation ratios (placed / allocatable LUH2 area).
    """
    nout = len(out_years)
    assert natveg_pct.shape[0] == nout, "natveg_pct must be annual (nout,ny,nx)"
    ny, nx = natveg_pct.shape[1:]
    area_hr = cell_area_km2(latc, lonc)
    veg_frac = (natveg_pct / 100.0).astype(np.float64)                      # (nout,ny,nx) 0..1
    luh = xr.open_dataset(LUH_DIR / LUH_FILE[scenario], decode_times=False)
    clat = luh.lat.values
    clon = luh.lon.values
    lat_sort = np.argsort(clat)                                            # LUH2 lat desc -> asc
    clat_asc = clat[lat_sort]
    coarse_id, inside, cshape = _build_hr_to_coarse_index(latc, lonc, clat_asc, clon)
    ncoarse = int(cshape[0] * cshape[1])
    id_flat = coarse_id.reshape(-1)
    a_in = np.where(inside.reshape(-1), area_hr.reshape(-1).astype(np.float64), 0.0)
    area_coarse = np.bincount(id_flat, weights=a_in, minlength=ncoarse)     # fine area per coarse cell

    out = {v: np.zeros((nout, ny, nx), dtype=np.float32) for v in HARVEST_VAR_MAP.values()}
    cons = []
    for k, Y in enumerate(out_years):
        cal = int(Y) - 1                                                   # k=-1 label convention
        hidx = min(cal, LUH_SSP_LAST) - LUH_SSP_YEAR0
        vf = veg_frac[k]                                                   # this year's natveg
        w = ((tree_comp_pct[k] / 100.0) * vf).astype(np.float32)           # forest cover weight
        w = np.where(w > 0, w, 0.0).astype(np.float32)
        sum_w = np.bincount(id_flat, weights=np.where(inside.reshape(-1), w.reshape(-1), 0.0),
                            minlength=ncoarse)
        alloc = sum_w > 0.0                                                # coarse cells with forest
        lut_grids = {}
        luh_area = 0.0
        placed = 0.0
        for luh_name, out_name in HARVEST_VAR_MAP.items():
            coarse = _safe_float32(luh[luh_name].isel(time=hidx).values[lat_sort, :])
            hr, ca_sums, _, _, _, _ = _distribute_conservatively(
                coarse, w, area_hr, coarse_id, inside, ncoarse)
            with np.errstate(divide="ignore", invalid="ignore"):
                lut = np.divide(hr, vf, out=np.zeros_like(hr, dtype=np.float32),
                                where=vf > 0.0)
            lut_grids[out_name] = lut
            cflat = coarse.reshape(-1).astype(np.float64)
            luh_area += float((cflat * area_coarse)[alloc].sum())
            placed += float(ca_sums[alloc].sum())
        # cap the 5-category total to <=1 (option A: clip excess)
        lut_sum = sum(lut_grids.values())
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            scale = np.where(lut_sum > 1.0, 1.0 / np.where(lut_sum > 0, lut_sum, 1.0), 1.0)
        for out_name, lut in lut_grids.items():
            out[out_name][k] = np.clip(lut * scale, 0.0, 1.0).astype(np.float32)
        cons.append(placed / luh_area if luh_area > 0 else 1.0)
    luh.close()
    return out, cons


# ============================================================================
# Future landuse.timeseries mode (§13 on the target ELM grid; appended below the
# original standalone harmonizer). Anchor = the target landuse.timeseries file's
# own 2023 state; Chen trend = a target-grid Chen file (produced by
# 01 --like <target>). Only PCT_NAT_PFT is harmonized; natveg is the target's
# static column (option A). This is stage A: the composition on the target grid.
# ============================================================================

TARGET_DEFAULT = ("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/"
                  "Make_surface_data/surfdata_results/"
                  "landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc")


def _march_composition(p_nl, p_ch):
    """§13 group-level min-footprint march + NLCD-frozen re-split.

    p_nl : (NPFT,ny,nx)      anchor p(j) = natveg*natpft/100 [% of cell]
    p_ch : (nyr,NPFT,ny,nx)  Chen p(j) annual (index 0 = anchor year)
    Returns p_harm (nyr,NPFT,ny,nx) [% of cell]; boreal/PFT6 forced 0.
    """
    ny, nx = p_nl.shape[1:]
    nyr = p_ch.shape[0]
    P_nl_g = group_sum(p_nl)                                   # (NG,ny,nx)
    P_ch_g = np.stack([group_sum(p_ch[k]) for k in range(nyr)])
    P_nl_g_pft = P_nl_g[GRP_OF_PFT]
    with np.errstate(invalid="ignore", divide="ignore"):
        w_frozen = np.where(P_nl_g_pft > 0, p_nl / P_nl_g_pft, 0.0)
    P_harm_g = np.empty((nyr, NG, ny, nx), dtype=np.float64)
    P_harm_g[0] = P_nl_g
    for i in range(1, nyr):
        Ph, Cprev, Cnow = P_harm_g[i - 1], P_ch_g[i - 1], P_ch_g[i]
        dC = Cnow - Cprev
        Cprev_safe = np.where(Cprev > 0, Cprev, 1.0)
        out = np.where(Ph == 0, np.maximum(dC, 0.0),
                       np.where(Cprev <= Ph, Ph + dC, Ph * Cnow / Cprev_safe))
        P_harm_g[i] = np.maximum(out, 0.0)

    def resplit(i):
        Pg_pft = P_harm_g[i][GRP_OF_PFT]
        P_ch_g_pft = P_ch_g[i][GRP_OF_PFT]
        with np.errstate(invalid="ignore", divide="ignore"):
            w_ch = np.where(P_ch_g_pft > 0, p_ch[i] / P_ch_g_pft, 0.0)
        w = np.where(P_nl_g_pft > 0, w_frozen, w_ch)
        ph = Pg_pft * w
        ph[FORCE_ZERO] = 0.0
        return ph

    return np.stack([resplit(i) for i in range(nyr)])


def _interp_annual(p_native, native_years, out_years):
    """Linear-interpolate p(j) from native (5-yr) to annual, on the year axis."""
    ny, nx = p_native.shape[2:]
    out = np.empty((len(out_years), p_native.shape[1], ny, nx), dtype=np.float64)
    for k, y in enumerate(out_years):
        if y <= native_years[0]:
            out[k] = p_native[0]
        elif y >= native_years[-1]:
            out[k] = p_native[-1]
        else:
            b = int(np.searchsorted(native_years, y, side="right"))
            w = (y - native_years[b - 1]) / (native_years[b] - native_years[b - 1])
            out[k] = p_native[b - 1] * (1 - w) + p_native[b] * w
    return out


def build_landuse_timeseries(args):
    """Stage A: harmonized PCT_NAT_PFT on the target grid, natveg=0 -> 100% bare."""
    tgt = args.anchor_file or TARGET_DEFAULT
    t = xr.open_dataset(tgt, decode_times=False)
    latc = np.asarray(t["LATIXY"].values)[:, 0]
    lonc = np.asarray(t["LONGXY"].values)[0, :]
    tyr = t["YEAR"].values.astype(int)
    i23 = int(np.where(tyr == ANCHOR)[0][0])
    natveg_a = np.nan_to_num(t["PCT_NATVEG"].values.astype(np.float64))          # (ny,nx) static
    natpft23 = np.nan_to_num(t["PCT_NAT_PFT"].isel(time=i23).values.astype(np.float64))  # (17,ny,nx)
    grazing23 = np.nan_to_num(t["GRAZING"].isel(time=i23).values.astype(np.float32))     # (ny,nx)
    t.close()
    ny, nx = natveg_a.shape

    chen_path = (args.chen_targetgrid or (OUTDIR / "interim" /
                 f"chen_targetgrid_{args.scenario}_2015-2100_1_24deg.nc"))
    c = xr.open_dataset(chen_path)
    assert np.allclose(c.lat.values, latc) and np.allclose(c.lon.values, lonc), \
        "chen target-grid file grid != anchor grid"
    cyrs = c.time.values.astype(int)
    cnv = np.nan_to_num(c.PCT_NATVEG.values.astype(np.float64))                  # (nt,ny,nx)
    cpf = np.nan_to_num(c.PCT_NAT_PFT.values.astype(np.float64))                 # (nt,17,ny,nx)
    c.close()

    # anchor p(j) = target static natveg * target natpft(2023); Chen p(j) annual
    p_nl = natpft23 * natveg_a[None] / 100.0
    p_ch_native = cpf * cnv[:, None] / 100.0
    annual = np.arange(ANCHOR, END + 1)                                          # 2023..2100
    p_ch = _interp_annual(p_ch_native, cyrs, annual)

    p_harm = _march_composition(p_nl, p_ch)                                      # (nyr,17,ny,nx)

    # recover composition; force 100% bare where target natveg==0 or Σ==0
    natveg_zero = natveg_a == 0.0
    nyr = p_harm.shape[0]
    comp = np.zeros((nyr, NPFT, ny, nx), dtype=np.float32)
    # Annual harmonized natveg = Sum_j p(j), i.e. the natveg implied by the marched
    # p(j) field (anchored at the target's 2023 natveg, carrying the Chen trend).
    # Same quantity the standalone SEUS mode writes as PCT_NATVEG. Used by stage B
    # only; the output file still carries the target's static column (see stage C).
    natveg_dyn = np.zeros((nyr, ny, nx), dtype=np.float64)
    for i in range(nyr):
        s = p_harm[i].sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            ci = np.where(s > 0, 100.0 * p_harm[i] / np.where(s > 0, s, 1.0)[None], 0.0)
        fill = natveg_zero | (s <= 1e-9)
        ci[:, fill] = 0.0
        ci[0, fill] = 100.0                                                      # PFT0 (bare) = 100
        comp[i] = ci.astype(np.float32)
        nvi = np.clip(s, 0.0, 100.0)
        nvi[fill] = 0.0
        natveg_dyn[i] = nvi

    out_years = np.arange(ANCHOR + 1, END + 1)                                   # 2024..2100
    pft_out = comp[1:]                                                           # drop 2023 anchor slice
    natveg_out = natveg_dyn[1:]                                                  # (nout,ny,nx)

    # ---- Stage B: harvest downscale (LUH2 scenario -> target grid) ----
    # Dynamic natveg here (weight + LUT denominator), matching s4_2's historical
    # convention. The file's PCT_NATVEG stays static, so ELM's recovered harvest
    # area carries a factor natveg_static/natveg_dyn; reported below.
    tree_comp = pft_out[:, TREE_PFT_IDXS].sum(axis=1)                            # (nout,ny,nx) tree % of natveg
    harv, cons = downscale_harvest(args.scenario, latc, lonc, tree_comp, natveg_out, out_years)
    grazing_out = np.repeat(grazing23[None], len(out_years), axis=0).astype(np.float32)  # persist 2023
    print(f"  harvest area-conservation (placed/allocatable LUH2): "
          f"min {min(cons):.4f} mean {float(np.mean(cons)):.4f} max {max(cons):.4f}")
    for v in ("HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"):
        print(f"    {v}: max {harv[v].max():.4g} mean {harv[v].mean():.4g}")
    # How far the file's static PCT_NATVEG sits from the denominator actually used.
    # ELM recovers harvested area = HARVEST * PCT_NATVEG_static, so this ratio is
    # the multiplicative offset vs the LUH2 area that was downscaled.
    _m = (natveg_out > 0) & (natveg_a[None] > 0)
    if _m.any():
        _r = np.broadcast_to(natveg_a[None], natveg_out.shape)[_m] / natveg_out[_m]
        _p = np.percentile(_r, [5, 50, 95])
        print(f"  natveg_static/natveg_dynamic (ELM area offset): "
              f"p05 {_p[0]:.4f} p50 {_p[1]:.4f} p95 {_p[2]:.4f} max {_r.max():.4f}")
        _wa = np.repeat(cell_area_km2(latc, lonc)[None], len(out_years), axis=0)[_m]
        print(f"  area-weighted mean offset: "
              f"{float((_r * _wa).sum() / _wa.sum()):.4f} (1.0 = no offset)")

    # ---- validation ----
    print(f"[timeseries stageA] scenario {args.scenario}  grid {ny}x{nx}")
    ss = pft_out.sum(axis=1)
    print(f"  sum-to-100: max|sum-100| = {float(np.abs(ss - 100.0).max()):.4f}  "
          f"(min {ss.min():.3f} max {ss.max():.3f})")
    m_veg = natveg_a > 0
    d23 = float(np.abs(comp[0][:, m_veg] - natpft23[:, m_veg].astype(np.float32)).max())
    n_anom = int((natveg_zero & (natpft23[0] < 99.9)).sum())
    print(f"  anchor 2023 composition == target 2023 (natveg>0): max|diff| = {d23:.4f}")
    nz = int(natveg_zero.sum())
    barefill_ok = np.allclose(pft_out[:, 0][:, natveg_zero], 100.0) and \
        np.allclose(pft_out[:, 1:][:, :, natveg_zero], 0.0)
    print(f"  natveg=0 cells ({nz:,}) -> 100% bare: {barefill_ok}  "
          f"({n_anom} target cells were non-bare at natveg=0, overridden)")

    # ---- Stage C: assemble future landuse.timeseries with the target schema ----
    tds = xr.open_dataset(tgt, decode_times=False)
    STATIC_VARS = ["LANDFRAC_PFT", "PFTDATA_MASK", "PCT_NATVEG", "PCT_CROP", "AREA",
                   "LONGXY", "LATIXY", "PCT_WETLAND", "PCT_LAKE", "PCT_GLACIER",
                   "PCT_URBAN", "APATITE_P", "LABILE_P", "OCCLUDED_P", "SECONDARY_P"]

    def _at(v):
        return dict(tds[v].attrs) if v in tds.variables else {}

    dv = {}
    for v in STATIC_VARS:                                    # copy verbatim from target
        if v in tds.variables:
            dv[v] = (tds[v].dims, tds[v].values, _at(v))
    # cast time-varying vars to float64 to match the target dtype exactly
    dv["PCT_NAT_PFT"] = (("time", "natpft", "lsmlat", "lsmlon"),
                         pft_out.astype(np.float64), _at("PCT_NAT_PFT"))
    for v in ("HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"):
        dv[v] = (("time", "lsmlat", "lsmlon"), harv[v].astype(np.float64), _at(v))
    dv["GRAZING"] = (("time", "lsmlat", "lsmlon"), grazing_out.astype(np.float64), _at("GRAZING"))
    dv["YEAR"] = (("time",), out_years.astype(np.int32), _at("YEAR"))
    fn = np.array([f"harmonized_{args.scenario}_{int(y)}".ljust(256)[:256].encode()
                   for y in out_years], dtype="S256")
    dv["input_pftdata_filename"] = (("time",), fn, _at("input_pftdata_filename"))

    coords = {"time": out_years.astype(np.int32)}
    if "natpft" in tds.coords:
        coords["natpft"] = tds["natpft"].values
    out_ds = xr.Dataset(dv, coords=coords)
    out_ds.attrs.update(dict(tds.attrs))
    out_ds.attrs.update(
        harmonized_scenario=args.scenario,
        harmonized_note=(f"future 2024-2100: NLCD-2023 state (from {Path(tgt).name}) + "
                         f"Chen {args.scenario} trend (harmonize_seus.py §13); harvest downscaled "
                         f"from LUH2 {LUH_FILE[args.scenario]} (forest-weighted, area-conserving); "
                         f"GRAZING persisted from target 2023; natveg=0 -> 100% bare"),
        harvest_natveg_convention=(
            "HARVEST_* were downscaled and converted to LUT units using the ANNUAL "
            "harmonized natveg (sum_j p(j)), matching s4_2's historical convention. "
            "PCT_NATVEG in this file is the target's STATIC column and is NOT the "
            "denominator used; ELM's recovered harvest area therefore carries a factor "
            "natveg_static/natveg_annual."))

    # grid hard-check vs target
    gok = (np.array_equal(out_ds["LATIXY"].values, tds["LATIXY"].values)
           and np.array_equal(out_ds["LONGXY"].values, tds["LONGXY"].values)
           and out_ds.sizes["lsmlat"] == tds.sizes["lsmlat"]
           and out_ds.sizes["lsmlon"] == tds.sizes["lsmlon"])
    tds.close()
    print(f"  grid identical to target (LATIXY/LONGXY/dims): {gok}")
    print(f"  variables: {sorted(out_ds.data_vars)}")
    assert gok, "output grid does not match target"

    out = args.out or (OUTDIR / "processed" /
                       f"landuse.timeseries_SEUS_1_24deg_nlcd2elm_{args.scenario}_simyr2024-2100.nc")
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = {v: {"zlib": True, "complevel": 4}
           for v in out_ds.data_vars if out_ds[v].dtype.kind in "fi"}
    out_ds.to_netcdf(out, encoding=enc)
    print(f"[landuse.timeseries] wrote {out}  "
          f"({len(out_years)} yrs {int(out_years[0])}..{int(out_years[-1])})")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hist-start", type=int, default=ANCHOR + 1,
                    help="first output year (default %d = harmonized future only; NLCD "
                         "owns <=%d in its own file). Pass 1850 to prepend NLCD history."
                         % (ANCHOR + 1, ANCHOR))
    ap.add_argument("--scenario", default="SSP1_RCP19", choices=list(CHEN),
                    help="Chen SSP-RCP scenario (default SSP1_RCP19)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--build-timeseries", action="store_true",
                    help="build future landuse.timeseries on the target ELM grid "
                         "(stage A: PCT_NAT_PFT only, natveg=0 -> 100%% bare)")
    ap.add_argument("--anchor-file", type=Path, default=None,
                    help="target landuse.timeseries (anchor + grid); default TARGET_DEFAULT")
    ap.add_argument("--chen-targetgrid", type=Path, default=None,
                    help="Chen file on the target grid (01 --like <target>); default from scenario")
    args = ap.parse_args()
    if args.build_timeseries:
        return build_landuse_timeseries(args)
    ch_path = OUTDIR / "processed" / CHEN[args.scenario]
    print(f"scenario {args.scenario}  <-  {ch_path.name}")

    nl = xr.open_dataset(NL); ch = xr.open_dataset(ch_path)
    lat = nl.lat.values; lon = nl.lon.values
    assert np.allclose(lat, ch.lat.values) and np.allclose(lon, ch.lon.values)

    # --- SEUS crop indices ---
    jl = np.where((lat >= SEUS["lat0"]) & (lat <= SEUS["lat1"]))[0]
    il = np.where((lon >= SEUS["lon0"]) & (lon <= SEUS["lon1"]))[0]
    la0, la1, lo0, lo1 = jl[0], jl[-1] + 1, il[0], il[-1] + 1
    lat_s, lon_s = lat[la0:la1], lon[lo0:lo1]
    ny, nx = lat_s.size, lon_s.size
    area = cell_area_km2(lat_s, lon_s)
    print(f"SEUS grid {ny} x {nx}  lat {lat_s[0]:.2f}..{lat_s[-1]:.2f} "
          f"lon {lon_s[0]:.2f}..{lon_s[-1]:.2f}")

    nl_yrs = nl.time.dt.year.values
    ch_yrs = ch.time.values.astype(int)

    def nl_p(year):
        i = int(np.where(nl_yrs == year)[0][0])
        nv = np.nan_to_num(nl.PCT_NATVEG.isel(time=i).values[la0:la1, lo0:lo1].astype(np.float64))
        pf = np.nan_to_num(nl.PCT_NAT_PFT.isel(time=i).values[:, la0:la1, lo0:lo1].astype(np.float64))
        return nv, pf, pf * nv[None] / 100.0      # nv, pf, p(j)

    def ch_p(year):
        i = int(np.where(ch_yrs == year)[0][0])
        nv = np.nan_to_num(ch.PCT_NATVEG.isel(time=i).values[la0:la1, lo0:lo1].astype(np.float64))
        pf = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=i).values[:, la0:la1, lo0:lo1].astype(np.float64))
        return pf * nv[None] / 100.0

    # --- anchor: NLCD 2023 ---
    nv23, pf23, p_nl = nl_p(ANCHOR)                       # p_nl: (NPFT,ny,nx)
    seus_mask = nv23 > 0.0                                # cells with natveg at anchor

    # --- Chen native p(j), then linear-interp to annual on p(j) (§13.1/13.2) ---
    native = ch_yrs                                        # 2015,2020,2025..2100
    p_ch_native = np.stack([ch_p(int(y)) for y in native])  # (n_native,NPFT,ny,nx)
    annual = np.arange(ANCHOR, END + 1)                   # 2023..2100  (index 0 = anchor)
    p_ch = np.empty((annual.size, NPFT, ny, nx), dtype=np.float64)
    for k, y in enumerate(annual):
        if y <= native[0]:
            p_ch[k] = p_ch_native[0]
        elif y >= native[-1]:
            p_ch[k] = p_ch_native[-1]
        else:
            b = int(np.searchsorted(native, y, side="right"))   # native[b-1] <= y < native[b]
            w = (y - native[b - 1]) / (native[b] - native[b - 1])
            p_ch[k] = p_ch_native[b - 1] * (1 - w) + p_ch_native[b] * w

    # --- group totals ---
    P_nl_g = group_sum(p_nl)                              # (NG,ny,nx)
    P_ch_g = np.stack([group_sum(p_ch[k]) for k in range(annual.size)])  # (nyr,NG,ny,nx)

    # frozen within-group NLCD proportions (§13.6)
    P_nl_g_pft = P_nl_g[GRP_OF_PFT]                       # (NPFT,ny,nx)
    with np.errstate(invalid="ignore", divide="ignore"):
        w_frozen = np.where(P_nl_g_pft > 0, p_nl / P_nl_g_pft, 0.0)

    # --- march group totals annually (§13.5) ---
    nyr = annual.size
    P_harm_g = np.empty((nyr, NG, ny, nx), dtype=np.float64)
    P_harm_g[0] = P_nl_g                                  # anchor 2023 = NLCD
    for i in range(1, nyr):
        Ph, Cprev, Cnow = P_harm_g[i - 1], P_ch_g[i - 1], P_ch_g[i]
        dC = Cnow - Cprev
        Cprev_safe = np.where(Cprev > 0, Cprev, 1.0)
        out = np.where(Ph == 0, np.maximum(dC, 0.0),
                       np.where(Cprev <= Ph, Ph + dC, Ph * Cnow / Cprev_safe))
        P_harm_g[i] = np.maximum(out, 0.0)

    # --- re-split group totals to PFT (§13.6): frozen NLCD basis, Chen fallback where seeded ---
    def resplit(i):
        Pg_pft = P_harm_g[i][GRP_OF_PFT]                  # (NPFT,ny,nx)
        P_ch_g_pft = P_ch_g[i][GRP_OF_PFT]
        with np.errstate(invalid="ignore", divide="ignore"):
            w_ch = np.where(P_ch_g_pft > 0, p_ch[i] / P_ch_g_pft, 0.0)
        w = np.where(P_nl_g_pft > 0, w_frozen, w_ch)      # frozen where NLCD had group, else Chen split
        ph = Pg_pft * w
        ph[FORCE_ZERO] = 0.0                              # no boreal/tropical in SEUS
        return ph

    p_harm = np.stack([resplit(i) for i in range(nyr)])   # (nyr,NPFT,ny,nx), years 2023..2100

    # --- recover output variables (§13.7) ---
    def recover(ph):
        s = ph.sum(axis=0)                                # natveg as % of cell (pre-clip)
        natveg = np.clip(s, 0, 100)
        with np.errstate(invalid="ignore", divide="ignore"):
            pct = np.where(s > 0, 100.0 * ph / s[None], 0.0)
        return natveg.astype(np.float32), pct.astype(np.float32)

    # --- assemble output timeline ---
    hist_start = args.hist_start
    out_years = list(range(hist_start, END + 1))
    nat_out = np.zeros((len(out_years), ny, nx), dtype=np.float32)
    pft_out = np.zeros((len(out_years), NPFT, ny, nx), dtype=np.float32)
    for it, y in enumerate(out_years):
        if y <= ANCHOR:                                   # NLCD passthrough (exact), incl. anchor 2023
            nv, pf, _ = nl_p(y)
            nat_out[it] = nv.astype(np.float32)
            pf[FORCE_ZERO] = 0.0
            pft_out[it] = pf.astype(np.float32)
        else:                                             # harmonized future
            nat_out[it], pft_out[it] = recover(p_harm[y - ANCHOR])

    # ================= validation (§13.10) =================
    print("\n===== validation =====")
    # (1) sum-to-100 within natveg
    ss = pft_out.sum(axis=1)
    m100 = nat_out > 0
    dev = float(np.abs(ss[m100] - 100.0).max()) if m100.any() else 0.0
    print(f"  (1) max|PCT_NAT_PFT sum - 100| where natveg>0 : {dev:.4f}")
    # (2) natveg range
    print(f"  (2) PCT_NATVEG range : [{nat_out.min():.2f}, {nat_out.max():.2f}]")
    # (3) anchor identity: 2023 == NLCD 2023
    d_anchor = float(np.abs(P_harm_g[0] - P_nl_g).max())
    print(f"  (3) internal anchor P_harm_g[{ANCHOR}] == NLCD {ANCHOR} group totals : "
          f"max|diff| = {d_anchor:.2e}   (output starts {out_years[0]}; {ANCHOR} is NLCD's own file)")
    # (4) boreal/PFT6 zero
    fz = float(np.abs(pft_out[:, FORCE_ZERO, :, :]).max())
    print(f"  (4) boreal+PFT6 max value (should be 0) : {fz:.4f}")
    # (5) group sign check at 2100 vs Chen, where NLCD had the group
    i2100 = nyr - 1
    dHarm = P_harm_g[i2100] - P_harm_g[0]
    dChen = P_ch_g[i2100] - P_ch_g[0]
    print("  (5) group trend sign agreement (harm vs Chen), SEUS-natveg cells:")
    for gi, g in enumerate(GN):
        mm = seus_mask & (P_nl_g[gi] > 0)
        if mm.sum() == 0:
            continue
        agree = np.mean(np.sign(dHarm[gi][mm]) == np.sign(dChen[gi][mm])) * 100
        print(f"        {g:<6} sign-agree {agree:5.1f}%   "
              f"Δharm={np.average(dHarm[gi][mm], weights=area[mm]):+6.2f}  "
              f"Δchen={np.average(dChen[gi][mm], weights=area[mm]):+6.2f} (% of cell)")
    # (6) budget residual: annual Chen natveg change vs harmonized natveg change
    dP_ch_tot = (P_ch_g.sum(axis=1)[1:] - P_ch_g.sum(axis=1)[:-1])       # (nyr-1,ny,nx)
    dP_hm_tot = (P_harm_g.sum(axis=1)[1:] - P_harm_g.sum(axis=1)[:-1])
    resid = np.abs(dP_ch_tot - dP_hm_tot)[:, seus_mask]
    print(f"  (6) budget residual |Δchen-Δharm| per yr/cell : "
          f"mean {resid.mean():.4f}  p99 {np.percentile(resid,99):.3f}  max {resid.max():.3f} (% of cell)")
    # (7) interp reproduces native at native years
    err = 0.0
    for y in native:
        if ANCHOR <= y <= END:
            err = max(err, float(np.abs(p_ch[int(y) - ANCHOR] - p_ch_native[int(np.where(native==y)[0][0])]).max()))
    print(f"  (7) annual interp reproduces native years : max|diff| = {err:.6f}")

    # ================= write NetCDF =================
    out = args.out or (OUTDIR / "processed" /
                       f"harmonized_SEUS_{args.scenario}_{hist_start}-{END}_1_24deg.nc")
    out.parent.mkdir(parents=True, exist_ok=True)
    ds = xr.Dataset(
        data_vars=dict(
            PCT_NATVEG=(("time", "lat", "lon"), nat_out),
            PCT_NAT_PFT=(("time", "natpft", "lat", "lon"), pft_out),
        ),
        coords=dict(
            time=("time", np.array(out_years, dtype=np.int32)),
            natpft=("natpft", np.arange(NPFT, dtype=np.int32)),
            lat=("lat", lat_s.astype(np.float64)),
            lon=("lon", lon_s.astype(np.float64)),
        ),
    )
    ds["pft_name"] = (("natpft",), np.array([s.ljust(48) for s in ELM_PFT_NAMES], dtype="S48"))
    ds["lat"].attrs.update(units="degrees_north", long_name="latitude")
    ds["lon"].attrs.update(units="degrees_east", long_name="longitude")
    ds["time"].attrs.update(units="year", long_name="calendar year")
    for v in ("PCT_NATVEG", "PCT_NAT_PFT"):
        ds[v].attrs.update(units="%", valid_min=np.float32(0), valid_max=np.float32(100))
    ds["PCT_NAT_PFT"].attrs["long_name"] = "natural PFT cover within PCT_NATVEG (sums to 100)"
    ds.attrs.update(
        title="Harmonized SEUS land use: NLCD state + Chen2022 SSP1-RCP1.9 trend",
        method=("delta-harmonization; anchor=NLCD 2023; group-level Chen2022 eq.1 "
                "min-footprint marched annually; NLCD-frozen 2023 within-group re-split; "
                "Chen interpolated to annual on p(j); boreal/PFT6 forced 0"),
        base_file=str(NL), scenario_file=str(ch_path), scenario=args.scenario,
        seus_bbox=f"lon {SEUS['lon0']}..{SEUS['lon1']}, lat {SEUS['lat0']}..{SEUS['lat1']}",
        anchor_year=ANCHOR,
    )
    ds.to_netcdf(out)
    print(f"\nwrote {out}  ({len(out_years)} years {out_years[0]}..{out_years[-1]})")

    # diagnostics for follow-up plotting
    diag = OUTDIR / "interim" / f"harmonize_seus_diag_{args.scenario}.npz"
    np.savez_compressed(
        diag, years=np.array(out_years), annual=annual, lat=lat_s, lon=lon_s,
        area=area, seus_mask=seus_mask,
        Pnl_g=P_nl_g.astype(np.float32), Pch_g=P_ch_g.astype(np.float32),
        Pharm_g=P_harm_g.astype(np.float32), gnames=np.array(GN))
    print(f"wrote {diag}")
    nl.close(); ch.close()


if __name__ == "__main__":
    raise SystemExit(main())
