# coding: utf-8
"""
SpatiaLite database writer for cadastral parcel data.

Schema:
  parcels (
    id            INTEGER PRIMARY KEY,
    parcel_id     TEXT NOT NULL,
    source_file   TEXT,
    city_code     TEXT,
    city_name     TEXT,
    map_name      TEXT,
    lot_number    TEXT,
    lot_number_sub TEXT,
    registered_land_use TEXT,
    statistical_land_use TEXT,
    parcel_number TEXT,
    shape_class   TEXT,
    owner_type    TEXT,
    geom          MULTIPOLYGON (EPSG:4326)
  )
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterator

# Ensure spatialite extension path is on LD_LIBRARY_PATH / known location
_GEO_ENV = Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo"))
_MOD_SPATIALITE = _GEO_ENV / "lib" / "mod_spatialite"


def _load_spatialite(conn: sqlite3.Connection) -> None:
    conn.enable_load_extension(True)
    conn.load_extension(str(_MOD_SPATIALITE))
    conn.enable_load_extension(False)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS parcels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parcel_id       TEXT NOT NULL,
    source_file     TEXT,
    city_code       TEXT,
    city_name       TEXT,
    map_name        TEXT,
    lot_number      TEXT,
    district_code   TEXT,
    district_name   TEXT,
    chome_code      TEXT,
    chome_name      TEXT,
    accuracy_class  TEXT,
    coord_type      TEXT
);
"""

INSERT_SQL = """
INSERT INTO parcels (
    parcel_id, source_file, city_code, city_name, map_name,
    lot_number, district_code, district_name, chome_code, chome_name,
    accuracy_class, coord_type,
    geom
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    SetSRID(GeomFromGeoJSON(?), 4326)
);
"""


class SpatiaLiteWriter:
    """
    Write GeoJSON Features to a SpatiaLite database.

    Usage:
        with SpatiaLiteWriter("output.db") as writer:
            writer.write(geojson_feature)
    """

    def __init__(self, path: Path | str, batch_size: int = 1000) -> None:
        self.path = Path(path)
        self.batch_size = batch_size
        self._conn: sqlite3.Connection | None = None
        self._pending: list = []

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self.path))
        _load_spatialite(self._conn)
        self._conn.execute("SELECT InitSpatialMetadata(1)")
        self._conn.execute(CREATE_TABLE_SQL)
        self._conn.execute(
            "SELECT AddGeometryColumn('parcels', 'geom', 4326, 'MULTIPOLYGON', 'XY')"
        )
        self._conn.execute(
            "SELECT CreateSpatialIndex('parcels', 'geom')"
        )
        self._conn.commit()

    def close(self) -> None:
        if self._pending:
            self._flush()
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SpatiaLiteWriter":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def write(self, feature: dict) -> None:
        """Queue one GeoJSON Feature for insertion."""
        props = feature.get("properties", {})
        geom_json = json.dumps(feature["geometry"])
        self._pending.append((
            props.get("parcel_id"),
            props.get("source_file"),
            props.get("city_code"),
            props.get("city_name"),
            props.get("map_name"),
            props.get("lot_number"),
            props.get("district_code"),
            props.get("district_name"),
            props.get("chome_code"),
            props.get("chome_name"),
            props.get("accuracy_class"),
            props.get("coord_type"),
            geom_json,
        ))
        if len(self._pending) >= self.batch_size:
            self._flush()

    def write_many(self, features: Iterator[dict]) -> int:
        """Write an iterator of features; return count written."""
        count = 0
        for f in features:
            self.write(f)
            count += 1
        return count

    def _flush(self) -> None:
        assert self._conn is not None
        self._conn.executemany(INSERT_SQL, self._pending)
        self._conn.commit()
        self._pending.clear()
