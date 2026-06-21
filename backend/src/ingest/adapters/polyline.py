"""Google encoded-polyline decoder.

IBI/511 feeds deliver geometry as Google-encoded polylines (a single string
for events/road conditions, or a list of strings for Alberta winter roads).
"""
from __future__ import annotations

from typing import List, Optional, Tuple, Union


def decode(encoded: str) -> List[Tuple[float, float]]:
    """Decode one polyline string into a list of (lon, lat) pairs."""
    coords: List[Tuple[float, float]] = []
    index = lat = lon = 0
    length = len(encoded)

    while index < length:
        for is_lon in (False, True):
            shift = result = 0
            while True:
                if index >= length:
                    return coords
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lon:
                lon += delta
            else:
                lat += delta
        coords.append((lon / 1e5, lat / 1e5))  # GeoJSON order: [lon, lat]
    return coords


def to_geojson(encoded: Union[str, List[str], None]) -> Optional[dict]:
    """Convert an encoded polyline (or list of them) into a GeoJSON geometry."""
    if not encoded:
        return None

    if isinstance(encoded, str):
        coords = decode(encoded)
        if len(coords) < 2:
            return {"type": "Point", "coordinates": coords[0]} if coords else None
        return {"type": "LineString", "coordinates": coords}

    lines = [decode(s) for s in encoded if s]
    lines = [ln for ln in lines if len(ln) >= 2]
    if not lines:
        return None
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}
