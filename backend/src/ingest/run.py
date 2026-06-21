"""Ingester orchestrator.

Collects road events / cameras / conditions from every configured province,
filters to highways, and writes them to Supabase. Supports an offline mode
that reads captured sample payloads instead of hitting the network.

Examples:
    python -m src.ingest.run --push --facilities ../points_of_interest.csv
    python -m src.ingest.run --from-samples samples --out samples/normalized
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from .adapters import ibi511, mtq_quebec, open511
from .config import API_KEYS, settings
from .facilities import load_facilities_csv
from .throttle import RateLimiter

# Sources that work without a key today (+ Manitoba whose key we hold).
DEFAULT_SOURCES = ["bc", "ab", "on", "mb", "qc"]
ALL_SOURCES = DEFAULT_SOURCES + ["sk", "nb", "ns", "pe", "nl"]

# Which captured sample file feeds which resource, for offline runs.
SAMPLE_FILES = {
    "bc": {"events": "bc_open511_events.json"},
    "ab": {"events": "ab_event.json", "cameras": "ab_cameras.json", "conditions": "ab_winterroads.json"},
    "on": {"events": "on_event.json", "conditions": "on_roadconditions.json"},
    "mb": {"events": "mb_event.json"},
    "qc": {"events": "qc_events.geojson"},
}


def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def collect_from_samples(source: str, sample_dir: Path) -> Dict[str, list]:
    files = SAMPLE_FILES.get(source, {})
    out: Dict[str, list] = {"events": [], "cameras": [], "conditions": []}
    if source == "bc" and "events" in files:
        out["events"] = open511.parse_events(_load(sample_dir / files["events"]))
    elif source == "qc" and "events" in files:
        out["events"] = mtq_quebec.parse_events(_load(sample_dir / files["events"]))
    elif source in ibi511.IBI_PROVINCES:
        prov = ibi511.IBI_PROVINCES[source]["province"]
        if "events" in files:
            out["events"] = ibi511.parse_events(_load(sample_dir / files["events"]), source, prov)
        if "cameras" in files:
            out["cameras"] = ibi511.parse_cameras(_load(sample_dir / files["cameras"]), source, prov)
        if "conditions" in files:
            out["conditions"] = ibi511.parse_conditions(_load(sample_dir / files["conditions"]), source, prov)
    return out


def collect_live(source: str, limiter: RateLimiter) -> Dict[str, list]:
    out: Dict[str, list] = {"events": [], "cameras": [], "conditions": []}
    key = API_KEYS.get(source)
    if source == "bc":
        out["events"] = open511.fetch_events()
    elif source == "qc":
        out["events"] = mtq_quebec.fetch_events()
    elif source in ibi511.IBI_PROVINCES:
        cfg = ibi511.IBI_PROVINCES[source]
        if cfg["needs_key"] and not key:
            print(f"  ! {source}: API key missing, skipping")
            return out
        limiter.acquire()
        out["events"] = ibi511.fetch_events(source, key)
        try:
            limiter.acquire()
            out["cameras"] = ibi511.fetch_cameras(source, key)
        except Exception as exc:  # cameras are optional
            print(f"  ! {source} cameras: {exc}")
        resource, version = ("winterroads", "v3") if source == "ab" else ("roadconditions", "v2")
        try:
            limiter.acquire()
            out["conditions"] = ibi511.fetch_conditions(source, key, resource=resource, version=version)
        except Exception as exc:
            print(f"  ! {source} conditions: {exc}")
    return out


def filter_highways(collected: Dict[str, list], highways_only: bool) -> Dict[str, list]:
    if not highways_only:
        return collected
    collected["events"] = [e for e in collected["events"] if e.is_highway]
    collected["conditions"] = [c for c in collected["conditions"] if c.is_highway]
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Road Incidents ingester")
    parser.add_argument("--source", action="append", help="Source code(s); default core set")
    parser.add_argument("--all-sources", action="store_true", help="Include key-gated provinces")
    parser.add_argument("--from-samples", metavar="DIR", help="Offline: parse captured samples")
    parser.add_argument("--out", metavar="DIR", help="Write normalized JSON payloads to DIR")
    parser.add_argument("--push", action="store_true", help="Write to Supabase")
    parser.add_argument("--facilities", metavar="CSV", help="Load facilities CSV into Supabase")
    parser.add_argument("--all-roads", action="store_true", help="Keep local roads (default: highways only)")
    parser.add_argument("--no-raw", action="store_true", help="Exclude the raw source blob from payloads")
    args = parser.parse_args()

    sources = args.source or (ALL_SOURCES if args.all_sources else DEFAULT_SOURCES)
    highways_only = not args.all_roads
    limiter = RateLimiter()
    sink = None
    if args.push or args.facilities:
        settings.require_supabase()
        from .sink import SupabaseSink

        sink = SupabaseSink(settings.supabase_url, settings.supabase_service_key)

    if args.facilities and sink:
        facs = load_facilities_csv(args.facilities)
        print(f"facilities: upserting {len(facs)}")
        print(f"  -> {sink.upsert_facilities(facs)} rows")

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    totals = {"events": 0, "cameras": 0, "conditions": 0}
    failures = []
    for source in sources:
        try:
            if args.from_samples:
                collected = collect_from_samples(source, Path(args.from_samples))
            else:
                collected = collect_live(source, limiter)
        except Exception as exc:
            # One source failing must not abort the rest, and must not clear its
            # existing rows in the DB — skip it entirely this run.
            print(f"{source}: FETCH FAILED, skipping (DB left unchanged): {exc}")
            failures.append(source)
            continue
        collected = filter_highways(collected, highways_only)
        n_e, n_cam, n_c = len(collected["events"]), len(collected["cameras"]), len(collected["conditions"])
        totals["events"] += n_e
        totals["cameras"] += n_cam
        totals["conditions"] += n_c
        print(f"{source}: events={n_e} cameras={n_cam} conditions={n_c}")

        if out_dir:
            inc = not args.no_raw
            payloads = {
                "events": [e.to_payload(include_raw=inc) for e in collected["events"]],
                "cameras": [c.to_payload(include_raw=inc) for c in collected["cameras"]],
                "conditions": [c.to_payload(include_raw=inc) for c in collected["conditions"]],
            }
            with open(out_dir / f"{source}.json", "w", encoding="utf-8") as fh:
                json.dump(payloads, fh, ensure_ascii=False)

        if sink:
            sink.replace_events(source, collected["events"])
            if collected["cameras"]:
                sink.replace_cameras(source, collected["cameras"])
            if collected["conditions"]:
                sink.replace_conditions(source, collected["conditions"])

    print(f"TOTAL events={totals['events']} cameras={totals['cameras']} conditions={totals['conditions']}")
    if failures:
        print(f"FAILED sources: {', '.join(failures)}")
    # Only treat a run as failed if every requested source failed (a real outage),
    # not for an isolated transient timeout.
    if failures and len(failures) == len(sources):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
