# coding: utf-8
"""
Parse MOJ (Ministry of Justice) cadastral XML files.

Actual XML structure (ver1.0, namespace http://www.moj.go.jp/MINJI/tizuxml):

  地図
  ├── version, 地図名, 市区町村コード, 市区町村名, 座標系, 測地系判別
  ├── 空間属性                ← geometry section
  │   ├── zmn:GM_Point[]    ← coordinate points
  │   ├── zmn:GM_Curve[]    ← line segments (reference points)
  │   └── zmn:GM_Surface[]  ← polygon surfaces (ID starts with F)
  └── 主題属性                ← thematic attributes section
      ├── 基準点[]            ← reference points (ignored)
      ├── 筆界点[]            ← boundary points (ignored)
      ├── 筆界線[]            ← boundary lines (ignored)
      └── 筆[]               ← parcels
          ├── @id
          ├── 大字コード/大字名 (district code/name)
          ├── 丁目コード/丁目名 (chome code/name)
          ├── 地番            (lot number)
          ├── 形状[@idref]    → surface ID (F...)
          ├── 精度区分         (accuracy class)
          └── 座標値種別       (coordinate type)
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import xmltodict

from .crs import get_epsg


def _ensure_list(obj: Any) -> list:
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


def _build_point_table(spatial: dict) -> dict[str, list[float]]:
    table: dict[str, list[float]] = {}
    for pt in _ensure_list(spatial.get("zmn:GM_Point")):
        pid = pt["@id"]
        pos = pt["zmn:GM_Point.position"]["zmn:DirectPosition"]
        table[pid] = [float(pos["zmn:X"]), float(pos["zmn:Y"])]
    return table


def _build_curve_table(
    spatial: dict, point_table: dict[str, list[float]]
) -> dict[str, list[list[float]]]:
    table: dict[str, list[list[float]]] = {}
    for curve in _ensure_list(spatial.get("zmn:GM_Curve")):
        cid = curve["@id"]
        pts: list[list[float]] = []
        columns = (
            curve["zmn:GM_Curve.segment"]["zmn:GM_LineString"][
                "zmn:GM_LineString.controlPoint"
            ]["zmn:GM_PointArray.column"]
        )
        for col in _ensure_list(columns):
            if col.get("zmn:GM_Position.indirect") is not None:
                ref_id = col["zmn:GM_Position.indirect"]["zmn:GM_PointRef.point"][
                    "@idref"
                ]
                pts.append(point_table[ref_id])
            elif col.get("zmn:GM_Position.direct") is not None:
                direct = col["zmn:GM_Position.direct"]
                pts.append([float(direct["zmn:X"]), float(direct["zmn:Y"])])
        table[cid] = pts
    return table


def _ring_coords(ring_def: Any, curve_table: dict) -> list[list[float]]:
    coords: list[list[float]] = []
    generators = _ensure_list(
        ring_def["zmn:GM_Ring"].get("zmn:GM_CompositeCurve.generator")
    )
    for gen in generators:
        ref_id = gen["@idref"]
        coords.extend(curve_table[ref_id])
    return [k for k, _ in itertools.groupby(coords)]


def _build_surface_table(
    spatial: dict, curve_table: dict
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for surf in _ensure_list(spatial.get("zmn:GM_Surface")):
        sid = surf["@id"]
        boundary = surf["zmn:GM_Surface.patch"]["zmn:GM_Polygon"][
            "zmn:GM_Polygon.boundary"
        ]["zmn:GM_SurfaceBoundary"]

        exterior = _ring_coords(boundary["zmn:GM_SurfaceBoundary.exterior"], curve_table)
        interior_rings: list[list[list[float]]] = []
        if boundary.get("zmn:GM_SurfaceBoundary.interior") is not None:
            for ring_def in _ensure_list(boundary["zmn:GM_SurfaceBoundary.interior"]):
                interior_rings.append(_ring_coords(ring_def, curve_table))

        table[sid] = {"exterior": exterior, "interior": interior_rings}
    return table


# Parcel fields (XML key → output key)
PARCEL_FIELDS = [
    ("地番", "lot_number"),
    ("大字コード", "district_code"),
    ("大字名", "district_name"),
    ("丁目コード", "chome_code"),
    ("丁目名", "chome_name"),
    ("小字コード", "sub_district_code"),
    ("精度区分", "accuracy_class"),
    ("座標値種別", "coord_type"),
]


class ParsedFile:
    def __init__(self) -> None:
        self.city_code: str = ""
        self.city_name: str = ""
        self.map_name: str = ""
        self.version: str = ""
        self.crs_name: str = ""
        self.epsg: int | None = None
        self.features: list[dict] = []


def parse_file(path: Path) -> ParsedFile:
    """
    Parse a MOJ XML file and return a ParsedFile with all parcel features.
    Features with arbitrary coordinate systems will have epsg=None.
    """
    with open(path, encoding="utf-8") as fh:
        raw = xmltodict.parse(fh.read())

    root = raw["地図"]
    result = ParsedFile()
    result.version = root.get("version", "")
    result.map_name = root.get("地図名", "")
    result.city_code = root.get("市区町村コード", "")
    result.city_name = root.get("市区町村名", "")
    result.crs_name = root.get("座標系", "")
    result.epsg = get_epsg(result.crs_name)

    spatial = root.get("空間属性", {})
    thematic = root.get("主題属性", {})

    # Build geometry lookup tables
    point_table = _build_point_table(spatial)
    curve_table = _build_curve_table(spatial, point_table)
    surface_table = _build_surface_table(spatial, curve_table)

    for parcel in _ensure_list(thematic.get("筆")):
        shape_ref = parcel.get("形状", {})
        if isinstance(shape_ref, dict):
            surface_id = shape_ref.get("@idref")
        else:
            continue  # unexpected format

        if surface_id is None or surface_id not in surface_table:
            continue

        surf = surface_table[surface_id]
        feature: dict[str, Any] = {
            "parcel_id": parcel.get("@id", ""),
            "source_file": path.name,
            "city_code": result.city_code,
            "city_name": result.city_name,
            "map_name": result.map_name,
            "version": result.version,
            "crs_name": result.crs_name,
            "epsg": result.epsg,
            "exterior": surf["exterior"],
            "interior": surf["interior"],
        }
        for xml_key, out_key in PARCEL_FIELDS:
            feature[out_key] = parcel.get(xml_key)

        result.features.append(feature)

    return result
