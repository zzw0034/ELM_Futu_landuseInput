"""Common land-cover legend for comparing NLCD (30 m) with Chen2022 (1 km).

The two products use different classifications and different resolutions, so a
direct class-to-class comparison is impossible. This module defines a coarse
legend that both can be crosswalked into without inventing information, plus
the two lookup tables.

Design notes
------------
* Both source rasters are on **equal-area** projections (NLCD: Albers Conical
  Equal Area; Chen2022: EASE-Grid 2.0 / WGS84 Cylindrical Equal Area), so the
  area of a class is exactly ``pixel_count * pixel_area``. Neither product has
  to be resampled to compute the statistics -- each is counted natively.
* The legend is deliberately coarse. Chen2022 splits trees/shrubs/grass by
  leaf habit and climate zone (things NLCD does not record), while NLCD splits
  developed land by intensity and separates pasture from cultivated crops
  (things Chen2022 does not record). Only the coarse groupings survive both.

Known asymmetries -- these are real, not bugs, and drive most of the numbers:

* **WETLAND**: NLCD has classes 90/95; Chen2022 has *no wetland class at all*.
  Chen must place that land somewhere else (forest/grass/water), so a nonzero
  NLCD wetland area with zero Chen wetland area is expected by construction.
* **CROPLAND**: NLCD separates 81 (Pasture/Hay) from 82 (Cultivated Crops);
  Chen2022 has a single undivided "Cropland". Whether NLCD pasture belongs in
  Chen's cropland or in its grass classes is genuinely ambiguous, so we do not
  hard-code the choice: 81 and 82 map to distinct common classes (PASTURE and
  CROPLAND) and the comparison script reports both the strict (82-only) and
  the inclusive (81+82) reading. See `NLCD_AGRI_CLASSES`.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Common legend
# ---------------------------------------------------------------------------
# Code 255 is reserved for "no data / not mapped".

COMMON_NODATA: int = 255

COMMON_CLASSES: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)

COMMON_NAMES: dict[int, str] = {
    0: "Water",
    1: "Snow/Ice",
    2: "Developed",
    3: "Barren",
    4: "Forest",
    5: "Shrub",
    6: "Grass",
    7: "Pasture/Hay",
    8: "Cropland",
    9: "Wetland",
}

# Colors follow the NLCD convention where a counterpart exists, so the two
# maps are readable side by side.
COMMON_COLORS: dict[int, str] = {
    0: "#466b9f",  # water        (NLCD 11)
    1: "#d1def8",  # snow/ice     (NLCD 12)
    2: "#ab0000",  # developed    (NLCD 24)
    3: "#b3ac9f",  # barren       (NLCD 31)
    4: "#1c5f2c",  # forest       (NLCD 42)
    5: "#ccb879",  # shrub        (NLCD 52)
    6: "#dfdfc2",  # grass        (NLCD 71)
    7: "#dcd939",  # pasture/hay  (NLCD 81)
    8: "#ab6c28",  # cropland     (NLCD 82)
    9: "#b8d9eb",  # wetland      (NLCD 90)
}

# The two defensible readings of "cropland" when comparing against Chen2022's
# single undivided Cropland class (see module docstring).
NLCD_AGRI_STRICT: tuple[int, ...] = (8,)  # cultivated crops only
NLCD_AGRI_INCLUSIVE: tuple[int, ...] = (7, 8)  # + pasture/hay


# ---------------------------------------------------------------------------
# NLCD -> common
# ---------------------------------------------------------------------------
# Annual NLCD Land Cover (CONUS) legend. 30 m, Albers, nodata = 250.
NLCD_CLASS_NAMES: dict[int, str] = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land (Rock/Sand/Clay)",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    52: "Shrub/Scrub",
    71: "Herbaceous",
    81: "Hay/Pasture",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands",
}

NLCD_TO_COMMON: dict[int, int] = {
    11: 0,  # Open Water            -> Water
    12: 1,  # Perennial Ice/Snow    -> Snow/Ice
    21: 2,  # Developed, Open Space -> Developed
    22: 2,
    23: 2,
    24: 2,
    31: 3,  # Barren Land           -> Barren
    41: 4,  # Deciduous Forest      -> Forest
    42: 4,  # Evergreen Forest      -> Forest
    43: 4,  # Mixed Forest          -> Forest
    52: 5,  # Shrub/Scrub           -> Shrub
    71: 6,  # Herbaceous            -> Grass
    81: 7,  # Hay/Pasture           -> Pasture/Hay
    82: 8,  # Cultivated Crops      -> Cropland
    90: 9,  # Woody Wetlands        -> Wetland
    95: 9,  # Emergent Herb Wetland -> Wetland
}

NLCD_NODATA: int = 250
NLCD_PIXEL_AREA_M2: float = 30.0 * 30.0


# ---------------------------------------------------------------------------
# Chen2022 -> common
# ---------------------------------------------------------------------------
# 20 classes, see data/external/chen2022_1km/readme.txt. int8, nodata = -128.
CHEN_TO_COMMON: dict[int, int] = {
    1: 0,  # Water                              -> Water
    2: 4,  # Broadleaf evergreen tree, tropical -> Forest
    3: 4,  # Broadleaf evergreen tree, temperate
    4: 4,  # Broadleaf deciduous tree, tropical
    5: 4,  # Broadleaf deciduous tree, temperate
    6: 4,  # Broadleaf deciduous tree, boreal
    7: 4,  # Needleleaf evergreen tree, temperate
    8: 4,  # Needleleaf evergreen tree, boreal
    9: 4,  # Needleleaf deciduous tree
    10: 5,  # Broadleaf evergreen shrub, temperate -> Shrub
    11: 5,  # Broadleaf deciduous shrub, temperate
    12: 5,  # Broadleaf deciduous shrub, boreal
    13: 6,  # C3 grass, arctic                  -> Grass
    14: 6,  # C3 grass
    15: 6,  # C4 grass
    16: 6,  # Mixed C3/C4 grass
    17: 3,  # Barren                            -> Barren
    18: 8,  # Cropland                          -> Cropland
    19: 2,  # Urban                             -> Developed
    20: 1,  # Permanent snow and ice            -> Snow/Ice
}
# Chen2022 has no wetland class and no pasture/hay class: common codes 9 and 7
# are unreachable from Chen. That absence is a headline result, not an error.

CHEN_NODATA: int = -128
CHEN_PIXEL_AREA_M2: float = 1000.0 * 1000.0


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------
def nlcd_lut() -> np.ndarray:
    """256-entry uint8 LUT: NLCD byte value -> common code (255 = nodata).

    Indexing this with the raw raster maps a whole block in one vectorized op.
    Values not in the NLCD legend (including nodata 250) land on COMMON_NODATA.
    """
    lut = np.full(256, COMMON_NODATA, dtype=np.uint8)
    for src, dst in NLCD_TO_COMMON.items():
        lut[src] = dst
    return lut


def chen_lut() -> np.ndarray:
    """256-entry uint8 LUT indexed by the *unsigned view* of Chen's int8 data.

    Chen rasters are int8 with nodata -128. Viewing the block as uint8 makes
    every value a valid index into a 256-entry table (negative values wrap to
    128..255), which keeps the mapping branch-free. Valid classes are 1..20 and
    are unaffected by the wrap.
    """
    lut = np.full(256, COMMON_NODATA, dtype=np.uint8)
    for src, dst in CHEN_TO_COMMON.items():
        if not 0 <= src <= 127:
            raise ValueError(f"Chen class {src} outside int8 positive range")
        lut[src] = dst
    return lut
