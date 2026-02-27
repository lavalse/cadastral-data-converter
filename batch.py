#!/usr/bin/env python3
# coding: utf-8
"""
Batch converter for MOJ (Ministry of Justice) cadastral XML data.

Converts ZIP archives (or directories of XML files) to:
  - SpatiaLite database (.db)   — for spatial queries and database storage
  - PMTiles file (.pmtiles)     — for MapLibre GL display

Usage examples:
  # Convert a single ZIP:
  python batch.py input/13106-0105-2025.zip -o output/

  # Convert all ZIPs in a directory:
  python batch.py input/ -o output/

  # Skip PMTiles generation (DB only):
  python batch.py input/ -o output/ --no-tiles

  # Skip SpatiaLite (tiles only):
  python batch.py input/ -o output/ --no-db
"""
from __future__ import annotations

import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Iterator

import click
from tqdm import tqdm

# Ensure the geo conda env's PROJ data is found
_GEO_ENV = Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo"))
os.environ.setdefault("PROJ_DATA", str(_GEO_ENV / "share" / "proj"))

from converter.geometry import feature_to_geojson
from converter.parser import parse_file
from converter.db import SpatiaLiteWriter
from converter.tiles import build_pmtiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def collect_xml_files(sources: list[Path], tmp_dir: Path) -> list[Path]:
    """
    Extract all XML files from sources (ZIPs or directories) into tmp_dir.
    Returns a sorted list of extracted XML paths.
    """
    import io

    paths: list[Path] = []

    def _extract_zip(zf: zipfile.ZipFile) -> None:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".xml"):
                dest = tmp_dir / Path(name).name
                with zf.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                paths.append(dest)
            elif lower.endswith(".zip"):
                with zf.open(name) as inner_bytes:
                    with zipfile.ZipFile(io.BytesIO(inner_bytes.read())) as inner_zf:
                        _extract_zip(inner_zf)

    for source in sources:
        if source.is_file() and source.suffix.lower() == ".xml":
            paths.append(source)
        elif source.is_file() and source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as zf:
                _extract_zip(zf)
        elif source.is_dir():
            for child in sorted(source.iterdir()):
                if child.suffix.lower() == ".xml":
                    paths.append(child)
                elif child.suffix.lower() == ".zip":
                    with zipfile.ZipFile(child) as zf:
                        _extract_zip(zf)

    return sorted(paths)


def collect_sources(inputs: tuple[str, ...]) -> list[Path]:
    """Resolve CLI inputs to a list of source paths."""
    sources = []
    for inp in inputs:
        p = Path(inp)
        if not p.exists():
            log.error("Input not found: %s", inp)
            sys.exit(1)
        sources.append(p)
    return sources


@click.command()
@click.argument("inputs", nargs=-1, required=True)
@click.option("-o", "--output-dir", required=True, help="Output directory")
@click.option("--db-name", default="cadastral.db", show_default=True, help="SpatiaLite filename")
@click.option("--tiles-name", default="cadastral.pmtiles", show_default=True, help="PMTiles filename")
@click.option("--no-db", is_flag=True, help="Skip SpatiaLite output")
@click.option("--no-tiles", is_flag=True, help="Skip PMTiles output")
@click.option("--min-zoom", default=10, show_default=True, help="Min zoom for PMTiles")
@click.option("--max-zoom", default=18, show_default=True, help="Max zoom for PMTiles")
@click.option("--skip-arbitrary", is_flag=True, default=True,
              help="Skip files with arbitrary coordinate systems (default: True)")
def main(
    inputs,
    output_dir,
    db_name,
    tiles_name,
    no_db,
    no_tiles,
    min_zoom,
    max_zoom,
    skip_arbitrary,
):
    """Convert MOJ cadastral XML/ZIP files to SpatiaLite + PMTiles."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    db_path = out / db_name
    tiles_path = out / tiles_name

    sources = collect_sources(inputs)

    # Extract all XML files into a single temp dir so paths stay valid
    import shutil
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="moj_xml_"))
    try:
        log.info("Extracting XML files...")
        xml_files = collect_xml_files(sources, tmp_dir)
        log.info("Found %d XML file(s)", len(xml_files))

        _run_conversion(
            xml_files, db_path, out, tiles_path,
            no_db, no_tiles, min_zoom, max_zoom, skip_arbitrary,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_conversion(
    xml_files, db_path, out, tiles_path,
    no_db, no_tiles, min_zoom, max_zoom, skip_arbitrary,
):
    total_features = 0
    skipped_arbitrary = 0
    skipped_geometry = 0
    errors = 0

    geojson_path = out / "cadastral_tmp.geojson" if not no_tiles else None

    # Remove stale DB so we start clean
    if not no_db and db_path.exists():
        db_path.unlink()

    # Open outputs
    db_writer: SpatiaLiteWriter | None = None
    geojson_fh = None

    if not no_db:
        db_writer = SpatiaLiteWriter(db_path)
        db_writer.open()
        log.info("Writing SpatiaLite DB → %s", db_path)

    if not no_tiles and geojson_path:
        geojson_fh = open(geojson_path, "w", encoding="utf-8")
        geojson_fh.write('{"type":"FeatureCollection","features":[\n')
        log.info("Collecting GeoJSON for tiles → %s", geojson_path)

    first_feature = True

    try:
        for xml_path in tqdm(xml_files, desc="Processing XML files", unit="file"):
            try:
                parsed = parse_file(xml_path)
            except Exception as exc:
                log.error("Failed to parse %s: %s", xml_path.name, exc)
                errors += 1
                continue

            if parsed.epsg is None:
                skipped_arbitrary += len(parsed.features)
                if skip_arbitrary:
                    log.debug("Skipping %s (arbitrary CRS: %s)", xml_path.name, parsed.crs_name)
                    continue

            for raw_feature in parsed.features:
                geojson_feature = feature_to_geojson(raw_feature)
                if geojson_feature is None:
                    skipped_geometry += 1
                    continue

                if db_writer:
                    db_writer.write(geojson_feature)

                if geojson_fh:
                    import json
                    prefix = "" if first_feature else ","
                    geojson_fh.write(prefix + json.dumps(geojson_feature, ensure_ascii=False) + "\n")
                    first_feature = False

                total_features += 1

    finally:
        if db_writer:
            db_writer.close()

        if geojson_fh:
            geojson_fh.write("]}\n")
            geojson_fh.close()

    log.info("Written %d features", total_features)
    if skipped_arbitrary:
        log.info("Skipped %d features with arbitrary CRS", skipped_arbitrary)
    if skipped_geometry:
        log.info("Skipped %d features with invalid/empty geometry", skipped_geometry)
    if errors:
        log.warning("Failed to parse %d file(s)", errors)

    if not no_tiles and geojson_path and geojson_path.exists() and total_features > 0:
        log.info("Building PMTiles → %s", tiles_path)
        try:
            build_pmtiles(
                geojson_path,
                tiles_path,
                min_zoom=min_zoom,
                max_zoom=max_zoom,
            )
            log.info("PMTiles written: %s (%.1f MB)", tiles_path,
                     tiles_path.stat().st_size / 1024 / 1024)
        except Exception as exc:
            log.error("PMTiles generation failed: %s", exc)
        finally:
            if geojson_path.exists():
                geojson_path.unlink()
    elif not no_tiles and total_features == 0:
        log.warning("No features to tile.")


if __name__ == "__main__":
    main()
