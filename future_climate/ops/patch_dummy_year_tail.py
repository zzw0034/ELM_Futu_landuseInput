#!/usr/bin/env python
"""Patch the dummy (2023) pad year's LAST record in an already-built future
CPL_BYPASS forcing file, in place, without regenerating the file.

Background: the cpl_bypass reader's day-boundary interpolation for a
2024-01-01 cold start reads exactly one dummy-year record -- DTIME index
DUMMY_YEAR_LEN-1 (0-indexed), the dummy year's very last record -- blended
with the real first record of 2024. Left at the ocean/invalid sentinel, that
blend pulls the run's first few integration steps' TBOT/PBOT/QBOT/FLDS toward
an unphysical value. See auto-memory tessfa2-dummy-year-tail-interpolation-fix
for the independent tindex-formula derivation that pins this down to exactly
one record (not "the last day or two" as originally scoped).

This script overwrites that one record with a verbatim copy of the real first
record (DTIME index DUMMY_YEAR_LEN). No land/ocean mask is read or needed:
every ocean/invalid cell already carries the same sentinel in the REAL data
too (that's how the build scripts construct it), so copying the real record
onto the dummy record leaves ocean cells unchanged and only changes land
cells -- self-masking, by construction of the source files.

Both the 4 km source files (build_cpl_bypass_tessfa2.py) and the 0.5 deg
aggregated files (build_future_forcing_0p5deg.py / build_future_flds_0p5deg.py)
use the same DUMMY_YEAR_LEN=2920 and the same (n, DTIME) layout, so one script
covers both resolutions -- pass the file path directly, this script does not
need to know which pipeline produced it.

usage:
  patch_dummy_year_tail.py --file /path/to/DBCCA_..._z01.nc --var TBOT
  patch_dummy_year_tail.py --file ... --var TBOT --dry-run   # report only
"""
from __future__ import annotations

import argparse
import time

import netCDF4 as nc
import numpy as np

DUMMY_YEAR_LEN = 2920
LAST_DUMMY_RECORD = DUMMY_YEAR_LEN - 1     # 0-indexed: 2919
FIRST_REAL_RECORD = DUMMY_YEAR_LEN         # 0-indexed: 2920


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="path to the *_z01.nc file to patch")
    ap.add_argument("--var", required=True,
                    choices=["TBOT", "PSRF", "QBOT", "FSDS", "PRECTmms", "WIND", "FLDS"])
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()

    mode = "r" if args.dry_run else "r+"
    t0 = time.time()
    with nc.Dataset(args.file, mode) as ds:
        v = ds.variables[args.var]
        v.set_auto_maskandscale(False)
        n, dtime = v.shape
        if dtime != 78 * DUMMY_YEAR_LEN:
            raise SystemExit(f"{args.file}: expected DTIME={78 * DUMMY_YEAR_LEN}, "
                             f"got {dtime} -- not a 1-dummy-year-plus-77-real-years "
                             f"future forcing file, refusing to touch it")

        before = np.asarray(v[:, LAST_DUMMY_RECORD])
        real_first = np.asarray(v[:, FIRST_REAL_RECORD])
        n_changed = int((before != real_first).sum())
        print(f"[{args.var}] {args.file}")
        print(f"  n={n:,} cells; dummy-year last record (index {LAST_DUMMY_RECORD}) "
              f"currently differs from real first record (index {FIRST_REAL_RECORD}) "
              f"at {n_changed:,} cells (expected land cells)")

        if args.dry_run:
            print("  --dry-run: nothing written")
            return

        v[:, LAST_DUMMY_RECORD] = real_first

    # Reopen read-only to verify the write actually landed, independent of
    # any in-process buffering.
    with nc.Dataset(args.file, "r") as ds:
        v = ds.variables[args.var]
        v.set_auto_maskandscale(False)
        after = np.asarray(v[:, LAST_DUMMY_RECORD])
        real_first_check = np.asarray(v[:, FIRST_REAL_RECORD])
        if not np.array_equal(after, real_first_check):
            raise SystemExit(f"VERIFICATION FAILED for {args.file}: dummy-year last "
                             f"record does not match real first record after write")
        n_still_diff_from_before = int((after != before).sum())
        print(f"  verified on disk: dummy-year last record now equals real first "
              f"record at every cell; {n_still_diff_from_before:,} cells changed "
              f"({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
