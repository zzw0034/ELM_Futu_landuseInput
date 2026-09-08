#!/usr/bin/env python
"""Investigate the ELM land cells whose cpl_bypass meteorology is the sentinel.

T1 and the completed historical production run both clamp TBOT to 323 K and
PBOT to 40000 Pa at the same 194 active land cells. 0.26% of cells is not by
itself an argument that the science is unaffected, so this answers the
questions that decide whether it is:

  1. where they are, in degrees, and what fraction of LAND AREA they carry
     (a cell count is not an area share)
  2. whether they sit on the coast, on islands, or on the domain edge
  3. which of the seven met variables are sentinel there, per cell
  4. why the reader hands them an invalid point
  5. what they contribute to domain carbon flux

On (4) the mechanism is not in doubt and the code is quoted rather than
guessed at. lnd_import_export.F90 matches every ELM gridcell to the nearest
zone_mappings row by plain Euclidean distance in degrees:

    do g3 = 1,ng
      thisdist = 100*((latixy(g3) - ldomain%latc(g))**2 + &
                      (longxy(g3) - ldomain%lonc(g))**2)**0.5
      if (thisdist .lt. mindist) then
        mindist = thisdist ; ztoget = zone_map(g3) ; gtoget = grid_map(g3)

There is no test that the matched point carries data. zone_mappings spans the
full met rectangle including ocean, and ocean rows hold each variable's
sentinel, so a land cell whose nearest met point is ocean silently receives it.
This script measures how far each of these cells is from its match and whether
a valid point existed nearby, which is what separates "grid offset" from
"genuinely no data".

Read-only. Usage:
    investigate_sentinel_cells.py --h0 <T1 h0> --prod-h0 <production h0>
                                 --surfdata <surfdata.nc> --zones <zone_mappings.txt>
                                 --metdir <cpl_bypass future_clim/sspXXX>
                                 [--json out.json]
"""
import argparse
import json
import sys

import netCDF4
import numpy as np

# raw packed sentinel per variable, from the historical files (see
# tessfa2_future_climate_cpl_bypass_patch notes); order is the reader's
# metvars order for metsource 6.
METVARS = ["TBOT", "PSRF", "QBOT", "FSDS", "PRECTmms", "WIND", "FLDS"]
SENTINEL = {"TBOT": 22725, "PSRF": -23831, "QBOT": -14592, "FSDS": -30984,
            "PRECTmms": -32768, "WIND": -14600, "FLDS": 14924}
FILEVAR = {"TBOT": "TBOT", "PSRF": "PSRF", "QBOT": "QBOT", "FSDS": "FSDS",
           "PRECTmms": "PRECTmms", "WIND": "WIND", "FLDS": "FLDS"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--h0", required=True, help="T1 h0 (hourly, has TBOT/PBOT)")
    p.add_argument("--prod-h0", help="production historical h0 for flux impact")
    p.add_argument("--surfdata", required=True)
    p.add_argument("--zones", required=True)
    p.add_argument("--metdir", required=True)
    p.add_argument("--domain", required=True,
                   help="the case's domain.nc -- xc/yc are what the reader matches on")
    p.add_argument("--json")
    a = p.parse_args()

    d = netCDF4.Dataset(a.h0)
    T = np.ma.filled(d.variables["TBOT"][:].astype("f8"), np.nan)
    fin = np.isfinite(T)
    hot = fin & (T >= 322.999)
    cellhot = hot.any(axis=0)                     # (lat, lon)
    idx = np.argwhere(cellhot)
    lat = np.asarray(d.variables["lat"][:], dtype="f8")
    lon = np.asarray(d.variables["lon"][:], dtype="f8")
    active = fin.any(axis=0)
    d.close()

    print("== 1. how many, and where ==")
    print("  active land cells in output : %d" % int(active.sum()))
    print("  sentinel-fed cells          : %d  (%.4f%% by count)"
          % (len(idx), 100.0 * len(idx) / max(int(active.sum()), 1)))

    la = lat[idx[:, 0]]
    lo = lon[idx[:, 1]]
    print("  lat range %.4f .. %.4f     lon range %.4f .. %.4f"
          % (la.min(), la.max(), lo.min(), lo.max()))

    # ---- area weighting ----
    s = netCDF4.Dataset(a.surfdata)
    AREA = np.ma.filled(s.variables["AREA"][:].astype("f8"), np.nan)
    LFRAC = np.ma.filled(s.variables["LANDFRAC_PFT"][:].astype("f8"), np.nan)
    s.close()
    w = AREA * LFRAC
    w = np.where(np.isfinite(w), w, 0.0)
    tot_area = w[active].sum()
    hot_area = w[cellhot].sum()
    print("\n== 2. area weight, not cell count ==")
    print("  total land area (AREA*LANDFRAC) over active cells : %.6g km2" % tot_area)
    print("  same over sentinel-fed cells                      : %.6g km2" % hot_area)
    print("  AREA-WEIGHTED SHARE                               : %.4f%%"
          % (100.0 * hot_area / max(tot_area, 1e-30)))
    lf = LFRAC[cellhot]
    print("  their LANDFRAC_PFT: min %.4f  median %.4f  max %.4f  (<0.5: %d of %d)"
          % (np.nanmin(lf), np.nanmedian(lf), np.nanmax(lf),
             int((lf < 0.5).sum()), len(lf)))

    # ---- edge / coast character ----
    print("\n== 3. coast, island, or domain edge ==")
    nlat, nlon = active.shape
    di = np.minimum(idx[:, 0], nlat - 1 - idx[:, 0])
    dj = np.minimum(idx[:, 1], nlon - 1 - idx[:, 1])
    edge = np.minimum(di, dj)
    print("  distance to nearest domain edge, in cells:")
    for k in [0, 1, 2, 5, 10]:
        print("     <= %-3d : %d" % (k, int((edge <= k).sum())))
    # neighbours that are inactive => coastline
    pad = np.pad(active, 1, constant_values=False)
    nb = np.zeros(len(idx), dtype=int)
    for n, (i, j) in enumerate(idx):
        win = pad[i:i + 3, j:j + 3]
        nb[n] = 9 - int(win.sum())      # inactive neighbours incl. self-window
    print("  inactive cells in the 3x3 neighbourhood: min %d median %d max %d"
          % (nb.min(), int(np.median(nb)), nb.max()))
    print("  fully interior (0 inactive neighbours): %d of %d"
          % (int((nb == 0).sum()), len(nb)))

    # ---- nearest-neighbour match against zone_mappings ----
    print("\n== 4. what the reader matches them to ==")
    # Match on the DOMAIN file's xc/yc, which is what ldomain%lonc/latc holds
    # and therefore what the Fortran compares against. Using the history file's
    # lat/lon coordinate arrays instead put 12 of the 194 on the wrong met row
    # and produced a spurious "12 cells unexplained" (2026-09-08). It also
    # produced a spurious uniform half-diagonal match distance and an apparent
    # four-way tie at every cell; with xc/yc there are no ties at all.
    dm = netCDF4.Dataset(a.domain)
    xc = np.asarray(dm.variables["xc"][:], dtype="f8")
    yc = np.asarray(dm.variables["yc"][:], dtype="f8")
    dm.close()

    Z = np.loadtxt(a.zones)
    zlon, zlat, zzone, zgrid = Z[:, 0], Z[:, 1], Z[:, 2].astype(int), Z[:, 3].astype(int)
    print("  zone_mappings rows: %d   lon %.3f..%.3f   lat %.3f..%.3f"
          % (len(Z), zlon.min(), zlon.max(), zlat.min(), zlat.max()))
    print("  matching on domain.nc xc/yc (NOT the history file's lat/lon)")

    rows, dists, ties = [], [], []
    for i, j in idx:
        dd = (zlat - yc[i, j]) ** 2 + (zlon - xc[i, j]) ** 2
        k = int(np.argmin(dd))
        rows.append(zgrid[k])
        dists.append(float(np.sqrt(dd[k])))
        ties.append(int((dd == dd[k]).sum()))
    ties = np.array(ties)
    print("  tie multiplicity: min %d median %d max %d ; cells with a tie: %d of %d"
          % (ties.min(), int(np.median(ties)), ties.max(),
             int((ties > 1).sum()), len(ties)))
    rows = np.array(rows)
    dists = np.array(dists)
    print("  match distance (deg): min %.5f median %.5f max %.5f"
          % (dists.min(), np.median(dists), dists.max()))
    print("  matched met rows: %d distinct of %d cells" % (len(set(rows.tolist())), len(rows)))

    # Is that distance particular to these cells, or does every cell sit the
    # same way relative to the met grid? If it is uniform the two grids are
    # simply offset, and the 194 are the cells where that offset happens to
    # cross a land/ocean boundary.
    ai, aj = np.nonzero(active)
    sub = np.arange(0, len(ai), max(1, len(ai) // 4000))
    dall = []
    for i, j in zip(ai[sub], aj[sub]):
        dd = (zlat - lat[i]) ** 2 + (zlon - lon[j]) ** 2
        dall.append(float(np.sqrt(dd.min())))
    dall = np.array(dall)
    dlat = float(np.median(np.diff(np.unique(zlat))))
    dlon = float(np.median(np.diff(np.unique(zlon))))
    print("  met grid spacing: dlat %.6f dlon %.6f ; half-diagonal %.6f"
          % (dlat, dlon, 0.5 * np.hypot(dlat, dlon)))
    print("  match distance over %d sampled ACTIVE cells: min %.5f median %.5f max %.5f"
          % (len(dall), dall.min(), np.median(dall), dall.max()))

    # ---- which variables are sentinel at those rows ----
    print("\n== 5. which of the seven variables are sentinel there ==")
    order = np.argsort(rows)
    rsorted = rows[order]
    persent = {}
    for v in METVARS:
        import glob
        cand = glob.glob("%s/*_%s_*.nc" % (a.metdir, FILEVAR[v]))
        if not cand:
            print("  %-10s file not found in %s" % (v, a.metdir))
            continue
        ds = netCDF4.Dataset(cand[0])
        var = ds.variables[FILEVAR[v]]
        # netCDF4 applies scale_factor/add_offset automatically. The sentinels
        # are RAW packed shorts, so the comparison has to be made before that
        # transform or it is guaranteed false -- which is exactly how an earlier
        # version of this script reported "sentinel at 0 of 194" while the
        # decoded samples plainly contained the decoded sentinel.
        var.set_auto_maskandscale(False)
        scale = float(ds.variables[FILEVAR[v]].scale_factor)
        offset = float(ds.variables[FILEVAR[v]].add_offset)
        vals = np.array([int(var[int(r) - 1, 2920]) for r in rsorted])
        ds.close()
        issent = vals == SENTINEL[v]
        persent[v] = issent
        dec_sent = SENTINEL[v] * scale + offset
        print("  %-10s sentinel(raw %7d -> decoded %12.5g) at %3d of %d rows (%5.1f%%)"
              % (v, SENTINEL[v], dec_sent, int(issent.sum()), len(vals),
                 100.0 * issent.mean()))
        print("             distinct raw values at those rows: %s"
              % np.unique(vals)[:6].tolist())

    if persent:
        allsent = np.ones(len(rsorted), dtype=bool)
        anysent = np.zeros(len(rsorted), dtype=bool)
        for v in persent:
            allsent &= persent[v]
            anysent |= persent[v]
        print("  ALL seven sentinel : %d cells" % int(allsent.sum()))
        print("  ANY sentinel       : %d cells" % int(anysent.sum()))

    # ---- flux impact ----
    if a.prod_h0:
        print("\n== 6. contribution to domain carbon flux (production historical h0) ==")
        ph = netCDF4.Dataset(a.prod_h0)
        for name in ["GPP", "NEE", "TOTVEGC", "TLAI"]:
            if name not in ph.variables:
                continue
            X = np.ma.filled(ph.variables[name][:].astype("f8"), np.nan)
            Xm = np.nanmean(X, axis=0)                     # time mean per cell
            wa = np.where(np.isfinite(Xm) & active, w, 0.0)
            tot = np.nansum(np.where(np.isfinite(Xm), Xm, 0.0) * wa)
            hotv = np.nansum(np.where(np.isfinite(Xm) & cellhot, Xm, 0.0) * wa)
            print("  %-8s area-weighted domain total %.6g ; sentinel cells %.6g ; share %.4f%%"
                  % (name, tot, hotv, 100.0 * hotv / max(abs(tot), 1e-30)))
            hv = Xm[cellhot]
            hv = hv[np.isfinite(hv)]
            av = Xm[active & ~cellhot]
            av = av[np.isfinite(av)]
            if hv.size and av.size:
                print("            sentinel-cell mean %.6g vs rest-of-domain mean %.6g"
                      % (hv.mean(), av.mean()))
        ph.close()

    if a.json:
        out = dict(n_cells=int(len(idx)),
                   lat=la.tolist(), lon=lo.tolist(),
                   lat_i=idx[:, 0].tolist(), lon_i=idx[:, 1].tolist(),
                   met_row=rows.tolist(), match_deg=dists.tolist(),
                   area_share_pct=float(100.0 * hot_area / max(tot_area, 1e-30)))
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1)
        print("\nwrote %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
