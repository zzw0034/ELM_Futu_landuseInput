"""Class definitions and Chen2022 -> ELM PFT mapping.

Chen et al. (2022) global 1 km PFT-based land projection has 20 categorical
classes (see ../readme.txt). ELM/CLM expects:

  - PCT_NATVEG, PCT_CROP, PCT_URBAN, PCT_LAKE, PCT_GLACIER, PCT_WETLAND
    (percent of grid cell, summing to 100)
  - PCT_NAT_PFT(natpft, lat, lon) within the natural-vegetation column
    (percent of natveg, summing to 100, 17 PFTs by default for ELM)

This module encodes the Chen2022 -> ELM mapping used downstream.
"""

from __future__ import annotations

from dataclasses import dataclass


CHEN_CLASS_NAMES: dict[int, str] = {
    1: "Water",
    2: "Broadleaf evergreen tree, tropical",
    3: "Broadleaf evergreen tree, temperate",
    4: "Broadleaf deciduous tree, tropical",
    5: "Broadleaf deciduous tree, temperate",
    6: "Broadleaf deciduous tree, boreal",
    7: "Needleleaf evergreen tree, temperate",
    8: "Needleleaf evergreen tree, boreal",
    9: "Needleleaf deciduous tree",
    10: "Broadleaf evergreen shrub, temperate",
    11: "Broadleaf deciduous shrub, temperate",
    12: "Broadleaf deciduous shrub, boreal",
    13: "C3 grass, arctic",
    14: "C3 grass",
    15: "C4 grass",
    16: "Mixed C3/C4 grass",
    17: "Barren",
    18: "Cropland",
    19: "Urban",
    20: "Permanent snow and ice",
}

CHEN_CLASSES: tuple[int, ...] = tuple(CHEN_CLASS_NAMES.keys())


# ELM / CLM5 standard 17 natural PFTs (index = position in PCT_PFT)
# fmt: off
ELM_PFT_NAMES: tuple[str, ...] = (
    "Bare_Ground",                          # 0
    "needleleaf_evergreen_temperate_tree",  # 1
    "needleleaf_evergreen_boreal_tree",     # 2
    "needleleaf_deciduous_boreal_tree",     # 3
    "broadleaf_evergreen_tropical_tree",    # 4
    "broadleaf_evergreen_temperate_tree",   # 5
    "broadleaf_deciduous_tropical_tree",    # 6
    "broadleaf_deciduous_temperate_tree",   # 7
    "broadleaf_deciduous_boreal_tree",      # 8
    "broadleaf_evergreen_shrub",            # 9
    "broadleaf_deciduous_temperate_shrub",  # 10
    "broadleaf_deciduous_boreal_shrub",     # 11
    "c3_arctic_grass",                      # 12
    "c3_non-arctic_grass",                  # 13
    "c4_grass",                             # 14
    "crop",                                 # 15
    "irrigated_crop",                       # 16 placeholder empty value for irrigated crop
)
# fmt: on
NPFT: int = len(ELM_PFT_NAMES)  # 17


# Special (non-natveg) ELM column categories
SPECIAL_CATEGORIES: tuple[str, ...] = (
    "PCT_LAKE",
    "PCT_URBAN",
    "PCT_GLACIER",
    "PCT_CROP",
)


@dataclass(frozen=True)
class ChenMap:
    """How a single Chen class is distributed onto ELM categories.

    `pft_weights[i]` is the fraction (0..1) of this Chen class that should
    contribute to natveg PFT index `i`. `special` is a special-column name
    (e.g. "PCT_LAKE") to which 100% of this class is sent instead.

    Exactly one of (pft_weights nonzero) or (special set) is used.
    """

    special: str | None = None
    pft_weights: tuple[float, ...] = tuple(0.0 for _ in range(NPFT))


def _pft(idx: int, weight: float = 1.0) -> tuple[float, ...]:
    w = [0.0] * NPFT
    w[idx] = weight
    return tuple(w)


def _pft_split(idx_w: dict[int, float]) -> tuple[float, ...]:
    w = [0.0] * NPFT
    for i, v in idx_w.items():
        w[i] = v
    return tuple(w)


CHEN_TO_ELM: dict[int, ChenMap] = {
    1: ChenMap(special="PCT_LAKE"),
    2: ChenMap(pft_weights=_pft(4)),  # broadleaf evergreen tropical tree
    3: ChenMap(pft_weights=_pft(5)),  # broadleaf evergreen temperate tree
    4: ChenMap(pft_weights=_pft(6)),  # broadleaf deciduous tropical tree
    5: ChenMap(pft_weights=_pft(7)),  # broadleaf deciduous temperate tree
    6: ChenMap(pft_weights=_pft(8)),  # broadleaf deciduous boreal tree
    7: ChenMap(pft_weights=_pft(1)),  # needleleaf evergreen temperate tree
    8: ChenMap(pft_weights=_pft(2)),  # needleleaf evergreen boreal tree
    9: ChenMap(
        pft_weights=_pft(3)
    ),  # 3-needleleaf deciduous boreal tree but 9:Needleleaf deciduous tree
    # if assign all 9:Needleleaf deciduous tree to 3-needleleaf deciduous boreal tree,
    # SEUS will have 3-needleleaf deciduous boreal tree, which is not correct.
    # solution：SEUS assgin 9:Needleleaf deciduous tree to 1  needleleaf evergreen temperate tree
    10: ChenMap(pft_weights=_pft(9)),  # broadleaf evergreen shrub
    11: ChenMap(pft_weights=_pft(10)),  # broadleaf deciduous temperate shrub
    12: ChenMap(pft_weights=_pft(11)),  # broadleaf deciduous boreal shrub
    13: ChenMap(pft_weights=_pft(12)),  # C3 arctic grass
    14: ChenMap(pft_weights=_pft(13)),  # C3 grass
    15: ChenMap(pft_weights=_pft(14)),  # C4 grass
    16: ChenMap(pft_weights=_pft_split({13: 0.5, 14: 0.5})),  # Mixed C3/C4
    17: ChenMap(pft_weights=_pft(0)),  # bare ground
    # Cropland is mapped to ELM natural PFT 15 (crop) instead of the
    # separate PCT_CROP column, so cropland is carried inside PCT_NATVEG /
    # PCT_NAT_PFT and PCT_CROP stays 0 everywhere. This is a common
    # simplification for runs that do not use the ELM crop submodel.
    18: ChenMap(pft_weights=_pft(15)),  # Cropland -> crop PFT
    19: ChenMap(special="PCT_URBAN"),
    20: ChenMap(special="PCT_GLACIER"),
}


def class_groups() -> dict[str, list[int]]:
    """Group Chen classes by ELM destination column for diagnostics."""
    groups: dict[str, list[int]] = {
        "PCT_LAKE": [],
        "PCT_URBAN": [],
        "PCT_GLACIER": [],
        "PCT_CROP": [],
        "PCT_NATVEG": [],
    }
    for c, m in CHEN_TO_ELM.items():
        if m.special:
            groups[m.special].append(c)
        else:
            groups["PCT_NATVEG"].append(c)
    return groups


__all__ = [
    "CHEN_CLASS_NAMES",
    "CHEN_CLASSES",
    "ELM_PFT_NAMES",
    "NPFT",
    "SPECIAL_CATEGORIES",
    "ChenMap",
    "CHEN_TO_ELM",
    "class_groups",
]
