"""Load Purolator facilities from points_of_interest.csv into payload dicts."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List


def load_facilities_csv(path: str | Path) -> List[dict]:
    """Read the POI CSV into facility payloads for `upsert_facilities`."""
    rows: List[dict] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (KeyError, ValueError):
                continue
            rows.append(
                {
                    "id": row["id"],
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "region": row.get("region"),
                    "corridor": row.get("corridor"),
                    "priority": int(float(row.get("priority") or 1)),
                    "radius_km": float(row.get("radius_km") or 25),
                    "lat": lat,
                    "lon": lon,
                }
            )
    return rows
