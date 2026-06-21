-- Road Incidents — database schema (Supabase / PostGIS)
-- Consolidates Canadian provincial highway events, road conditions and cameras
-- for Purolator Middle Mile planners.
--
-- Applied to Supabase as migrations:
--   0001_enable_postgis, 0002_core_tables, 0003_views_and_rls
-- This file is the canonical, idempotent reference of the full schema.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists postgis;

-- ---------------------------------------------------------------------------
-- Facilities (Purolator points of interest / network nodes)
-- Loaded from points_of_interest.csv. radius_km defines the relevance buffer.
-- ---------------------------------------------------------------------------
create table if not exists public.facilities (
    id          text primary key,
    name        text not null,
    type        text,
    region      text,
    corridor    text,
    priority    int  not null default 1,
    radius_km   numeric not null default 25,
    lat         double precision not null,
    lon         double precision not null,
    geom        geography(Point, 4326) not null
);
create index if not exists facilities_geom_idx on public.facilities using gist (geom);

-- ---------------------------------------------------------------------------
-- Road events (closures, accidents, construction, restrictions, ...)
-- Normalized across Open511 (BC), IBI/511 (AB, SK, ON, MB, +Atlantic) and
-- MTQ WFS (QC). One row per source event; upserted on (source, source_event_id).
-- ---------------------------------------------------------------------------
create table if not exists public.road_events (
    id               bigint generated always as identity primary key,
    source           text not null,                 -- bc|ab|sk|on|mb|qc|nb|ns|pe|nl
    source_event_id  text not null,
    province         text not null,
    event_class      text not null,                 -- closure|accident|construction|restriction|special|info|other
    raw_event_type   text,
    raw_event_subtype text,
    roadway_name     text,
    road_number      text,
    is_highway       boolean not null default false,
    is_full_closure  boolean not null default false,
    direction        text,
    severity         text,
    headline         text,
    description      text,
    restrictions     jsonb,                          -- {width,height,length,weight,speed}
    starts_at        timestamptz,
    planned_end_at   timestamptz,
    is_scheduled     boolean not null default false, -- starts in the future
    reported_at      timestamptz,
    last_updated     timestamptz,
    lat              double precision,
    lon              double precision,
    geom             geography(Geometry, 4326),      -- point or linestring
    raw              jsonb,
    ingested_at      timestamptz not null default now(),
    constraint road_events_source_uniq unique (source, source_event_id)
);
create index if not exists road_events_geom_idx on public.road_events using gist (geom);
create index if not exists road_events_class_idx on public.road_events (event_class);
create index if not exists road_events_province_idx on public.road_events (province);
create index if not exists road_events_highway_idx on public.road_events (is_highway);

-- ---------------------------------------------------------------------------
-- Road conditions (winter / surface state), segment-based.
-- ---------------------------------------------------------------------------
create table if not exists public.road_conditions (
    id               bigint generated always as identity primary key,
    source           text not null,
    source_cond_id   text not null,
    province         text not null,
    roadway_name     text,
    road_number      text,
    is_highway       boolean not null default false,
    condition        text,                           -- e.g. bare/dry, snow covered, ice
    condition_raw    text,
    geom             geography(Geometry, 4326),
    last_updated     timestamptz,
    raw              jsonb,
    ingested_at      timestamptz not null default now(),
    constraint road_conditions_source_uniq unique (source, source_cond_id)
);
create index if not exists road_conditions_geom_idx on public.road_conditions using gist (geom);

-- ---------------------------------------------------------------------------
-- Traffic cameras.
-- ---------------------------------------------------------------------------
create table if not exists public.cameras (
    id               bigint generated always as identity primary key,
    source           text not null,
    source_camera_id text not null,
    province         text not null,
    title            text,
    roadway          text,
    lat              double precision,
    lon              double precision,
    geom             geography(Point, 4326),
    views            jsonb,                          -- [{url,...}]
    last_updated     timestamptz,
    raw              jsonb,
    ingested_at      timestamptz not null default now(),
    constraint cameras_source_uniq unique (source, source_camera_id)
);
create index if not exists cameras_geom_idx on public.cameras using gist (geom);

-- ---------------------------------------------------------------------------
-- Relevance view: events within a facility's radius. One row per
-- (event, nearby facility) pair, with distance. Frontend groups by event.
-- ---------------------------------------------------------------------------
create or replace view public.relevant_road_events as
select
    e.*,
    f.id        as facility_id,
    f.name      as facility_name,
    f.priority  as facility_priority,
    f.corridor  as facility_corridor,
    round((st_distance(e.geom, f.geom) / 1000)::numeric, 1) as distance_km
from public.road_events e
join public.facilities f
  on e.geom is not null
 and st_dwithin(e.geom, f.geom, f.radius_km * 1000);

-- ---------------------------------------------------------------------------
-- Row Level Security: internal tool, read-only for the anon (frontend) role.
-- Writes happen only through the service_role key used by the ingester.
-- ---------------------------------------------------------------------------
alter table public.facilities       enable row level security;
alter table public.road_events      enable row level security;
alter table public.road_conditions  enable row level security;
alter table public.cameras          enable row level security;

drop policy if exists "anon read facilities"      on public.facilities;
drop policy if exists "anon read road_events"     on public.road_events;
drop policy if exists "anon read road_conditions" on public.road_conditions;
drop policy if exists "anon read cameras"         on public.cameras;

create policy "anon read facilities"      on public.facilities      for select to anon using (true);
create policy "anon read road_events"     on public.road_events     for select to anon using (true);
create policy "anon read road_conditions" on public.road_conditions for select to anon using (true);
create policy "anon read cameras"         on public.cameras         for select to anon using (true);
