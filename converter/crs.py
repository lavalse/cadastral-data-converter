# coding: utf-8
"""
CRS (Coordinate Reference System) definitions for MOJ cadastral XML data.

The actual XML format uses CRS strings like:
  - 任意座標系      → arbitrary (no real-world projection possible)
  - 公共座標X系     → Japan Plane Rectangular Zone X, JGD2000
                      Zone 1 = EPSG:2443, Zone 2 = EPSG:2444, ..., Zone 19 = EPSG:2461
"""
import re


def get_epsg(crs_name: str) -> int | None:
    """
    Return EPSG code for a CRS name string, or None for arbitrary systems.

    Examples:
      '公共座標9系'  → 2451
      '公共座標1系'  → 2443
      '任意座標系'   → None
    """
    if not crs_name or "任意" in crs_name:
        return None

    # Match 公共座標{N}系  (full-width or half-width digits)
    m = re.search(r"公共座標(\d+)系", crs_name)
    if m:
        zone = int(m.group(1))
        if 1 <= zone <= 19:
            return 2442 + zone   # Zone 1 → 2443, Zone 9 → 2451, etc.

    # Legacy names from older converter (kept for compatibility)
    _legacy = {
        "北緯線2000１座標系": 2443,
        "北緯線2000２座標系": 2444,
        "北緯線2000３座標系": 2445,
        "北緯線2000４座標系": 2446,
        "北緯線2000５座標系": 2447,
        "北緯線2000６座標系": 2448,
        "北緯線2000７座標系": 2449,
        "北緯線2000８座標系": 2450,
        "北緯線2000９座標系": 2451,
        "北緯線2000１０座標系": 2452,
        "北緯線2000１１座標系": 2453,
        "北緯線2000１２座標系": 2454,
        "北緯線2000１３座標系": 2455,
        "北緯線2000１４座標系": 2456,
        "北緯線2000１５座標系": 2457,
        "北緯線2000１６座標系": 2458,
        "北緯線2000１７座標系": 2459,
        "北緯線2000１８座標系": 2460,
        "北緯線2000１９座標系": 2461,
    }
    return _legacy.get(crs_name)
