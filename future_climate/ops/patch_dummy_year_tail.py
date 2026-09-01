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

**Idempotent and safe to retry.** The write only ever sets DTIME index
LAST_DUMMY_RECORD to a value read from DTIME index FIRST_REAL_RECORD, which
this script never modifies -- so an interrupted run (leaving some rows
patched and others not) is fully recovered by simply running the script
again; it converges to the same final state regardless of how many times it
is interrupted or re-run. There is no NetCDF3 transactional protection
against a crash mid-write, but there is nothing for a retry to get wrong.

**Before running this against a canonical/production file**: confirm no
Slurm job is currently reading it (`squeue -u $USER`, check for a running
future case pointing `metdata_bypass` at this file's directory) -- this
script does not check that for you.

**Build-record staleness**: patching changes the file's sha256, which no
longer matches any pre-existing `data/intermediate/future_forcing_<ssp>_
<var>_build.json` produced by the original build script. This script does
NOT touch that file (preserves the original build provenance); instead, with
--record-dir, it writes a SEPARATE `<tag>_<scenario>_<basename>.patch_
record.json` alongside it (see record_stem() -- basename alone collides
across scenarios AND across the three known locations, since every
scenario's file for a given var shares the exact same basename) recording
old/new sha256 (opt-in via --sha256, since a full 96GB 4 km file hash is a
meaningful chunk of wall time -- expect several minutes on /projects NFS),
changed-cell count, timestamp, and this script's git commit.

usage:
  patch_dummy_year_tail.py --file /path/to/DBCCA_..._z01.nc --var TBOT
  patch_dummy_year_tail.py --file ... --var TBOT --dry-run       # report only
  patch_dummy_year_tail.py --file ... --var TBOT --sha256 \\
      --record-dir /path/to/patch_records/                      # + audit trail
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time

import netCDF4 as nc
import numpy as np

DUMMY_YEAR_LEN = 2920
LAST_DUMMY_RECORD = DUMMY_YEAR_LEN - 1     # 0-indexed: 2919
FIRST_REAL_RECORD = DUMMY_YEAR_LEN         # 0-indexed: 2920

# The three known locations this fix touches -- mapped to a short tag for
# the patch-record filename. All three scenarios' files share the exact
# same basename (DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc), so basename
# alone collides across scenarios AND across these three locations; a record
# filename built from basename alone silently overwrites a previous record.
KNOWN_ROOTS = {
    "/scratch/hpcl-cli185/zw5/future_clim": "scratch",
    "/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
    "Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim": "worldshared",
    "/projects/hpcl-cli185/proj-shared/zw5/SEUS_halfdeg/data/processed/"
    "cpl_bypass_0p5deg_future": "halfdeg0p5",
}


def record_stem(file_path):
    """A patch-record filename stem that stays unique across scenario AND
    location. Recognizes the three known future-forcing roots (tags each
    with a short name, prefixes the scenario -- the file's parent directory
    name) and falls back to the full sanitized path for anything else,
    so an unrecognized location still gets a collision-free name rather
    than silently colliding on basename."""
    p = os.path.abspath(file_path)
    for root, tag in KNOWN_ROOTS.items():
        if p.startswith(root + "/"):
            scenario = os.path.basename(os.path.dirname(p))
            return f"{tag}_{scenario}_{os.path.basename(p)}"
    return p.strip("/").replace("/", "_")


def sha256_of(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit_of(script_path):
    try:
        here = os.path.dirname(os.path.abspath(script_path))
        return subprocess.check_output(
            ["git", "-C", here, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="path to the *_z01.nc file to patch")
    ap.add_argument("--var", required=True,
                    choices=["TBOT", "PSRF", "QBOT", "FSDS", "PRECTmms", "WIND", "FLDS"])
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change, write nothing")
    ap.add_argument("--sha256", action="store_true",
                    help="compute whole-file sha256 before and after (slow on "
                         "large 4km files -- several minutes each on /projects NFS)")
    ap.add_argument("--record-dir", default=None,
                    help="write a patch record JSON here, named by record_stem() -- "
                         "location tag + scenario + basename, collision-free across "
                         "scenarios and locations (requires --sha256 for old/new "
                         "sha256 fields to be populated; without it, the record still "
                         "captures changed-cell count and timestamp)")
    args = ap.parse_args()

    t0 = time.time()
    sha_before = sha256_of(args.file) if args.sha256 else None
    if sha_before:
        print(f"  sha256 before: {sha_before}  ({time.time() - t0:.0f}s)", flush=True)

    mode = "r" if args.dry_run else "r+"
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

    sha_after = sha256_of(args.file) if args.sha256 else None
    if sha_after:
        print(f"  sha256 after:  {sha_after}  ({time.time() - t0:.0f}s total)", flush=True)

    if args.record_dir:
        os.makedirs(args.record_dir, exist_ok=True)
        record = dict(
            file=args.file, var=args.var,
            sha256_before=sha_before, sha256_after=sha_after,
            n_cells_total=n, n_cells_changed=n_still_diff_from_before,
            last_dummy_record=LAST_DUMMY_RECORD, first_real_record=FIRST_REAL_RECORD,
            patched_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            patch_script_commit=git_commit_of(__file__),
            slurm_job_id=os.environ.get("SLURM_JOB_ID", "none"),
        )
        rp = os.path.join(args.record_dir, f"{record_stem(args.file)}.patch_record.json")
        with open(rp, "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
        print(f"  patch record: {rp}")


if __name__ == "__main__":
    main()
