# coding: utf-8
"""
PMTiles generation from a SpatiaLite database or GeoJSON file.

Pipeline:
  SpatiaLite → GeoJSON (ogr2ogr) → tippecanoe → PMTiles

tippecanoe 2.x supports PMTiles output directly.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

_GEO_ENV = Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo"))
_TIPPECANOE = _GEO_ENV / "bin" / "tippecanoe"
_OGR2OGR = _GEO_ENV / "bin" / "ogr2ogr"


def db_to_geojson(db_path: Path, geojson_path: Path) -> None:
    """Export all parcels from SpatiaLite to a GeoJSON file via ogr2ogr."""
    cmd = [
        str(_OGR2OGR),
        "-f", "GeoJSON",
        str(geojson_path),
        str(db_path),
        "parcels",
        "-t_srs", "EPSG:4326",
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def build_pmtiles(
    input_path: Path,
    output_path: Path,
    layer_name: str = "parcels",
    min_zoom: int = 10,
    max_zoom: int = 18,
    extra_args: list[str] | None = None,
) -> None:
    """
    Generate a PMTiles file from a GeoJSON or SpatiaLite source using tippecanoe.

    Args:
        input_path:  GeoJSON file (or a .db file; .db triggers ogr2ogr export first).
        output_path: Destination .pmtiles file.
        layer_name:  Vector tile layer name.
        min_zoom:    Minimum zoom level (default 10 — cadastral data is detail-heavy).
        max_zoom:    Maximum zoom level (default 18).
        extra_args:  Additional tippecanoe arguments.
    """
    geojson_path = input_path
    _tmp = None
    if input_path.suffix in (".db", ".sqlite"):
        _tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
        geojson_path = Path(_tmp.name)
        _tmp.close()
        db_to_geojson(input_path, geojson_path)

    cmd = [
        str(_TIPPECANOE),
        "-o", str(output_path),
        "-l", layer_name,
        "-z", str(max_zoom),
        "-Z", str(min_zoom),
        "--force",           # overwrite existing output
        "--no-tile-size-limit",
        "--no-feature-limit",
        str(geojson_path),
    ]
    if extra_args:
        cmd.extend(extra_args)

    try:
        subprocess.run(cmd, check=True)
    finally:
        if _tmp is not None and geojson_path.exists():
            geojson_path.unlink()
