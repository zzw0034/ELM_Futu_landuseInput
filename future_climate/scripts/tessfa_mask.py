"""Shared TESSFA2 valid-cell mask for the cpl_bypass historical forcing.

The historical cpl_bypass files do NOT use NaN for cells outside the land
mask. They are int16 with scale_factor/add_offset, and invalid cells carry an
int sentinel that decodes to a perfectly finite number:

    TBOT      raw 22725  -> 396.001 K     (real values run ~250-300 K)
    PRECTmms  raw -32768 -> -0.088 mm/s   (real values are >= 0)

So np.isfinite does not filter them and they walk straight into a domain mean
-- which is what produced 67 degC and negative precipitation on the first run.

The future CanESM5 files DO use NaN, over exactly the same cells: both records
have 117964 valid cells of 225625 and the two masks are elementwise equal
(verified against clmforc.4km.TPQWL.2024-01.nc). Masking the historical side
therefore makes the two domain means cover the same area.

`n` is the flattened grid, lat-fastest: n = ilon*361 + ilat, so
mask.reshape(625, 361).T gives the (lat, lon) layout the future files use.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

HIST = Path("/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/"
            "Daymet_ERA5_TESSFA2/cpl_bypass_full")
STEM = "Daymet_ERA5_TESSFA.4km_%s_1980-2023_z01.nc"

TBOT_FILL_ABOVE = 350.0     # real TBOT never approaches this; sentinel is 396.001
NLAT, NLON = 361, 625
NCELL = NLAT * NLON
NVALID_EXPECTED = 117964    # cross-checked against the future files' NaN mask


def valid_cell_mask(check_steps=(0, 64239, 128479)) -> np.ndarray:
    """-> (n,) bool, True where the cell carries real data.

    Derived from TBOT rather than a domain file so it cannot drift out of sync
    with the forcing itself. Verified time-invariant over `check_steps`.
    """
    ds = xr.open_dataset(HIST / (STEM % "TBOT"), decode_times=False)
    m = None
    for t in check_steps:
        v = ds.TBOT.isel(DTIME=t).values
        mt = v < TBOT_FILL_ABOVE
        if m is None:
            m = mt
        elif not np.array_equal(m, mt):
            raise AssertionError(f"land mask differs at DTIME={t}: "
                                 f"{int((m != mt).sum())} cells")
    ds.close()
    n = int(m.sum())
    if n != NVALID_EXPECTED:
        raise AssertionError(f"valid cells {n} != expected {NVALID_EXPECTED}")
    return m


def assert_physical(var: str, a: np.ndarray) -> None:
    """Catch any sentinel that slipped through the mask."""
    if a.size == 0:
        return
    lo, hi = float(np.nanmin(a)), float(np.nanmax(a))
    if var == "TBOT" and not (200.0 < lo and hi < 340.0):
        raise AssertionError(f"TBOT out of physical range after masking: {lo}..{hi}")
    if var == "PRECTmms" and not (lo >= -1e-12 and hi < 0.05):
        raise AssertionError(f"PRECTmms out of physical range after masking: {lo}..{hi}")
