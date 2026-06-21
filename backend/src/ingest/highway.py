"""Highway classification.

Middle Mile cares about provincial highways and major routes, not local
streets. This module decides whether a road name refers to a highway and, if
so, extracts a normalized route number. Tuned against real samples in
backend/samples/.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# Keywords that indicate a highway / major route (English + French).
_HIGHWAY_KEYWORDS = re.compile(
    r"\b("
    r"hwy|highway|autoroute|trans[\s-]?canada|tch|qew|freeway|expressway|"
    r"thruway|parkway|bypass|route\s*\d"
    r")\b",
    re.IGNORECASE,
)

# Province route codes such as "AB-2", "ON 401", "NB-1", "QC-20".
_ROUTE_CODE = re.compile(r"\b([A-Z]{2})[\s-]?(\d{1,3}[A-Z]?)\b")

# "Highway 401", "Hwy 16", "Autoroute 20", "Route 11".
_NAMED_NUMBER = re.compile(
    r"\b(?:hwy|highway|autoroute|route)\s*#?\s*(\d{1,3}[A-Z]?)\b",
    re.IGNORECASE,
)

# Named highways that carry no number.
_NAMED_HIGHWAYS = {"qew": "QEW", "gardiner": "Gardiner", "dvp": "DVP"}


def classify_highway(name: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Return (is_highway, road_number) for an IBI/Open511 road name."""
    if not name:
        return False, None
    text = name.strip()
    low = text.lower()

    for token, label in _NAMED_HIGHWAYS.items():
        if re.search(rf"\b{token}\b", low):
            return True, label

    m = _NAMED_NUMBER.search(text)
    if m:
        return True, m.group(1).upper()

    m = _ROUTE_CODE.search(text)
    if m:
        return True, f"{m.group(1).upper()}-{m.group(2).upper()}"

    if _HIGHWAY_KEYWORDS.search(text):
        return True, None

    return False, None


def quebec_is_highway(numero_route: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Québec MTQ feed: a non-empty `numeroRoute` means a numbered route."""
    if numero_route and str(numero_route).strip():
        return True, str(numero_route).strip()
    return False, None
