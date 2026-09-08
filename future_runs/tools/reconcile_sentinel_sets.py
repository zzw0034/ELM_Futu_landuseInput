#!/usr/bin/env python
"""Reconcile the sentinel-cell sets, and chase the cells the first pass left over.

Three sets are in play and they were built by different routes, which is why
they have to be intersected rather than assumed equal:

  M  fine_bad_mask from SEUS_halfdeg/data/processed/contamination_masks_SEUS.nc
     (2026-08-21, job 468590): "a 4 km land cell assigned an all-sentinel met
     cell", derived from the met-cell assignment, not from model output.
  C  cells whose TBOT reaches the 323 K clamp in a 4 km run's history output.
     This is what the T1 investigation used, and it is a symptom, not a
     definition -- a cell could in principle clamp for another reason.
  S  cells whose matched zone_mappings row is raw-sentinel in all seven
     variables at one particular record.

C minus S was 12 cells and went unexplained. If those 12 are in M, the single
record was the limitation and nothing else is wrong. If they are not, there is
a second mechanism. This checks that instead of leaving it open, and scans a
window of records rather than one.

Read-only.
"""
import argparse, glob, sys
import netCDF4, numpy as np

METVARS = ["TBOT", "PSRF", "QBOT", "FSDS", "PRECTmms", "WIND", "FLDS"]
SENTINEL = {"TBOT": 22725, "PSRF": -23831, "QBOT": -14592, "FSDS": -30984,
            "PRECTmms": -32768, "WIND": -14600, "FLDS": 14924}

p = argparse.ArgumentParser()
p.add_argument("--h0", required=True)
p.add_argument("--mask", required=True)
p.add_argument("--zones", required=True)
p.add_argument("--metdir-fut", required=True)
p.add_argument("--metdir-hist", required=True)
p.add_argument("--rec-lo", type=int, default=2912)
p.add_argument("--rec-hi", type=int, default=2952)
a = p.parse_args()

d = netCDF4.Dataset(a.h0)
T = np.ma.filled(d.variables["TBOT"][:].astype("f8"), np.nan)
fin = np.isfinite(T)
C = (fin & (T >= 322.999)).any(axis=0)
active = fin.any(axis=0)
lat = np.asarray(d.variables["lat"][:], "f8"); lon = np.asarray(d.variables["lon"][:], "f8")
d.close()

m = netCDF4.Dataset(a.mask)
M = np.asarray(m.variables["fine_bad_mask"][:]) == 1
m.close()

print("== set sizes ==")
print("  M  fine_bad_mask (2026-08-21, job 468590) : %d" % int(M.sum()))
print("  C  TBOT reaches 323 K in T1 h0            : %d" % int(C.sum()))
print("  active land cells                         : %d" % int(active.sum()))
print()
print("== set algebra ==")
print("  M and C   : %d" % int((M & C).sum()))
print("  C not M   : %d" % int((C & ~M).sum()))
print("  M not C   : %d" % int((M & ~C).sum()))
print("  M == C    : %s" % bool(np.array_equal(M, C)))

# match every cell in C to its zone_mappings row
Z = np.loadtxt(a.zones)
zlon, zlat, zgrid = Z[:, 0], Z[:, 1], Z[:, 3].astype(int)
idx = np.argwhere(C)
rows = []
for i, j in idx:
    dd = (zlat - lat[i]) ** 2 + (zlon - lon[j]) ** 2
    rows.append(int(zgrid[int(np.argmin(dd))]))
rows = np.array(rows)

def sentinel_over_window(metdir, tag):
    """For each cell in C, is its matched row sentinel in all 7 vars, at any
    record in the window, and at every record in the window?"""
    allv_any = np.ones((len(rows), a.rec_hi - a.rec_lo), dtype=bool)
    found = {}
    for v in METVARS:
        cand = glob.glob("%s/*_%s_*.nc" % (metdir, v))
        if not cand:
            print("  [%s] %s: file not found" % (tag, v)); return None
        ds = netCDF4.Dataset(cand[0])
        var = ds.variables[v]; var.set_auto_maskandscale(False)
        blk = np.array([var[r - 1, a.rec_lo:a.rec_hi] for r in rows])
        ds.close()
        found[v] = (blk == SENTINEL[v])
        allv_any &= found[v]
    return allv_any, found

print()
print("== sentinel over record window [%d, %d) ==" % (a.rec_lo, a.rec_hi))
for tag, md in (("future ssp370", a.metdir_fut), ("historical", a.metdir_hist)):
    r = sentinel_over_window(md, tag)
    if r is None: continue
    allv, per = r
    always = allv.all(axis=1)
    ever = allv.any(axis=1)
    print("  [%s] all-7 sentinel at EVERY record in window : %d of %d"
          % (tag, int(always.sum()), len(rows)))
    print("  [%s] all-7 sentinel at ANY record in window   : %d of %d"
          % (tag, int(ever.sum()), len(rows)))
    inM = M[idx[:, 0], idx[:, 1]]
    print("  [%s] of the %d cells NOT all-sentinel anywhere: %d, of which in M: %d"
          % (tag, len(rows), int((~ever).sum()), int((~ever & inM).sum())))
    if (~ever).any():
        k = np.argwhere(~ever).ravel()[:12]
        print("  [%s] those cells (lat_i, lon_i, lat, lon, met_row, in_M):" % tag)
        for n in k:
            i, j = idx[n]
            print("      (%3d,%3d)  %.4f %.4f  row=%6d  inM=%s"
                  % (i, j, lat[i], lon[j], rows[n], bool(M[i, j])))
        # which variables ARE sentinel for them
        for v in METVARS:
            sub = per[v][k]
            print("      %-10s sentinel fraction over window: %s"
                  % (v, np.round(sub.mean(axis=1), 3).tolist()))
