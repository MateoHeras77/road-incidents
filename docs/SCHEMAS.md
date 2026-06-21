# Data Schemas

Raw shapes captured from each source (see `backend/samples/`) and how they map to
the normalized model. Captured 2026-06-20.

## Normalized model

`RoadEvent` (table `road_events`):

| Field | Notes |
|-------|-------|
| source | `bc\|ab\|sk\|on\|mb\|qc\|nb\|ns\|pe\|nl` |
| source_event_id | stable upstream id; unique with `source` |
| province | full province name |
| event_class | `closure\|accident\|construction\|restriction\|special\|info\|condition\|other` |
| roadway_name, road_number | road_number extracted by highway filter |
| is_highway | local roads filtered out at ingest |
| is_full_closure | full road closure |
| direction, severity, headline, description | |
| raw_event_type, raw_event_subtype | original source type strings |
| restrictions | `{width,height,length,weight,speed}` (truck-relevant) |
| starts_at, planned_end_at, is_scheduled | `is_scheduled` = starts in the future |
| reported_at, last_updated | |
| geojson → geom | server builds PostGIS geography from GeoJSON |
| lat, lon | representative point (`ST_PointOnSurface`) |

`Camera` (`cameras`), `RoadCondition` (`road_conditions`) and `facilities` follow the
same payload→RPC pattern. `relevant_road_events` is a view joining events to
facilities within `radius_km` (`ST_DWithin`), adding `distance_km` + facility info.

## 1. Open511 — British Columbia

`GET https://api.open511.gov.bc.ca/events?format=json&limit=500`

```
{ "events": [ {
  "id": "drivebc.ca/DBC-90617", "headline": "CONSTRUCTION", "status": "ACTIVE",
  "created": "...", "updated": "...", "description": "...",
  "schedule": { "intervals": ["2026-04-29T18:34/2026-10-02T06:59"] },
  "event_type": "CONSTRUCTION", "event_subtypes": ["ROAD_CONSTRUCTION"],
  "severity": "MINOR",
  "geography": { "type": "Point", "coordinates": [-120.78, 49.66] },
  "roads": [ { "name": "Highway 99", "direction": "NONE", "state": "..." } ]
} ], "pagination": {...} }
```

Mapping: `event_type`→event_class; `roads[0].name`→roadway (+highway classify);
`roads[].state == CLOSED`→full closure; `schedule.intervals[0]`→start/end;
`geography`→geojson (already GeoJSON).

## 2. IBI / 511 platform — Alberta, Saskatchewan, Ontario, Manitoba (+Atlantic)

`GET https://<host>/api/v2/get/event?format=json&lang=en[&key=...]` → JSON array.

```
{ "ID": 7, "SourceId": "57604", "RoadwayName": "Moraine Lake Rd",
  "DirectionOfTravel": "All", "Description": "...",
  "Reported": 1723917420, "LastUpdated": 1781933873, "StartDate": ..., "PlannedEndDate": null,
  "EventType": "closures", "EventSubType": "general", "IsFullClosure": true,
  "Severity": "None", "Latitude": 51.41, "Longitude": -116.19, "EncodedPolyline": null,
  "Restrictions": { "Width": null, "Height": null, "Length": null, "Weight": null, "Speed": null } }
```

`EventType` values: `roadwork, closures, accidentsAndIncidents, restrictionClass,
generalInfo, specialEvents`. Timestamps are Unix epoch seconds. Geometry = point
(`Latitude/Longitude`) or decoded `EncodedPolyline` (Google polyline).

- **cameras** (`/get/cameras`): `Id, SourceId, Roadway, Location, Latitude, Longitude,
  Views[{Url}]`.
- **road conditions** — Ontario/Manitoba `/get/roadconditions`: `RoadwayName` (bare
  number e.g. `"627"`), `Condition: [..]`, `EncodedPolyline` (string), `LastUpdated`.
  Alberta `/api/v3/get/winterroads`: `Id, RoadwayName, "Primary Condition",
  "Secondary Conditions", EncodedPolyline` (**array** of polylines), `LastUpdated`.
  Noise conditions (`No Report`, etc.) are dropped.

Hosts & keys in `backend/src/ingest/adapters/ibi511.py:IBI_PROVINCES`.

## 3. MTQ Québec — WFS GeoJSON

`GET https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:evenements&outfile=AvertissementRoutier&srsname=EPSG:4326&outputformat=geojson`

```
{ "type": "FeatureCollection", "features": [ {
  "geometry": { "type": "LineString", "coordinates": [...] },
  "properties": {
    "identifiant": 81387, "entrave": "Circulation en alternance",
    "numeroRoute": "", "localisation": "...", "direction": "OUEST et EST",
    "municipalite": "Val-des-Monts", "cause": "Mesures préventives",
    "consequence": "", "detour": "", "regions": "(1:Outaouais)",
    "enVigueurDepuis": "2025-07-30T11:17:00" } } ] }
```

French fields. **`numeroRoute` non-empty → highway** (numbered route); empty → local
(filtered out). `cause`/`entrave` map to event_class; `"fermeture"` (without
`"voie"`) → full closure. Geometry is a GeoJSON LineString.
