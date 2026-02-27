# coding: utf-8
"""
Coordinate conversion for MOJ cadastral data.

MOJ XML files use Japan Plane Rectangular coordinate systems (JGD2000,
EPSG 2443-2461). We convert them to WGS84 (EPSG:4326) for storage and display.

JGD2011 and WGS84 differ by less than 1 m in Japan, so for cadastral display
purposes converting JGD2000 → WGS84 is accurate enough.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping

# Ensure pyproj can find its datum grids.  The caller (batch.py) typically
# sets PROJ_DATA before importing this module; we fall back to the geo env.
if "PROJ_DATA" not in os.environ:
    _GEO_ENV = Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo"))
    os.environ["PROJ_DATA"] = str(_GEO_ENV / "share" / "proj")


@lru_cache(maxsize=32)
def _transformer(from_epsg: int) -> Transformer:
    """Return a cached pyproj Transformer from a plane rect EPSG → WGS84."""
    return Transformer.from_crs(from_epsg, 4326, always_xy=True)


def project_ring(
    coords: list[list[float]], from_epsg: int
) -> list[tuple[float, float]]:
    """
    Reproject a ring from Japan Plane Rectangular to WGS84 (lon, lat).

    In MOJ XML, zmn:X is the NORTHING and zmn:Y is the EASTING — the opposite
    of the usual GIS convention.  pyproj with always_xy=True expects
    (easting, northing), so we pass (xy[1], xy[0]).
    """
    tr = _transformer(from_epsg)
    result = []
    for xy in coords:
        lon, lat = tr.transform(xy[1], xy[0])   # xy[1]=zmn:Y=easting, xy[0]=zmn:X=northing
        result.append((round(lon, 8), round(lat, 8)))
    return result


def build_polygon(exterior: list, interior: list[list], from_epsg: int) -> Polygon:
    """Build a shapely Polygon from MOJ plane rectangular coordinates."""
    ext_wgs = project_ring(exterior, from_epsg)
    int_wgs = [project_ring(ring, from_epsg) for ring in interior]
    return Polygon(ext_wgs, int_wgs)


def feature_to_geojson(feature: dict) -> dict | None:
    """
    Convert a parsed parcel feature to a GeoJSON Feature dict.

    Returns None if the feature uses an arbitrary coordinate system and
    therefore cannot be placed on a geographic map.
    """
    epsg = feature.get("epsg")
    if epsg is None:
        return None

    try:
        poly = build_polygon(feature["exterior"], feature["interior"], epsg)
        if not poly.is_valid:
            poly = poly.buffer(0)  # attempt to fix invalid geometry
        if poly.is_empty:
            return None
        geom = mapping(MultiPolygon([poly]) if not isinstance(poly, MultiPolygon) else poly)
    except Exception:
        return None

    props = {
        "parcel_id": feature["parcel_id"],
        "source_file": feature["source_file"],
        "city_code": feature["city_code"],
        "city_name": feature["city_name"],
        "map_name": feature["map_name"],
        "lot_number": feature.get("lot_number"),
        "district_code": feature.get("district_code"),
        "district_name": feature.get("district_name"),
        "chome_code": feature.get("chome_code"),
        "chome_name": feature.get("chome_name"),
        "accuracy_class": feature.get("accuracy_class"),
        "coord_type": feature.get("coord_type"),
    }

    return {
        "type": "Feature",
        "geometry": geom,
        "properties": props,
    }
