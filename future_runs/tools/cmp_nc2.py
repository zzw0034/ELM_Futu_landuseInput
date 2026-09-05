#!/usr/bin/env python
"""Compare two NetCDF files: numeric data, non-numeric data, and metadata.

Written for restart/history consistency tests, where three different kinds of
difference must be told apart and none may be waved away:

  DATA     numeric variables, compared elementwise
  TEXT     char/string variables, compared exactly (cmp_nc.py skipped these)
  META     global and per-variable attributes (the usual reason two files have
           the same data and different checksums -- but that has to be shown,
           not assumed)

Record alignment
---------------
A history file written by the first year of a job can carry a different number
of time records than the same year written mid-run.  Refusing to compare (or
reporting a bare SHAPE mismatch) hides whether the overlapping records agree.
So when the leading dimension is the record dimension and the two files
disagree on its length, the records are aligned on their own time coordinate
(mcdate+mcsec, else time) and the intersection is compared, with the dropped
records named explicitly.

Usage:
    cmp_nc2.py A.nc B.nc [--rtol 0] [--max-report 40] [--quiet-attrs]

Exit status: 0 if DATA and TEXT are equal on the compared records, 1 otherwise.
META differences alone do not change the exit status; they are always printed.
"""
import argparse
import sys

import netCDF4
import numpy as np


def _fmt(v):
    s = repr(v)
    return s if len(s) <= 90 else s[:87] + "..."


def record_keys(ds):
    """Per-record identity: (mcdate, mcsec) if present, else time, else None."""
    v = ds.variables
    if "mcdate" in v and "mcsec" in v:
        return [("mcdate/mcsec", int(a), int(b))
                for a, b in zip(np.ravel(v["mcdate"][:]), np.ravel(v["mcsec"][:]))]
    if "time" in v:
        return [("time", float(t), 0) for t in np.ravel(v["time"][:])]
    return None


def align(da, db, name):
    """Return (idx_a, idx_b, note) aligning the record dimension, or None."""
    ka, kb = record_keys(da), record_keys(db)
    if ka is None or kb is None:
        return None
    ia = {k: i for i, k in enumerate(ka)}
    ib = {k: i for i, k in enumerate(kb)}
    common = [k for k in ka if k in ib]
    if not common:
        return None
    only_a = [k for k in ka if k not in ib]
    only_b = [k for k in kb if k not in ia]
    note = "aligned on %s: %d common record(s)" % (common[0][0], len(common))
    if only_a:
        note += "; only in A: %s" % [k[1:] for k in only_a]
    if only_b:
        note += "; only in B: %s" % [k[1:] for k in only_b]
    return [ia[k] for k in common], [ib[k] for k in common], note


def attr_diff(a_obj, b_obj, where, out):
    na = {k: a_obj.getncattr(k) for k in a_obj.ncattrs()}
    nb = {k: b_obj.getncattr(k) for k in b_obj.ncattrs()}
    for k in sorted(set(na) | set(nb)):
        if k not in nb:
            out.append((where, k, _fmt(na[k]), "<absent>"))
        elif k not in na:
            out.append((where, k, "<absent>", _fmt(nb[k])))
        else:
            va, vb = na[k], nb[k]
            same = np.array_equal(va, vb) if isinstance(va, np.ndarray) else va == vb
            if not same:
                out.append((where, k, _fmt(va), _fmt(vb)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--rtol", type=float, default=0.0,
                   help="relative tolerance; default 0 = require exact equality")
    p.add_argument("--max-report", type=int, default=40)
    p.add_argument("--quiet-attrs", action="store_true",
                   help="count attribute differences but do not list them")
    args = p.parse_args()

    da, db = netCDF4.Dataset(args.a), netCDF4.Dataset(args.b)
    va, vb = set(da.variables), set(db.variables)
    common = sorted(va & vb)

    print("A: %s" % args.a)
    print("B: %s" % args.b)
    print("variables: A=%d B=%d common=%d" % (len(va), len(vb), len(common)))
    for label, s in (("ONLY IN A", sorted(va - vb)), ("ONLY IN B", sorted(vb - va))):
        if s:
            print("  %s (%d): %s" % (label, len(s), s[:20]))

    unlim = [d for d, o in da.dimensions.items() if o.isunlimited()]
    rec_dim = unlim[0] if unlim else None

    data_same, data_diff, text_same, text_diff, notes = [], [], [], [], []

    for name in common:
        xa, xb = da.variables[name], db.variables[name]

        # --- TEXT ---
        if xa.dtype.kind in "SU" or xb.dtype.kind in "SU":
            A, B = xa[:], xb[:]
            try:
                eq = np.array_equal(np.asarray(A), np.asarray(B))
            except Exception:
                eq = False
            (text_same if eq else text_diff).append(name)
            continue

        if xa.dtype.kind not in "fiub" or xb.dtype.kind not in "fiub":
            text_diff.append(name + " (uncomparable dtype %s/%s)" % (xa.dtype, xb.dtype))
            continue

        # --- DATA ---
        A = np.ma.filled(xa[:], np.nan).astype("f8")
        B = np.ma.filled(xb[:], np.nan).astype("f8")

        if A.shape != B.shape:
            if rec_dim and xa.dimensions and xa.dimensions[0] == rec_dim:
                al = align(da, db, name)
                if al is None:
                    data_diff.append((name, float("inf"), float("inf"), -1,
                                      "SHAPE %s vs %s, no time coord to align on"
                                      % (A.shape, B.shape)))
                    continue
                ia, ib, note = al
                if note not in notes:
                    notes.append(note)
                A, B = A[ia], B[ib]
            else:
                data_diff.append((name, float("inf"), float("inf"), -1,
                                  "SHAPE %s vs %s" % (A.shape, B.shape)))
                continue

        both_nan = np.isnan(A) & np.isnan(B)
        with np.errstate(invalid="ignore"):
            d = np.where(both_nan, 0.0, np.abs(A - B))
        d = np.where(np.isnan(d), np.inf, d)
        scale = np.where(both_nan, 1.0, np.maximum(np.abs(A), np.abs(B)))
        scale = np.where((scale == 0) | np.isnan(scale), 1.0, scale)
        rel = d / scale
        bad = rel > args.rtol if args.rtol > 0 else d > 0
        n = int(np.count_nonzero(bad))
        if n == 0:
            data_same.append(name)
        else:
            data_diff.append((name, float(d.max()), float(rel.max()), n, ""))

    # --- META ---
    attrs = []
    attr_diff(da, db, "<global>", attrs)
    for name in common:
        attr_diff(da.variables[name], db.variables[name], name, attrs)

    if notes:
        print()
        for nte in notes:
            print("RECORD ALIGNMENT: %s" % nte)

    print()
    print("DATA  equal : %d   differing : %d" % (len(data_same), len(data_diff)))
    print("TEXT  equal : %d   differing : %d" % (len(text_same), len(text_diff)))
    print("META  differing attributes : %d" % len(attrs))

    if data_diff:
        print()
        print("%-30s %14s %12s %12s  %s"
              % ("variable", "max|A-B|", "max rel", "n differing", "note"))
        for name, mx, rl, n, note in sorted(data_diff, key=lambda t: -t[1])[:args.max_report]:
            print("%-30s %14.6g %12.4g %12d  %s" % (name, mx, rl, n, note))

    if text_diff:
        print()
        print("TEXT differing: %s" % text_diff[:args.max_report])

    if attrs and not args.quiet_attrs:
        print()
        print("%-28s %-24s %-40s %s" % ("where", "attribute", "A", "B"))
        for where, k, x, y in attrs[:args.max_report]:
            print("%-28s %-24s %-40s %s" % (where[:28], k[:24], x[:40], y[:60]))
        if len(attrs) > args.max_report:
            print("... %d more" % (len(attrs) - args.max_report))

    ok = not data_diff and not text_diff
    print()
    print("VERDICT: DATA+TEXT %s%s"
          % ("EQUAL" if ok else "NOT equal",
             "; META differs in %d attribute(s)" % len(attrs) if attrs else "; META identical"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
