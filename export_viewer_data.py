#!/usr/bin/env python3
# coding: utf-8
"""
Export all parcel data (including arbitrary-CRS) for the list viewer.

Creates:
  output/maps_index.json         – list of all 144 source maps with stats
  output/maps/{key}.json         – per-map: parcel metadata + local coordinates
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault(
    "PROJ_DATA",
    str(Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo")) / "share" / "proj"),
)

from batch import collect_xml_files
from converter.parser import parse_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def safe_key(name: str) -> str:
    return re.sub(r"[^\w.]", "_", name)


def main() -> None:
    input_dir = Path("input")
    output_dir = Path("output")
    maps_dir = output_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(input_dir.glob("*.zip"))
    if not sources:
        log.error("No ZIP files found in input/")
        sys.exit(1)

    tmp_dir = Path(tempfile.mkdtemp(prefix="moj_export_"))
    try:
        log.info("Extracting XML files…")
        xml_files = collect_xml_files(sources, tmp_dir)
        log.info("Found %d XML files", len(xml_files))

        maps_index = []

        for xml_path in xml_files:
            try:
                parsed = parse_file(xml_path)
            except Exception as exc:
                log.error("Failed %s: %s", xml_path.name, exc)
                continue

            if not parsed.features:
                continue

            # Build per-parcel records with raw MOJ local coordinates
            # MOJ convention: ext[i] = [X=northing, Y=easting]
            parcels = []
            for feat in parsed.features:
                ext = feat.get("exterior", [])
                parcels.append({
                    "id":       feat["parcel_id"],
                    "lot":      feat.get("lot_number") or "",
                    "district": feat.get("district_name") or "",
                    "chome":    feat.get("chome_name") or "",
                    "acc":      feat.get("accuracy_class") or "",
                    "coord":    feat.get("coord_type") or "",
                    # Round to cm precision; arbitrary CRS coords are often integers anyway
                    "ext": [[round(p[0], 2), round(p[1], 2)] for p in ext],
                })

            key = safe_key(xml_path.name)
            map_data = {
                "map_name":  parsed.map_name,
                "city_name": parsed.city_name,
                "city_code": parsed.city_code,
                "crs":       parsed.crs_name,
                "is_geo":    parsed.epsg is not None,
                "parcels":   parcels,
            }
            out_file = maps_dir / f"{key}.json"
            out_file.write_text(json.dumps(map_data, ensure_ascii=False, separators=(",", ":")))

            districts = sorted({p["district"] for p in parcels if p["district"]})
            maps_index.append({
                "src":       xml_path.name,
                "key":       key,
                "map_name":  parsed.map_name,
                "city":      parsed.city_name,
                "crs":       parsed.crs_name,
                "is_geo":    parsed.epsg is not None,
                "count":     len(parcels),
                "districts": districts,
            })
            log.info("  %-40s %5d parcels  %s",
                     xml_path.name, len(parcels),
                     "[geo]" if parsed.epsg else "")

        index_path = output_dir / "maps_index.json"
        index_path.write_text(json.dumps(maps_index, ensure_ascii=False, indent=2))
        total = sum(m["count"] for m in maps_index)
        log.info("Done: %d maps, %d parcels → %s", len(maps_index), total, index_path)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
