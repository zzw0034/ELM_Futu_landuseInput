#!/usr/bin/env python
"""Rewrite a NETCDF4 landuse.timeseries into the classic ELM container.

The future SSP landuse.timeseries files were written by xarray's default
`to_netcdf`, which picks NETCDF4 as soon as any variable asks for `zlib`.
The historical file they sit beside is NETCDF3_64BIT_OFFSET. That mismatch is
not a live failure -- the `e3sm.exe` on Pathfinder links netCDF-C 4.9.2 with
`has-nc4=yes`, and lnd runs `pio_typename = "netcdf"`, so NETCDF4 reads fine
as configured. It is a trap for later: `libpnetcdf.so.4` is linked too, and
switching `PIO_TYPENAME` to `pnetcdf` for the 75,920-gridcell 4 km domain is
an obvious performance move that would make these inputs unreadable. Classic
is readable under every `PIO_TYPENAME`.

Three things move, and only these three:

  format       NETCDF4 + zlib level 4  ->  NETCDF3_64BIT_OFFSET
  time         fixed length            ->  unlimited (record dimension)
  _FillValue   NaN on 21 variables     ->  absent

The `_FillValue` attributes were added by xarray's default encoding, not by
the science; the historical file carries none. Everything else -- variable
set, order, dtypes, dimensions, other attributes, and every value -- is
copied through unchanged, and `qa/check_format_equivalence.py` is expected to
prove that bitwise.

Deliberately *not* using `nccopy -k nc6 -u`: it handles format and unlimited
but cannot drop `_FillValue`, so it would need a second `ncatted` pass. One
pass is easier to verify than two.

Two implementation details that matter:

  * Auto-masking is switched off on the source. With `_FillValue = NaN`,
    netCDF4-python would otherwise hand back masked arrays whose masked
    entries get rewritten as the destination's default fill value on output --
    a silent value change in exactly the variables this conversion claims not
    to touch.
  * Record variables are copied in blocks aligned to the *source's* HDF5
    chunking along time. `PCT_NAT_PFT` is chunked [20, 4, 81, 126]; reading it
    one record at a time makes each chunk decompress up to 80 times over
    (measured: 331 s vs 15 s for the same file).

Usage:
    to_classic_netcdf.py --src <netcdf4 file> --dst <classic file>
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

# Cap on how much of one variable is held in memory at once. Blocks are always
# a whole number of source chunks, so this is a target, not a hard bound: a
# single chunk larger than the cap is still read whole.
BLOCK_BYTES = 512 * 1024**2


def _time_block(sv, tlen):
    """Records per copy step: source chunk length along time, scaled up toward
    BLOCK_BYTES so small variables are not copied in needless pieces."""
    chunking = sv.chunking()
    chunk = chunking[0] if isinstance(chunking, list) else tlen
    chunk = max(1, min(chunk, tlen))
    per_record = int(np.prod(sv.shape[1:], dtype=np.int64)) * sv.dtype.itemsize
    mult = max(1, BLOCK_BYTES // max(1, chunk * per_record))
    return int(min(tlen, chunk * mult))


def convert(src, dst, time_dim="time"):
    with Dataset(src) as s, Dataset(dst, "w", format="NETCDF3_64BIT_OFFSET") as d:
        # Raw values, no masking, no scaling -- see module docstring.
        s.set_auto_maskandscale(False)

        print(f"src {src}\n    format {s.file_format}")
        for name, dim in s.dimensions.items():
            d.createDimension(name, None if name == time_dim else len(dim))
        print(f"    dimensions: {', '.join(s.dimensions)}  ({time_dim} -> unlimited)")

        # Define every variable and attribute, including the global ones,
        # before writing any data. Growing a classic file's header after data
        # exists forces the library to shift the whole data section.
        dropped = []
        for name, sv in s.variables.items():
            dv = d.createVariable(name, sv.dtype, sv.dimensions)  # no fill_value
            for a in sv.ncattrs():
                if a == "_FillValue":
                    dropped.append(name)
                    continue
                dv.setncattr(a, sv.getncattr(a))
        for a in s.ncattrs():
            d.setncattr(a, s.getncattr(a))
        print(f"    dropped _FillValue from {len(dropped)} variable(s): "
              f"{', '.join(dropped)}")

        tlen = len(s.dimensions[time_dim])
        for name, sv in s.variables.items():
            dv = d.variables[name]
            if sv.dimensions[:1] == (time_dim,):
                step = _time_block(sv, tlen)
                for i0 in range(0, tlen, step):
                    i1 = min(i0 + step, tlen)
                    dv[i0:i1] = sv[i0:i1]
                print(f"    {name}: {tlen} records in blocks of {step}")
            else:
                dv[:] = sv[:]
                print(f"    {name}: copied whole")

    with Dataset(dst) as d:
        print(f"dst {dst}\n    format {d.file_format}, "
              f"{time_dim} unlimited={d.dimensions[time_dim].isunlimited()}, "
              f"{len(d.variables)} variables")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--src", required=True, help="NETCDF4 input")
    p.add_argument("--dst", required=True, help="classic output (must not exist)")
    p.add_argument("--time-dim", default="time",
                   help="dimension to make unlimited (default: time)")
    args = p.parse_args()

    if Path(args.dst).exists():
        print(f"FATAL: {args.dst} already exists; refusing to overwrite")
        return 1
    convert(args.src, args.dst, args.time_dim)
    return 0


if __name__ == "__main__":
    sys.exit(main())
