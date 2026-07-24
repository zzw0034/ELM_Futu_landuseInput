"""ELM_LandUse: Build ELM surface data inputs from Chen 2022 1 km PFT dataset.

Submodules:
- chen_classes : Chen 2022 -> ELM PFT mapping
- raster_io    : helpers for locating and reading Chen 2022 GeoTIFFs
- aggregate    : area-weighted aggregation onto a target lat/lon grid

Usage:
    from elm_landuse.chen_classes import CHEN_CLASSES, ELM_PFT_NAMES, NPFT
    from elm_landuse.raster_io import find_tif, read_window_for_bbox
    from elm_landuse.aggregate import TargetGrid, aggregate_class_fractions
"""

__version__ = "0.1.0"
