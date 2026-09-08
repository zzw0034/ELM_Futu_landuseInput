#!/usr/bin/env python
"""Rewrite seq_infodata_case_name inside a cpl.r restart, preserving padding.

The driver checks this field against the running case and aborts with
"(seq_infodata_Check) : invalid continue restart case name" if it disagrees.
Renaming the file is not enough -- the name is stored in the data.

The field is fixed-width (256 characters here), so the replacement is padded to
exactly the original length. Writing a shorter string would leave the tail of
the previous name in place and produce a name that is neither.
"""
import sys
import netCDF4
import numpy as np

if len(sys.argv) != 3:
    sys.exit("usage: rewrite_cplr_casename.py <cpl.r.nc> <new_case_name>")
path, new = sys.argv[1], sys.argv[2]

d = netCDF4.Dataset(path, "a")
var = None
for name in d.variables:
    if name == "seq_infodata_case_name":
        var = d.variables[name]
        break
if var is None:
    d.close()
    sys.exit("seq_infodata_case_name not found in %s" % path)

old = b"".join(np.atleast_1d(var[:]).ravel()).decode("utf-8", "replace")
width = len(old)
if len(new) > width:
    d.close()
    sys.exit("new case name (%d chars) longer than the field (%d)" % (len(new), width))

padded = new.ljust(width)
var[:] = np.array(list(padded.encode("utf-8")), dtype="S1")
d.close()

chk = netCDF4.Dataset(path)
got = b"".join(np.atleast_1d(chk.variables["seq_infodata_case_name"][:]).ravel()).decode("utf-8", "replace")
chk.close()
print("old: %r" % old.strip())
print("new: %r" % got.strip())
print("width preserved: %s" % (len(got) == width))
if got.strip() != new:
    sys.exit("readback mismatch")
