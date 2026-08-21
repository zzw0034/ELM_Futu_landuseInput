#!/usr/bin/env python
"""Prove a classic rebuild changed nothing but the two things it meant to.

This is the authoritative check for `to_classic_netcdf.py`. It requires

  * every value byte-for-byte identical, and
  * every structural difference to be one of exactly two intended changes:
    an `_FillValue` attribute dropped, or `time` becoming unlimited.

Anything else -- a changed `units`, a lost `long_name`, a different dimension
length, an extra or missing variable, a reordered variable -- fails.

`qa/check_format_equivalence.py` in SEUS_halfdeg runs alongside this and is the
independent second opinion, but two of its results need reading rather than
trusting:

  * It reports the `_FillValue` removal as a plain FAIL, having no notion of an
    intended change. That is the difference this script is here to whitelist.
  * Its value test is `np.array_equal`, which reports False for two arrays that
    are identical down to the bit whenever either holds a NaN, because NaN is
    not equal to itself. These files are documented as NaN-free (section 6),
    but that is exactly the sort of thing worth measuring rather than assuming,
    so the NaN count per variable is printed below and the comparison here is
    done on the raw bytes, where a NaN compares equal to its own copy.

The `string256` vs `nchar` character-dimension name is a known and retained
difference between the SSP files and the *historical* file. It is not a
difference between these two builds, so it does not appear here.

Usage:
    check_classic_rebuild.py --a <netcdf4 source> --b <classic rebuild>
"""

import argparse
import sys

import numpy as np
from netCDF4 import Dataset

EXPECTED_DROP = "_FillValue"
BLOCK_BYTES = 512 * 1024**2


def _bytes_equal(va, vb):
    """Byte-for-byte, so a NaN compares equal to its own copy."""
    return np.array_equal(np.ascontiguousarray(va).view(np.uint8),
                          np.ascontiguousarray(vb).view(np.uint8))


def _compare_values(a, b, time_dim, problems):
    # Raw values on both sides: with _FillValue = NaN, auto-masking would hand
    # back masked arrays and hide what is actually stored.
    a.set_auto_maskandscale(False)
    b.set_auto_maskandscale(False)
    tlen = len(a.dimensions[time_dim]) if time_dim in a.dimensions else 0

    for n in a.variables:
        va_all, vb_all = a.variables[n], b.variables[n]
        nan = 0
        if va_all.dimensions[:1] == (time_dim,) and tlen:
            per_record = int(np.prod(va_all.shape[1:], dtype=np.int64) or 1)
            step = max(1, min(tlen, BLOCK_BYTES //
                              max(1, per_record * va_all.dtype.itemsize)))
            ok = True
            for i0 in range(0, tlen, step):
                i1 = min(i0 + step, tlen)
                x, y = np.asarray(va_all[i0:i1]), np.asarray(vb_all[i0:i1])
                ok = ok and _bytes_equal(x, y)
                if x.dtype.kind in "fc":
                    nan += int(np.isnan(x).sum())
        else:
            x, y = np.asarray(va_all[:]), np.asarray(vb_all[:])
            ok = _bytes_equal(x, y)
            if x.dtype.kind in "fc":
                nan += int(np.isnan(x).sum())
        print(f"  {'ok ' if ok else 'DIFF'}  {n:<24s} NaN={nan}")
        if not ok:
            problems.append(f"{n}: values are not byte-identical")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--a", required=True, help="the NETCDF4 source")
    p.add_argument("--b", required=True, help="the classic rebuild")
    p.add_argument("--time-dim", default="time")
    args = p.parse_args()

    problems = []
    dropped = []
    with Dataset(args.a) as a, Dataset(args.b) as b:
        print(f"A: {args.a}\n   {a.file_format}")
        print(f"B: {args.b}\n   {b.file_format}\n")

        if a.file_format != "NETCDF4":
            problems.append(f"A is {a.file_format}, expected NETCDF4")
        if b.file_format != "NETCDF3_64BIT_OFFSET":
            problems.append(f"B is {b.file_format}, expected NETCDF3_64BIT_OFFSET")

        # Dimensions: same names, same order, same lengths. Only the record
        # flag on time may move, and only from fixed to unlimited.
        if list(a.dimensions) != list(b.dimensions):
            problems.append(f"dimension names/order differ: "
                            f"{list(a.dimensions)} vs {list(b.dimensions)}")
        else:
            for n in a.dimensions:
                da, db = a.dimensions[n], b.dimensions[n]
                if len(da) != len(db):
                    problems.append(f"dimension {n}: {len(da)} vs {len(db)}")
                if da.isunlimited() != db.isunlimited() and not (
                        n == args.time_dim
                        and not da.isunlimited() and db.isunlimited()):
                    problems.append(
                        f"dimension {n}: unlimited {da.isunlimited()} -> "
                        f"{db.isunlimited()}, not the intended change")
            if args.time_dim not in b.dimensions:
                problems.append(f"B has no {args.time_dim} dimension")
            elif not b.dimensions[args.time_dim].isunlimited():
                problems.append(f"{args.time_dim} is not unlimited in B")

        if list(a.variables) != list(b.variables):
            problems.append("variable names/order differ")
        else:
            for n in a.variables:
                va, vb = a.variables[n], b.variables[n]
                if va.dtype != vb.dtype:
                    problems.append(f"{n}: dtype {va.dtype} -> {vb.dtype}")
                if va.dimensions != vb.dimensions:
                    problems.append(f"{n}: dims {va.dimensions} -> {vb.dimensions}")
                aa = {k: str(va.getncattr(k)) for k in va.ncattrs()}
                ab = {k: str(vb.getncattr(k)) for k in vb.ncattrs()}
                gone = set(aa) - set(ab)
                if gone == {EXPECTED_DROP}:
                    dropped.append(n)
                    aa.pop(EXPECTED_DROP)
                elif gone:
                    problems.append(f"{n}: attributes lost {sorted(gone)}")
                    for k in gone:
                        aa.pop(k, None)
                added = set(ab) - set(aa)
                if added:
                    problems.append(f"{n}: attributes gained {sorted(added)}")
                for k in set(aa) & set(ab):
                    if aa[k] != ab[k]:
                        problems.append(f"{n}:{k} value differs")

        ga = {k: str(a.getncattr(k)) for k in a.ncattrs()}
        gb = {k: str(b.getncattr(k)) for k in b.ncattrs()}
        if ga != gb:
            names = sorted(set(ga) ^ set(gb))
            vals = sorted(k for k in set(ga) & set(gb) if ga[k] != gb[k])
            problems.append(f"global attributes differ: only-on-one-side={names}, "
                            f"values-differ={vals}")

        print(f"_FillValue dropped from {len(dropped)} variable(s): "
              f"{', '.join(dropped) if dropped else '(none)'}")
        print(f"{args.time_dim}: fixed -> unlimited\n")
        print("values (byte-for-byte)")
        _compare_values(a, b, args.time_dim, problems)

    print()
    if problems:
        print(f"{len(problems)} unintended difference(s):")
        for x in problems:
            print(f"  - {x}")
        return 1
    print("VERIFIED: values byte-identical; the only differences are the "
          "_FillValue removal and the unlimited time dimension")
    return 0


if __name__ == "__main__":
    sys.exit(main())
