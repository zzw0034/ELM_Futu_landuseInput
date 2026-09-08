#!/usr/bin/env python
"""Scientific sanity check of an ELM restart, and its diff against a predecessor.

Written for the A3 restart: the 2024-01-01 state re-run with the A+B cpl_bypass
fixes, which is the initial condition all seven 4km future scenarios will start
from. "It completed" and "220 of 464 variables changed" are not acceptance.

Three things a naive check gets wrong here, all handled explicitly:

1. Fill values. 462 of the 464 variables carry _FillValue = 1e36. Computing a
   range without masking returns 1e36 for nearly everything and hides real
   outliers. Every statistic below is over valid points only, and the valid
   count is reported so a variable that is entirely fill cannot masquerade as
   a clean pass.

2. NaN vs fill. A fill point is expected; a NaN or Inf at a *valid* point is a
   defect. They are counted separately and only the latter fails.

3. Sign conventions. Pools that are physically non-negative are checked for
   negatives at a tolerance, rather than assuming any negative is fatal --
   ELM's BGC carries small negative round-off in some pools by design.

Usage:
    check_a3_restart.py --new NEW.nc [--old OLD.nc] [--json out.json]
                        [--top 40] [--rel-eps 1e-12]

Exit status: 0 if no valid-point NaN/Inf and no non-negativity violation
beyond tolerance; 1 otherwise.
"""
import argparse
import json
import sys

import netCDF4
import numpy as np

FILL_CUTOFF = 1e35  # anything at or above this is ELM's 1e36 fill

# Pools that must not go meaningfully negative. Prefix match, case-insensitive.
NONNEG_PREFIXES = (
    "h2osoi_liq", "h2osoi_ice", "h2osno", "h2ocan", "snow_depth",
    "leafc", "frootc", "livestemc", "deadstemc", "livecrootc", "deadcrootc",
    "totlitc", "cwdc", "soil1c", "soil2c", "soil3c", "soil4c",
    "litr1c", "litr2c", "litr3c",
    "leafn", "frootn", "sminn", "solutionp", "labilep", "secondp", "occlp", "primp",
)

# Physical bounds for a spotlight set; (lo, hi) in the file's own units.
SPOTLIGHT = {
    "T_SOISNO": (150.0, 400.0),
    "T_GRND": (150.0, 400.0),
    "T_VEG": (150.0, 400.0),
    "T_LAKE": (150.0, 400.0),
    "H2OSOI_LIQ": (-1e-6, 1e5),
    "H2OSOI_ICE": (-1e-6, 1e5),
    "H2OSNO": (-1e-6, 1e5),
    "ZWT": (-10.0, 200.0),
    "WA": (-1e5, 1e5),
    "leafc": (-1e-3, 1e5),
    "deadstemc": (-1e-3, 1e7),
    "totlitc": (-1e-3, 1e6),
    "cwdc_vr": (-1e-3, 1e6),
    "soil1c_vr": (-1e-3, 1e6),
    "soil4c_vr": (-1e-3, 1e7),
    "sminn_vr": (-1e-3, 1e5),
    "solutionp_vr": (-1e-3, 1e5),
}


def load(ds, name):
    """Return (values_as_f8, valid_mask). Valid = not fill, not masked."""
    v = ds.variables[name]
    a = v[:]
    if np.ma.isMaskedArray(a):
        masked = np.ma.getmaskarray(a)
        a = np.ma.filled(a.astype("f8"), np.nan)
    else:
        a = np.asarray(a, dtype="f8")
        masked = np.zeros(a.shape, dtype=bool)
    valid = ~masked & ~(np.abs(a) >= FILL_CUTOFF)
    return a, valid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--new", required=True)
    p.add_argument("--old")
    p.add_argument("--json")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--rel-eps", type=float, default=0.0,
                   help="relative difference below this counts as unchanged")
    a = p.parse_args()

    dn = netCDF4.Dataset(a.new)
    do = netCDF4.Dataset(a.old) if a.old else None

    rows, problems, changed = [], [], []
    n_novalid = 0

    names = [n for n in sorted(dn.variables)
             if dn.variables[n].dtype.kind in "fiu"]
    print("restart: %s" % a.new.split("/")[-1])
    if do:
        print("against: %s" % a.old.split("/")[-1])
    print("numeric variables: %d of %d\n" % (len(names), len(dn.variables)))

    for name in names:
        A, va = load(dn, name)
        nvalid = int(va.sum())
        if nvalid == 0:
            n_novalid += 1
            rows.append(dict(name=name, nvalid=0))
            continue
        vals = A[va]
        nnan = int(np.isnan(vals).sum())
        ninf = int(np.isinf(vals).sum())
        fin = vals[np.isfinite(vals)]
        lo = float(fin.min()) if fin.size else float("nan")
        hi = float(fin.max()) if fin.size else float("nan")
        mean = float(fin.mean()) if fin.size else float("nan")

        r = dict(name=name, nvalid=nvalid, ntot=int(A.size),
                 nan=nnan, inf=ninf, min=lo, max=hi, mean=mean)

        if nnan or ninf:
            problems.append("%-24s NaN=%d Inf=%d at valid points" % (name, nnan, ninf))

        lname = name.lower()
        if any(lname.startswith(px) for px in NONNEG_PREFIXES) and fin.size:
            neg = fin[fin < 0]
            if neg.size:
                worst = float(neg.min())
                r["min_negative"] = worst
                r["n_negative"] = int(neg.size)
                # tolerance: 1e-9 of the variable's own scale
                scale = max(abs(hi), 1.0)
                if abs(worst) > 1e-9 * scale:
                    problems.append(
                        "%-24s %d negative values, min %.6g (scale %.6g)"
                        % (name, neg.size, worst, scale))

        if name in SPOTLIGHT and fin.size:
            blo, bhi = SPOTLIGHT[name]
            if lo < blo or hi > bhi:
                problems.append("%-24s range [%.6g, %.6g] outside [%.6g, %.6g]"
                                % (name, lo, hi, blo, bhi))

        if do is not None and name in do.variables:
            B, vb = load(do, name)
            if A.shape == B.shape:
                both = va & vb
                if both.any():
                    d = np.abs(A[both] - B[both])
                    d = np.where(np.isnan(d), np.inf, d)
                    sc = np.maximum(np.abs(A[both]), np.abs(B[both]))
                    sc = np.where((sc == 0) | ~np.isfinite(sc), 1.0, sc)
                    rel = d / sc
                    nd = int((rel > a.rel_eps).sum()) if a.rel_eps > 0 else int((d > 0).sum())
                    r["ndiff"] = nd
                    r["maxabs"] = float(d.max())
                    r["maxrel"] = float(rel.max())
                    r["fracdiff"] = nd / both.sum()
                    if nd:
                        changed.append(r)
            else:
                r["shape_mismatch"] = True

        rows.append(r)

    print("== valid-point NaN / Inf and sign checks ==")
    if problems:
        for s in problems:
            print("  FAIL  " + s)
    else:
        print("  none -- no NaN/Inf at valid points, no out-of-range spotlight,")
        print("  no non-negativity violation beyond 1e-9 of scale")
    if n_novalid:
        print("  note: %d variable(s) have zero valid points (all fill)" % n_novalid)

    print("\n== spotlight ranges (valid points only) ==")
    print("%-16s %10s %14s %14s %14s" % ("variable", "nvalid", "min", "max", "mean"))
    for name in SPOTLIGHT:
        r = next((x for x in rows if x["name"] == name), None)
        if r and r.get("nvalid"):
            print("%-16s %10d %14.6g %14.6g %14.6g"
                  % (name, r["nvalid"], r["min"], r["max"], r["mean"]))

    if do is not None:
        tot = sum(1 for r in rows if "ndiff" in r)
        print("\n== difference against predecessor ==")
        print("compared: %d   changed: %d   unchanged: %d"
              % (tot, len(changed), tot - len(changed)))
        changed.sort(key=lambda r: -r["maxrel"])
        print("\n%-24s %10s %10s %14s %14s" %
              ("variable", "n diff", "frac", "max|A-B|", "max rel"))
        for r in changed[:a.top]:
            print("%-24s %10d %10.4f %14.6g %14.6g"
                  % (r["name"], r["ndiff"], r["fracdiff"], r["maxabs"], r["maxrel"]))
        if len(changed) > a.top:
            print("... %d more changed variables" % (len(changed) - a.top))

        big = [r for r in changed if r["maxrel"] > 0.5]
        print("\nchanged with max relative difference > 0.5: %d" % len(big))
        for r in big[:20]:
            print("   %-24s frac=%.4f maxrel=%.4g range新=[%.4g, %.4g]"
                  % (r["name"], r["fracdiff"], r["maxrel"], r["min"], r["max"]))

    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)
        print("\nwrote %s" % a.json)

    dn.close()
    if do:
        do.close()
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
