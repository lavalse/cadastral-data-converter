#!/usr/bin/env python3
# coding: utf-8
"""
Approximate geographic placement of arbitrary-CRS cadastral parcels.

For each map with 任意座標系 (arbitrary local CRS), geocodes the primary
district/chome via the GSI AddressSearch API and uses the geocoded point as
the origin for a translate-only approximation (1 local unit = 1 metre).

Accuracy: parcels appear in the correct district, correct relative shapes and
sizes, but orientation may differ from reality.

Output:
  output/geocoded_districts.json   – geocoding cache (keyed by query string)
  output/approximate.geojson       – GeoJSON FeatureCollection (intermediate)
  output/approximate.pmtiles       – PMTiles (via tippecanoe)
  viewer/approximate.pmtiles       – symlink → ../output/approximate.pmtiles

Usage:
  python3 georef_approximate.py
"""
from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

os.environ.setdefault(
    "PROJ_DATA",
    str(Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo")) / "share" / "proj"),
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")
MAPS_DIR = OUTPUT_DIR / "maps"
INDEX_PATH = OUTPUT_DIR / "maps_index.json"
GEOCACHE_PATH = OUTPUT_DIR / "geocoded_districts.json"
APPROX_GEOJSON = OUTPUT_DIR / "approximate.geojson"
APPROX_PMTILES = OUTPUT_DIR / "approximate.pmtiles"
VIEWER_SYMLINK = Path("viewer") / "approximate.pmtiles"

_GEO_ENV = Path(os.environ.get("CONDA_PREFIX", "/home/red/miniforge3/envs/geo"))
# When running without conda activate, try the geo env directly
_TIPPECANOE_CANDIDATES = [
    _GEO_ENV / "bin" / "tippecanoe",
    Path("/home/red/miniforge3/envs/geo/bin/tippecanoe"),
]
TIPPECANOE = next((p for p in _TIPPECANOE_CANDIDATES if p.exists()), _TIPPECANOE_CANDIDATES[0])

GSI_API = "https://msearch.gsi.go.jp/address-search/AddressSearch"


# ---------------------------------------------------------------------------
# Geocoding helpers
# ---------------------------------------------------------------------------

def geocode(query: str) -> tuple[float, float] | None:
    """
    Query GSI address search API.
    Returns (lat, lon) in WGS84, or None on failure.
    """
    url = f"{GSI_API}?q={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cadastral-converter/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        if data:
            coords = data[0]["geometry"]["coordinates"]  # [lon, lat]
            return float(coords[1]), float(coords[0])
    except Exception as exc:
        log.warning("Geocode failed for %r: %s", query, exc)
    return None


def load_geocache() -> dict[str, list[float] | None]:
    if GEOCACHE_PATH.exists():
        return json.loads(GEOCACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_geocache(cache: dict) -> None:
    GEOCACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def compute_centroid(parcels: list[dict]) -> tuple[float, float]:
    """Mean of all exterior ring points across all parcels in local coords."""
    xs: list[float] = []
    ys: list[float] = []
    for p in parcels:
        for xy in p.get("ext", []):
            xs.append(xy[0])
            ys.append(xy[1])
    if not xs:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def translate_ring(
    ring: list[list[float]],
    cx: float,
    cy: float,
    lat_c: float,
    lon_c: float,
) -> list[list[float]]:
    """
    Translate a ring from local metre coordinates to approximate WGS84.

    MOJ convention: ext[i] = [X=northing, Y=easting]
    (cx, cy) = local centroid (metres)
    (lat_c, lon_c) = geocoded anchor point (WGS84 degrees)
    """
    m_per_deg_lat = 111_000.0
    m_per_deg_lon = 111_000.0 * math.cos(math.radians(lat_c))
    result: list[list[float]] = []
    for xy in ring:
        dn = xy[0] - cx  # northing delta (metres)
        de = xy[1] - cy  # easting delta (metres)
        lat = lat_c + dn / m_per_deg_lat
        lon = lon_c + de / m_per_deg_lon
        result.append([round(lon, 8), round(lat, 8)])
    return result


# ---------------------------------------------------------------------------
# District selection
# ---------------------------------------------------------------------------

def primary_geocode_query(parcels: list[dict], city: str) -> str:
    """
    Return the most frequent (district, chome) combination as a query string.
    Falls back to just city name if no district information is present.
    """
    counter: Counter = Counter()
    for p in parcels:
        d = (p.get("district") or "").strip()
        c = (p.get("chome") or "").strip()
        if d:
            counter[(d, c)] += 1
    if not counter:
        return city
    (district, chome), _ = counter.most_common(1)[0]
    return f"{city}{district}{chome}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INDEX_PATH.exists():
        log.error("maps_index.json not found — run export_viewer_data.py first")
        raise SystemExit(1)

    index: list[dict] = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    non_geo_maps = [m for m in index if not m["is_geo"]]
    log.info("%d non-geo maps to process (out of %d total)", len(non_geo_maps), len(index))

    geocache = load_geocache()
    features: list[dict] = []
    failed_geocode = 0
    total_parcels = 0

    for map_entry in non_geo_maps:
        key = map_entry["key"]
        city = map_entry["city"]

        map_json_path = MAPS_DIR / f"{key}.json"
        if not map_json_path.exists():
            log.warning("Missing map JSON: %s — skipping", map_json_path.name)
            continue

        map_data: dict = json.loads(map_json_path.read_text(encoding="utf-8"))
        parcels: list[dict] = map_data.get("parcels", [])
        if not parcels:
            continue

        # Determine geocoding query from dominant district/chome
        query = primary_geocode_query(parcels, city)

        # Geocode with cache
        if query not in geocache:
            log.info("  Geocoding: %s", query)
            result = geocode(query)
            geocache[query] = list(result) if result else None
            save_geocache(geocache)
            time.sleep(0.2)  # polite rate limiting

        geo = geocache[query]
        if geo is None:
            log.warning("  No geocode result for %r — skipping map %s", query, key)
            failed_geocode += 1
            continue

        lat_c, lon_c = geo[0], geo[1]

        # Compute local centroid across all parcels in this map file
        cx, cy = compute_centroid(parcels)

        # Build GeoJSON features
        for p in parcels:
            ext = p.get("ext", [])
            if len(ext) < 3:
                continue

            coords_wgs = translate_ring(ext, cx, cy, lat_c, lon_c)

            feature: dict = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords_wgs],
                },
                "properties": {
                    "parcel_id":    p["id"],
                    "source_file":  map_entry["src"],
                    "map_name":     map_data.get("map_name", ""),
                    "lot_number":   p.get("lot") or "",
                    "district_name": p.get("district") or "",
                    "chome_name":   p.get("chome") or "",
                    "accuracy_class": p.get("acc") or "",
                    "coord_type":   p.get("coord") or "",
                    "is_approximate": True,
                },
            }
            features.append(feature)
            total_parcels += 1

    log.info("Writing %d approximate features → %s", total_parcels, APPROX_GEOJSON)
    with APPROX_GEOJSON.open("w", encoding="utf-8") as f:
        f.write('{"type":"FeatureCollection","features":[\n')
        for i, feat in enumerate(features):
            prefix = "" if i == 0 else ","
            f.write(prefix + json.dumps(feat, ensure_ascii=False) + "\n")
        f.write("]}\n")

    if failed_geocode:
        log.warning("%d map(s) had geocoding failures and were skipped", failed_geocode)

    # Build PMTiles via tippecanoe
    log.info("Building PMTiles → %s", APPROX_PMTILES)
    cmd = [
        str(TIPPECANOE),
        "-o", str(APPROX_PMTILES),
        "-l", "parcels_approx",
        "-Z10", "-z18",
        "--force",
        "--no-tile-size-limit",
        "--no-feature-limit",
        str(APPROX_GEOJSON),
    ]
    subprocess.run(cmd, check=True)
    size_mb = APPROX_PMTILES.stat().st_size / 1024 / 1024
    log.info("PMTiles written: %.1f MB", size_mb)

    # Create symlink in viewer/
    VIEWER_SYMLINK.parent.mkdir(parents=True, exist_ok=True)
    if VIEWER_SYMLINK.exists() or VIEWER_SYMLINK.is_symlink():
        VIEWER_SYMLINK.unlink()
    VIEWER_SYMLINK.symlink_to(Path("..") / "output" / "approximate.pmtiles")
    log.info("Symlink: %s → ../output/approximate.pmtiles", VIEWER_SYMLINK)

    log.info("Done — %d approximate features written.", total_parcels)


if __name__ == "__main__":
    main()
