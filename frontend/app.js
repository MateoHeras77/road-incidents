"use strict";

const CFG = window.ROAD_INCIDENTS_CONFIG;

const CLASS_COLORS = {
  closure: "#e03131",
  accident: "#f08c00",
  construction: "#e8a90c",
  restriction: "#7048e8",
  special: "#1c7ed6",
  condition: "#0ca678",
  info: "#868e96",
  other: "#868e96",
};
const CLASS_LABELS = {
  closure: "Closure", accident: "Accident", construction: "Construction",
  restriction: "Restriction", special: "Special", condition: "Condition",
  info: "Info", other: "Other",
};
const CLASS_RANK = { closure: 0, accident: 1, construction: 2, restriction: 3, special: 4, condition: 5, info: 6, other: 7 };
const PROVINCE_ABBR = {
  "British Columbia": "BC", "Alberta": "AB", "Saskatchewan": "SK", "Manitoba": "MB",
  "Ontario": "ON", "Quebec": "QC", "New Brunswick": "NB", "Nova Scotia": "NS",
  "Prince Edward Island": "PE", "Newfoundland and Labrador": "NL",
};

// --- Supabase REST -------------------------------------------------------
async function rest(path) {
  const url = `${CFG.SUPABASE_URL}/rest/v1/${path}`;
  const res = await fetch(url, {
    headers: { apikey: CFG.SUPABASE_KEY, Authorization: `Bearer ${CFG.SUPABASE_KEY}` },
  });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

async function restAll(table, select) {
  const pageSize = 1000;
  let offset = 0, all = [];
  while (true) {
    const rows = await rest(`${table}?select=${select}&limit=${pageSize}&offset=${offset}`);
    all = all.concat(rows);
    if (rows.length < pageSize) break;
    offset += pageSize;
  }
  return all;
}

// --- State ---------------------------------------------------------------
const state = {
  events: [], facilities: [], cameras: [], conditions: [],
  relevant: new Map(), // event id -> { distance, facilities: [] }
  classes: new Set(Object.keys(CLASS_COLORS)),
  provinces: new Set(),
  search: "", nearOnly: false, fullOnly: false, scheduledOnly: false,
  ageHours: 24, importance: "high",
  sort: "priority",
};

let map;
let popup;
let autoRefreshTimer = null;

// Most recent timestamp we know for an event, in ms (or null).
function eventTimeMs(e) {
  const t = e.last_updated || e.reported_at || e.starts_at;
  return t ? new Date(t).getTime() : null;
}

// Impact tier used by the "Importance" filter to cut low-signal noise.
// A full closure or accident is always Critical regardless of event_class.
function importanceOf(e) {
  if (e.is_full_closure || e.event_class === "accident") return "critical";
  const r = e.restrictions || {};
  const truckRestricted = r.weight || r.height || r.width || r.length;
  if (e.event_class === "closure" || e.event_class === "restriction" ||
      state.relevant.has(e.id) || truckRestricted) return "high";
  return "low";
}

// --- Data load -----------------------------------------------------------
async function loadData() {
  const [events, facilities, relevant] = await Promise.all([
    restAll("road_events",
      "id,source,province,event_class,road_number,roadway_name,is_full_closure,is_scheduled,severity,headline,description,direction,restrictions,starts_at,planned_end_at,last_updated,lat,lon"),
    restAll("facilities", "id,name,type,region,corridor,priority,radius_km,lat,lon"),
    restAll("relevant_road_events", "id,distance_km,facility_name"),
  ]);
  state.events = events.filter((e) => e.lat != null && e.lon != null);
  state.facilities = facilities;
  state.provinces = new Set(state.events.map((e) => e.province));

  const rel = new Map();
  for (const r of relevant) {
    const cur = rel.get(r.id);
    if (!cur || r.distance_km < cur.distance) rel.set(r.id, { distance: r.distance_km, facilities: [r.facility_name] });
    else cur.facilities.push(r.facility_name);
  }
  state.relevant = rel;

  // Cameras + conditions are heavier; load lazily but in background.
  restAll("cameras", "id,province,title,roadway,lat,lon,views").then((c) => {
    state.cameras = c.filter((x) => x.lat != null && x.lon != null);
    if (map && map.getSource("cameras")) map.getSource("cameras").setData(toFC(state.cameras, "camera"));
  });
  restAll("road_conditions", "id,province,roadway_name,road_number,condition,lat,lon,last_updated").then((c) => {
    state.conditions = c.filter((x) => x.lat != null && x.lon != null);
    if (map && map.getSource("conditions")) map.getSource("conditions").setData(toFC(state.conditions, "condition"));
  });
}

// --- GeoJSON helpers -----------------------------------------------------
function toFC(rows, kind) {
  return {
    type: "FeatureCollection",
    features: rows.map((r) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [r.lon, r.lat] },
      properties: { ...r, kind },
    })),
  };
}

function eventFeatures() {
  return {
    type: "FeatureCollection",
    features: filteredEvents().map((e) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [e.lon, e.lat] },
      properties: {
        id: e.id, cls: e.event_class, full: e.is_full_closure,
        label: e.road_number || e.roadway_name || "",
      },
    })),
  };
}

// --- Filtering -----------------------------------------------------------
function filteredEvents() {
  const q = state.search.toLowerCase();
  return state.events.filter((e) => {
    if (!state.classes.has(e.event_class)) return false;
    if (!state.provinces.has(e.province)) return false;
    if (state.fullOnly && !e.is_full_closure) return false;
    if (state.scheduledOnly && !e.is_scheduled) return false;
    if (state.nearOnly && !state.relevant.has(e.id)) return false;
    const imp = importanceOf(e);
    if (state.importance === "critical" && imp !== "critical") return false;
    if (state.importance === "high" && imp === "low") return false;
    // Recency: drop stale past events, but never hide ongoing critical ones
    // (a full closure that started weeks ago may still be active) or future ones.
    if (state.ageHours > 0 && imp !== "critical") {
      const ms = eventTimeMs(e);
      if (ms != null && ms <= Date.now() && Date.now() - ms > state.ageHours * 3600000) return false;
    }
    if (q) {
      const hay = `${e.roadway_name || ""} ${e.road_number || ""} ${e.description || ""} ${e.headline || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function sortEvents(list) {
  const byDist = (e) => (state.relevant.get(e.id)?.distance ?? 1e9);
  const cmp = {
    priority: (a, b) =>
      (b.is_full_closure - a.is_full_closure) ||
      (CLASS_RANK[a.event_class] - CLASS_RANK[b.event_class]) ||
      (byDist(a) - byDist(b)),
    distance: (a, b) => byDist(a) - byDist(b),
    updated: (a, b) => new Date(b.last_updated || 0) - new Date(a.last_updated || 0),
  }[state.sort];
  return [...list].sort(cmp);
}

// --- Rendering -----------------------------------------------------------
function relTime(ts) {
  if (!ts) return "";
  const d = (Date.now() - new Date(ts)) / 36e5;
  if (d < 1) return `${Math.round(d * 60)}m ago`;
  if (d < 48) return `${Math.round(d)}h ago`;
  return `${Math.round(d / 24)}d ago`;
}

function apply() {
  const list = sortEvents(filteredEvents());

  if (map.getSource("events")) map.getSource("events").setData(eventFeatures());

  // Counters
  const closures = list.filter((e) => e.event_class === "closure" || e.is_full_closure).length;
  const accidents = list.filter((e) => e.event_class === "accident").length;
  document.getElementById("counters").innerHTML =
    `<span><span class="num">${list.length}</span> events</span>` +
    `<span class="closure"><span class="num">${closures}</span> closures</span>` +
    `<span class="accident"><span class="num">${accidents}</span> accidents</span>` +
    `<span><span class="num">${state.relevant.size}</span> near facilities</span>`;

  // List
  document.getElementById("list-count").textContent = `${list.length} events`;
  const ul = document.getElementById("event-list");
  ul.innerHTML = "";
  for (const e of list.slice(0, 400)) {
    const color = CLASS_COLORS[e.event_class] || "#868e96";
    const near = state.relevant.get(e.id);
    const li = document.createElement("li");
    li.className = "event-item";
    li.style.borderLeftColor = color;
    li.innerHTML =
      `<div class="row1"><span class="road">${esc(e.road_number ? "Hwy " + e.road_number : e.roadway_name || "—")}</span>` +
      `<span class="badge" style="background:${color}">${CLASS_LABELS[e.event_class]}</span></div>` +
      `<div class="desc">${esc(e.headline || e.description || "")}</div>` +
      `<div class="meta">` +
      `<span>${PROVINCE_ABBR[e.province] || e.province}</span>` +
      (e.is_full_closure ? `<span class="full">FULL CLOSURE</span>` : "") +
      (e.is_scheduled ? `<span>scheduled</span>` : "") +
      (near ? `<span>${near.distance} km · ${esc(near.facilities[0] || "")}</span>` : "") +
      (e.last_updated ? `<span>${relTime(e.last_updated)}</span>` : "") +
      `</div>`;
    li.onclick = () => focusEvent(e);
    ul.appendChild(li);
  }
}

function focusEvent(e) {
  map.flyTo({ center: [e.lon, e.lat], zoom: 9 });
  showEventPopup(e, [e.lon, e.lat]);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// --- Popups --------------------------------------------------------------
function showEventPopup(e, lngLat) {
  const r = e.restrictions || {};
  const restr = Object.entries(r).map(([k, v]) => `${k}: ${v}`).join(", ");
  const near = state.relevant.get(e.id);
  const html =
    `<div class="popup-title">${esc(e.road_number ? "Highway " + e.road_number : e.roadway_name || "Road event")}</div>` +
    `<div class="popup-row"><b>${CLASS_LABELS[e.event_class]}</b>${e.is_full_closure ? " · <span style='color:#d6336c'>FULL CLOSURE</span>" : ""}</div>` +
    (e.description ? `<div class="popup-row">${esc(e.description)}</div>` : "") +
    (e.direction ? `<div class="popup-row">Direction: ${esc(e.direction)}</div>` : "") +
    (restr ? `<div class="popup-row">Restrictions: ${esc(restr)}</div>` : "") +
    (near ? `<div class="popup-row">${near.distance} km from ${esc(near.facilities.join(", "))}</div>` : "") +
    `<div class="popup-row" style="color:#8893a3">${PROVINCE_ABBR[e.province] || e.province}` +
    (e.last_updated ? ` · ${relTime(e.last_updated)}` : "") + `</div>`;
  popup.setLngLat(lngLat).setHTML(html).addTo(map);
}

// --- Map setup -----------------------------------------------------------
const BASE_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: ["a", "b", "c"].map((s) => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`),
      tileSize: 256,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [{ id: "carto", type: "raster", source: "carto" }],
};

function addLayers() {
  map.addSource("events", { type: "geojson", data: eventFeatures() });
  map.addSource("facilities", { type: "geojson", data: toFC(state.facilities, "facility") });
  map.addSource("cameras", { type: "geojson", data: toFC(state.cameras, "camera") });
  map.addSource("conditions", { type: "geojson", data: toFC(state.conditions, "condition") });

  map.addLayer({
    id: "conditions-layer", type: "circle", source: "conditions",
    layout: { visibility: "none" },
    paint: { "circle-radius": 3, "circle-color": "#0ca678", "circle-opacity": 0.5 },
  });
  map.addLayer({
    id: "cameras-layer", type: "circle", source: "cameras",
    layout: { visibility: "none" },
    paint: { "circle-radius": 3.5, "circle-color": "#3b5bdb", "circle-opacity": 0.7,
      "circle-stroke-width": 1, "circle-stroke-color": "#fff" },
  });
  map.addLayer({
    id: "facilities-layer", type: "circle", source: "facilities",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["get", "priority"], 1, 4, 5, 8],
      "circle-color": "#a98467", "circle-opacity": 0.85,
      "circle-stroke-width": 1, "circle-stroke-color": "#ffffff",
    },
  });
  const colorMatch = ["match", ["get", "cls"]];
  for (const [k, v] of Object.entries(CLASS_COLORS)) colorMatch.push(k, v);
  colorMatch.push("#868e96");
  map.addLayer({
    id: "events-layer", type: "circle", source: "events",
    paint: {
      "circle-radius": ["case", ["get", "full"], 8, 5.5],
      "circle-color": colorMatch,
      "circle-stroke-width": ["case", ["get", "full"], 2, 1],
      "circle-stroke-color": "#fff", "circle-opacity": 0.9,
    },
  });

  map.on("click", "events-layer", (ev) => {
    const id = ev.features[0].properties.id;
    const e = state.events.find((x) => x.id === id);
    if (e) showEventPopup(e, ev.lngLat);
  });
  map.on("click", "facilities-layer", (ev) => {
    const p = ev.features[0].properties;
    popup.setLngLat(ev.lngLat).setHTML(
      `<div class="popup-title">${esc(p.name)}</div><div class="popup-row">${esc(p.type || "")}</div>` +
      `<div class="popup-row" style="color:#8893a3">${esc(p.corridor || p.region || "")} · radius ${p.radius_km} km</div>`
    ).addTo(map);
  });
  map.on("click", "cameras-layer", (ev) => {
    const p = ev.features[0].properties;
    const views = p.views ? JSON.parse(p.views) : [];
    const bust = (u) => esc(u) + (u.includes("?") ? "&" : "?") + "_=" + Date.now(); // force a fresh frame
    const others = views.slice(1).map((u, i) =>
      `<a href="${bust(u)}" target="_blank" rel="noopener">View ${i + 2}</a>`).join(" · ");
    popup.setLngLat(ev.lngLat).setHTML(
      `<div class="popup-title">${esc(p.title || "Camera")}</div>` +
      (views[0]
        ? `<a class="popup-cam" href="${bust(views[0])}" target="_blank" rel="noopener"><img src="${bust(views[0])}" alt="camera" /></a>`
        : "") +
      `<div class="popup-row" style="color:#8893a3">Live snapshot · refreshes ~1 min · click to open full size</div>` +
      (others ? `<div class="popup-row">More angles: ${others}</div>` : "")
    ).addTo(map);
  });
  map.on("click", "conditions-layer", (ev) => {
    const p = ev.features[0].properties;
    popup.setLngLat(ev.lngLat).setHTML(
      `<div class="popup-title">${esc(p.road_number ? "Highway " + p.road_number : p.roadway_name || "Road condition")}</div>` +
      `<div class="popup-row">${esc(p.condition || "")}</div>`
    ).addTo(map);
  });
  for (const layer of ["events-layer", "facilities-layer", "cameras-layer", "conditions-layer"]) {
    map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
  }
}

// --- UI wiring -----------------------------------------------------------
function buildChips(containerId, items, set, labelFn, colorFn) {
  const c = document.getElementById(containerId);
  c.innerHTML = "";
  for (const item of items) {
    const chip = document.createElement("span");
    chip.className = "chip active";
    chip.style.background = colorFn ? colorFn(item) : "#495057";
    chip.innerHTML = (colorFn ? `<span class="dot" style="background:#fff"></span>` : "") + labelFn(item);
    chip.onclick = () => {
      if (set.has(item)) { set.delete(item); chip.classList.remove("active"); chip.style.background = "#fff"; chip.style.color = "#1c2330"; }
      else { set.add(item); chip.classList.add("active"); chip.style.background = colorFn ? colorFn(item) : "#495057"; chip.style.color = "#fff"; }
      apply();
    };
    c.appendChild(chip);
  }
}

function wireUI() {
  buildChips("class-filters", Object.keys(CLASS_COLORS), state.classes, (k) => CLASS_LABELS[k], (k) => CLASS_COLORS[k]);
  buildChips("province-filters", [...state.provinces].sort(), state.provinces, (p) => PROVINCE_ABBR[p] || p);

  const bind = (id, key) => document.getElementById(id).addEventListener("change", (e) => { state[key] = e.target.checked; apply(); });
  bind("near-only", "nearOnly");
  bind("full-only", "fullOnly");
  bind("scheduled-only", "scheduledOnly");

  document.getElementById("search").addEventListener("input", (e) => { state.search = e.target.value; apply(); });
  document.getElementById("sort").addEventListener("change", (e) => { state.sort = e.target.value; apply(); });
  document.getElementById("age").addEventListener("change", (e) => { state.ageHours = Number(e.target.value); apply(); });
  document.getElementById("importance").addEventListener("change", (e) => { state.importance = e.target.value; apply(); });
  document.getElementById("autorefresh").addEventListener("change", (e) => setAutoRefresh(e.target.checked));

  const layerToggle = (id, layer) => document.getElementById(id).addEventListener("change", (e) => {
    map.setLayoutProperty(layer, "visibility", e.target.checked ? "visible" : "none");
  });
  layerToggle("layer-events", "events-layer");
  layerToggle("layer-facilities", "facilities-layer");
  layerToggle("layer-cameras", "cameras-layer");
  layerToggle("layer-conditions", "conditions-layer");

  document.getElementById("refresh").onclick = () => init(true);
}

function setAutoRefresh(on) {
  if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
  if (on) {
    autoRefreshTimer = setInterval(() => init(true), 15 * 60 * 1000);
    flash("Auto-refresh on (every 15 min)");
  } else {
    flash("Auto-refresh off");
  }
}

function flash(msg) {
  const s = document.getElementById("status");
  s.textContent = msg; s.classList.add("show");
  setTimeout(() => s.classList.remove("show"), 1800);
}

// --- Boot ----------------------------------------------------------------
async function init(isRefresh) {
  try {
    document.getElementById("status").classList.add("show");
    document.getElementById("status").textContent = "Loading…";
    await loadData();
    if (!map) {
      map = new maplibregl.Map({ container: "map", style: BASE_STYLE, center: [-96, 56], zoom: 3.4 });
      popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" });
      map.addControl(new maplibregl.NavigationControl(), "top-right");
      await new Promise((res) => map.on("load", res));
      addLayers();
      wireUI();
    } else {
      map.getSource("facilities").setData(toFC(state.facilities, "facility"));
    }
    apply();
    flash(isRefresh ? "Data refreshed" : `Loaded ${state.events.length} highway events`);
  } catch (err) {
    document.getElementById("status").textContent = "Error: " + err.message;
    console.error(err);
  }
}

init(false);
