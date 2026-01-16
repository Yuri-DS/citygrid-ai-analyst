#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CityGrid synthetic dataset generator.

Creates:
- SQLite DB: data/citygrid.db
- Optional CSV exports: data/exports/*.csv
- RAG docs: docs_workspace/*.md
- Generation log: outputs/generation_log.txt

Deterministic by seed. Hourly time series for last N days.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# -----------------------------
# Config / enums
# -----------------------------

CITY_LAT_MIN, CITY_LAT_MAX = 55.60, 55.90
CITY_LON_MIN, CITY_LON_MAX = 37.40, 37.90

OBJECT_TYPES = ("substation", "streetlight", "road_segment", "stop", "parking", "building")
SENSOR_TYPES = ("noise_db", "pm25", "traffic_intensity", "temp_c")
SENSOR_UNITS = {
    "noise_db": "dB",
    "pm25": "ug/m3",
    "traffic_intensity": "veh/h",
    "temp_c": "C",
}
METER_TYPES = ("electricity_kwh", "water_m3", "heating_gcal")
METER_UNITS = {
    "electricity_kwh": "kWh",
    "water_m3": "m3",
    "heating_gcal": "Gcal",
}

EVENT_TYPES = ("concert", "fair", "football", "parade", "repair")
REQUEST_CATEGORIES = (
    "noise_complaint",
    "pothole",
    "broken_streetlight",
    "water_leak",
    "heating_issue",
    "parking_issue",
)
REQUEST_PRIORITIES = ("low", "medium", "high")

SCALE_PRESETS = {
    "small": {
        "districts": 10,
        "city_objects": 1000,
        "sensors": 1800,
        "smart_meters": 900,
        "municipal_events": 160,
        "citizen_requests": 40000,
        "public_transport_trips": 200000,
    },
    "medium": {
        "districts": 10,
        "city_objects": 2000,
        "sensors": 3500,
        "smart_meters": 1600,
        "municipal_events": 350,
        "citizen_requests": 70000,
        "public_transport_trips": 300000,
    },
    "large": {
        "districts": 10,
        "city_objects": 2000,
        "sensors": 4500,
        "smart_meters": 2200,
        "municipal_events": 500,
        "citizen_requests": 90000,
        "public_transport_trips": 450000,
    },
}


# -----------------------------
# Helpers
# -----------------------------

def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def iso_no_tz(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def gaussian_bump(x: np.ndarray, mu: float, sigma: float, amp: float) -> np.ndarray:
    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def weekend_factor(dow: np.ndarray, weekend_drop: float) -> np.ndarray:
    is_weekend = (dow >= 5).astype(np.float32)
    return 1.0 - weekend_drop * is_weekend


@dataclass
class District:
    district_id: int
    name: str
    population: int
    area_km2: float
    center_lat: float
    center_lon: float
    is_central: bool
    is_entertainment: bool


# -----------------------------
# DB schema
# -----------------------------

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS public_transport_trips;
DROP TABLE IF EXISTS citizen_requests;
DROP TABLE IF EXISTS municipal_events;
DROP TABLE IF EXISTS meter_readings;
DROP TABLE IF EXISTS sensor_readings;
DROP TABLE IF EXISTS smart_meters;
DROP TABLE IF EXISTS sensors;
DROP TABLE IF EXISTS city_objects;
DROP TABLE IF EXISTS districts;

CREATE TABLE districts (
  district_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  population INTEGER NOT NULL,
  area_km2 REAL NOT NULL,
  center_lat REAL NOT NULL,
  center_lon REAL NOT NULL
);

CREATE TABLE city_objects (
  object_id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL,
  object_type TEXT NOT NULL CHECK(object_type IN ('substation','streetlight','road_segment','stop','parking','building')),
  name TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  install_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active','inactive')),
  FOREIGN KEY(district_id) REFERENCES districts(district_id)
);

CREATE TABLE sensors (
  sensor_id INTEGER PRIMARY KEY,
  object_id INTEGER NOT NULL,
  sensor_type TEXT NOT NULL CHECK(sensor_type IN ('noise_db','pm25','traffic_intensity','temp_c')),
  unit TEXT NOT NULL,
  is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
  FOREIGN KEY(object_id) REFERENCES city_objects(object_id)
);

CREATE TABLE smart_meters (
  meter_id INTEGER PRIMARY KEY,
  object_id INTEGER NOT NULL,
  utility_type TEXT NOT NULL CHECK(utility_type IN ('electricity_kwh','water_m3','heating_gcal')),
  unit TEXT NOT NULL,
  is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
  FOREIGN KEY(object_id) REFERENCES city_objects(object_id)
);

CREATE TABLE sensor_readings (
  reading_id INTEGER PRIMARY KEY,
  sensor_id INTEGER NOT NULL,
  ts TEXT NOT NULL,
  value REAL NOT NULL,
  quality_flag TEXT NOT NULL CHECK(quality_flag IN ('ok','missing','suspect')),
  FOREIGN KEY(sensor_id) REFERENCES sensors(sensor_id)
);

CREATE TABLE meter_readings (
  reading_id INTEGER PRIMARY KEY,
  meter_id INTEGER NOT NULL,
  ts TEXT NOT NULL,
  value REAL NOT NULL,
  is_peak INTEGER NOT NULL CHECK(is_peak IN (0,1)),
  FOREIGN KEY(meter_id) REFERENCES smart_meters(meter_id)
);

CREATE TABLE municipal_events (
  event_id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('concert','fair','football','parade','repair')),
  start_ts TEXT NOT NULL,
  end_ts TEXT NOT NULL,
  attendance_est INTEGER NOT NULL,
  FOREIGN KEY(district_id) REFERENCES districts(district_id)
);

CREATE TABLE citizen_requests (
  request_id INTEGER PRIMARY KEY,
  district_id INTEGER NOT NULL,
  object_id INTEGER NULL,
  category TEXT NOT NULL CHECK(category IN ('noise_complaint','pothole','broken_streetlight','water_leak','heating_issue','parking_issue')),
  created_ts TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','in_progress','resolved')),
  resolved_ts TEXT NULL,
  resolution_hours REAL NULL,
  priority TEXT NOT NULL CHECK(priority IN ('low','medium','high')),
  FOREIGN KEY(district_id) REFERENCES districts(district_id),
  FOREIGN KEY(object_id) REFERENCES city_objects(object_id)
);

CREATE TABLE public_transport_trips (
  trip_id INTEGER PRIMARY KEY,
  route_no TEXT NOT NULL,
  vehicle_id TEXT NOT NULL,
  stop_object_id INTEGER NOT NULL,
  scheduled_ts TEXT NOT NULL,
  actual_ts TEXT NOT NULL,
  passenger_est INTEGER NOT NULL,
  FOREIGN KEY(stop_object_id) REFERENCES city_objects(object_id)
);

CREATE INDEX idx_sensor_readings_sensor_ts ON sensor_readings(sensor_id, ts);
CREATE INDEX idx_meter_readings_meter_ts ON meter_readings(meter_id, ts);
CREATE INDEX idx_sensors_object_type ON sensors(object_id, sensor_type);
CREATE INDEX idx_meters_object_type ON smart_meters(object_id, utility_type);
CREATE INDEX idx_requests_district_ts ON citizen_requests(district_id, created_ts);
CREATE INDEX idx_requests_object_ts ON citizen_requests(object_id, created_ts);
CREATE INDEX idx_events_district_start ON municipal_events(district_id, start_ts);
CREATE INDEX idx_trips_route_sched ON public_transport_trips(route_no, scheduled_ts);
CREATE INDEX idx_objects_district_type ON city_objects(district_id, object_type);
"""


# -----------------------------
# CLI
# -----------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate CityGrid synthetic dataset (SQLite + docs).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--scale", choices=sorted(SCALE_PRESETS.keys()), default="medium")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--step-hours", type=int, default=1)
    p.add_argument("--db-path", type=str, default="data/citygrid.db")
    p.add_argument("--export-csv", action="store_true")
    p.add_argument("--exports-dir", type=str, default="data/exports")
    p.add_argument("--docs-dir", type=str, default="docs_workspace")
    p.add_argument("--log-path", type=str, default="outputs/generation_log.txt")
    return p.parse_args(argv)


def connect_db(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def insert_many(conn: sqlite3.Connection, sql: str, rows: Iterable[Tuple], chunk: int = 50000) -> int:
    cur = conn.cursor()
    n = 0
    buf: List[Tuple] = []
    for r in rows:
        buf.append(r)
        if len(buf) >= chunk:
            cur.executemany(sql, buf)
            n += len(buf)
            buf.clear()
    if buf:
        cur.executemany(sql, buf)
        n += len(buf)
    return n


def export_table_to_csv(conn: sqlite3.Connection, table: str, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        while True:
            rows = cur.fetchmany(10000)
            if not rows:
                break
            w.writerows(rows)


# -----------------------------
# Generation
# -----------------------------

def gen_districts(rng: np.random.Generator, n: int) -> List[District]:
    central_ids = set(rng.choice(np.arange(1, n + 1), size=max(2, n // 4), replace=False).tolist())
    ent_ids = set(rng.choice(list(central_ids), size=1, replace=False).tolist())

    districts: List[District] = []
    for i in range(1, n + 1):
        center_lat = float(rng.uniform(CITY_LAT_MIN, CITY_LAT_MAX))
        center_lon = float(rng.uniform(CITY_LON_MIN, CITY_LON_MAX))
        pop = int(rng.integers(25000, 180000))
        area = float(rng.uniform(6.0, 35.0))
        districts.append(
            District(
                district_id=i,
                name=f"District {i:02d}",
                population=pop,
                area_km2=area,
                center_lat=center_lat,
                center_lon=center_lon,
                is_central=(i in central_ids),
                is_entertainment=(i in ent_ids),
            )
        )
    return districts


def gen_city_objects(
    rng: np.random.Generator,
    districts: List[District],
    n_objects: int,
) -> Tuple[List[Tuple], Dict[int, int], Dict[int, int]]:
    type_probs = np.array([0.03, 0.30, 0.22, 0.18, 0.12, 0.15], dtype=float)
    type_probs = type_probs / type_probs.sum()

    district_ids = np.array([d.district_id for d in districts])
    pop = np.array([d.population for d in districts], dtype=float)
    dist_probs = pop / pop.sum()

    central = [d.district_id for d in districts if d.is_central]

    rows: List[Tuple] = []
    obj2dist: Dict[int, int] = {}
    obj2type: Dict[int, int] = {}

    for object_id in range(1, n_objects + 1):
        did = int(rng.choice(district_ids, p=dist_probs))
        otype = str(rng.choice(OBJECT_TYPES, p=type_probs))

        if otype in ("stop", "parking"):
            if rng.random() < 0.60:
                did = int(rng.choice(central))

        d = districts[did - 1]
        lat = float(rng.normal(loc=d.center_lat, scale=0.015))
        lon = float(rng.normal(loc=d.center_lon, scale=0.020))
        lat = clamp(lat, CITY_LAT_MIN, CITY_LAT_MAX)
        lon = clamp(lon, CITY_LON_MIN, CITY_LON_MAX)

        install_dt = datetime.now().date() - timedelta(days=int(rng.integers(30, 3650)))
        install_date = install_dt.strftime("%Y-%m-%d")
        status = "active" if rng.random() < 0.92 else "inactive"
        name = f"{otype.capitalize()} {object_id:05d}"

        rows.append((object_id, did, otype, name, lat, lon, install_date, status))
        obj2dist[object_id] = did
        obj2type[object_id] = OBJECT_TYPES.index(otype)

    return rows, obj2dist, obj2type


def gen_sensors(
    rng: np.random.Generator,
    districts: List[District],
    objects_rows: List[Tuple],
    obj2dist: Dict[int, int],
    n_sensors: int,
) -> Tuple[List[Tuple], Dict[int, int], Dict[int, str]]:
    object_ids = np.array([r[0] for r in objects_rows], dtype=int)

    obj_type = np.array([OBJECT_TYPES.index(r[2]) for r in objects_rows], dtype=int)
    base_w = np.ones_like(obj_type, dtype=float)
    for i, t in enumerate(obj_type):
        if OBJECT_TYPES[t] in ("road_segment", "stop", "streetlight"):
            base_w[i] = 2.0
        if OBJECT_TYPES[t] == "building":
            base_w[i] = 1.2
        if OBJECT_TYPES[t] == "substation":
            base_w[i] = 0.8
    base_w = base_w / base_w.sum()

    rows: List[Tuple] = []
    sensor2dist: Dict[int, int] = {}
    sensor2type: Dict[int, str] = {}
    sid = 1

    obj_by_dist: Dict[int, np.ndarray] = {}
    for d in districts:
        obj_by_dist[d.district_id] = np.array(
            [oid for oid in object_ids if obj2dist[int(oid)] == d.district_id],
            dtype=int,
        )

    # Ensure coverage: 1 per sensor type per district
    for d in districts:
        oids = obj_by_dist[d.district_id]
        if len(oids) == 0:
            continue
        for st in SENSOR_TYPES:
            oid = int(rng.choice(oids))
            is_active = 1 if rng.random() < 0.95 else 0
            rows.append((sid, oid, st, SENSOR_UNITS[st], is_active))
            sensor2dist[sid] = d.district_id
            sensor2type[sid] = st
            sid += 1

    remaining = max(0, n_sensors - len(rows))
    sensor_type_probs = np.array([0.28, 0.18, 0.32, 0.22], dtype=float)
    sensor_type_probs = sensor_type_probs / sensor_type_probs.sum()

    for _ in range(remaining):
        oid = int(rng.choice(object_ids, p=base_w))
        st = str(rng.choice(SENSOR_TYPES, p=sensor_type_probs))
        is_active = 1 if rng.random() < 0.94 else 0
        rows.append((sid, oid, st, SENSOR_UNITS[st], is_active))
        sensor2dist[sid] = obj2dist[oid]
        sensor2type[sid] = st
        sid += 1

    return rows, sensor2dist, sensor2type


def gen_meters(
    rng: np.random.Generator,
    objects_rows: List[Tuple],
    obj2type: Dict[int, int],
    n_meters: int,
) -> Tuple[List[Tuple], Dict[int, int], Dict[int, str]]:
    object_ids = np.array([r[0] for r in objects_rows], dtype=int)
    obj_type = np.array([obj2type[int(oid)] for oid in object_ids], dtype=int)

    w = np.ones_like(obj_type, dtype=float)
    for i, t in enumerate(obj_type):
        tname = OBJECT_TYPES[int(t)]
        if tname == "building":
            w[i] = 3.0
        elif tname == "substation":
            w[i] = 1.5
        elif tname == "road_segment":
            w[i] = 1.1
        else:
            w[i] = 0.6
    w = w / w.sum()

    utility_probs = np.array([0.46, 0.28, 0.26], dtype=float)
    utility_probs = utility_probs / utility_probs.sum()

    rows: List[Tuple] = []
    meter2obj: Dict[int, int] = {}
    meter2type: Dict[int, str] = {}

    for mid in range(1, n_meters + 1):
        oid = int(rng.choice(object_ids, p=w))
        ut = str(rng.choice(METER_TYPES, p=utility_probs))
        is_active = 1 if rng.random() < 0.97 else 0
        rows.append((mid, oid, ut, METER_UNITS[ut], is_active))
        meter2obj[mid] = oid
        meter2type[mid] = ut

    return rows, meter2obj, meter2type


def make_time_index(days: int, step_hours: int) -> Tuple[List[datetime], np.ndarray, np.ndarray, np.ndarray]:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    end = now
    start = end - timedelta(days=days)

    dts: List[datetime] = []
    cur = start
    while cur <= end:
        dts.append(cur)
        cur += timedelta(hours=step_hours)

    hours = np.array([dt.hour for dt in dts], dtype=np.int16)
    dow = np.array([dt.weekday() for dt in dts], dtype=np.int16)
    day_index = np.array([(dt - dts[0]).days for dt in dts], dtype=np.int32)
    return dts, hours, dow, day_index


def gen_municipal_events(
    rng: np.random.Generator,
    districts: List[District],
    dts: List[datetime],
    n_events: int,
) -> List[Tuple]:
    district_ids = np.array([d.district_id for d in districts], dtype=int)
    w = np.array([1.6 if d.is_central else 1.0 for d in districts], dtype=float)
    w = w / w.sum()

    max_start_idx = max(1, len(dts) - 25)

    rows: List[Tuple] = []
    for eid in range(1, n_events + 1):
        did = int(rng.choice(district_ids, p=w))
        et = str(rng.choice(EVENT_TYPES, p=np.array([0.20, 0.18, 0.20, 0.12, 0.30])))

        sidx = int(rng.integers(0, max_start_idx))
        start = dts[sidx]
        dur_h = int(rng.integers(2, 10) if et != "repair" else rng.integers(8, 48))
        end = start + timedelta(hours=dur_h)

        base_att = int(rng.integers(300, 8000))
        if et == "football":
            base_att = int(rng.integers(1500, 25000))
        if et == "parade":
            base_att = int(rng.integers(2000, 40000))
        if et == "repair":
            base_att = int(rng.integers(20, 400))

        name = f"{et.capitalize()} #{eid:04d}"
        rows.append((eid, did, name, et, iso_no_tz(start), iso_no_tz(end), base_att))

    return rows


def district_time_series(
    rng: np.random.Generator,
    districts: List[District],
    dts: List[datetime],
    hours: np.ndarray,
    dow: np.ndarray,
    day_index: np.ndarray,
    events_rows: List[Tuple],
) -> Dict[int, Dict[str, np.ndarray]]:
    T = len(dts)
    xh = hours.astype(np.float32)
    xdow = dow.astype(np.int16)

    diurnal = np.sin(2.0 * np.pi * (xh / 24.0 - 0.25))
    night = ((xh < 6) | (xh >= 23)).astype(np.float32)

    morning_peak = gaussian_bump(xh, mu=8.5, sigma=1.3, amp=1.0)
    evening_peak = gaussian_bump(xh, mu=18.0, sigma=1.6, amp=1.1)
    traffic_profile = 0.35 + 0.75 * morning_peak + 0.85 * evening_peak

    w_factor = weekend_factor(xdow, weekend_drop=0.22)

    trend = (day_index.astype(np.float32) - day_index.min()) / max(1.0, float(day_index.max() - day_index.min()))

    events_by_dist: Dict[int, List[Tuple]] = {d.district_id: [] for d in districts}
    for row in events_rows:
        _, did, _, et, start_s, end_s, _ = row
        events_by_dist[int(did)].append((et, start_s, end_s))

    n_smog = int(rng.integers(1, 4))
    smog_periods: List[Tuple[int, int, Optional[set]]] = []
    for _ in range(n_smog):
        s = int(rng.integers(0, max(1, T - 72)))
        dur = int(rng.integers(24, 72))
        e = min(T - 1, s + dur)
        if rng.random() < 0.55:
            affected = None
        else:
            k = int(rng.integers(2, max(3, len(districts) // 2)))
            affected = set(rng.choice([d.district_id for d in districts], size=k, replace=False).tolist())
        smog_periods.append((s, e, affected))

    out: Dict[int, Dict[str, np.ndarray]] = {}

    for d in districts:
        base = float(rng.uniform(-2.0, 6.0))
        seasonal = (trend - 0.5) * float(rng.uniform(-6.0, 6.0))
        temp = base + 8.0 * diurnal + seasonal + rng.normal(0.0, 1.2, size=T)
        temp = np.clip(temp, -12.0, 27.0)

        central_boost = 1.25 if d.is_central else 1.0
        traffic_base = float(rng.uniform(120.0, 320.0)) * central_boost
        traffic = traffic_base * traffic_profile * w_factor
        traffic = traffic + rng.normal(0.0, traffic_base * 0.08, size=T)
        traffic = np.clip(traffic, 0.0, None)

        ent_night_boost = (10.0 if d.is_entertainment else 0.0) * night
        noise = 38.0 + 0.06 * traffic + ent_night_boost + rng.normal(0.0, 2.2, size=T)
        noise = np.clip(noise, 32.0, 92.0)

        pm = 9.0 + 0.07 * traffic + rng.normal(0.0, 2.5, size=T)
        for s, e, affected in smog_periods:
            if (affected is None) or (d.district_id in affected):
                pm[s : e + 1] += float(rng.uniform(18.0, 55.0))
        pm = np.clip(pm, 4.0, 140.0)

        # Apply municipal events boosts
        for et, start_s, end_s in events_by_dist[d.district_id]:
            start_dt = datetime.strptime(start_s, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_s, "%Y-%m-%d %H:%M:%S")
            sidx = int((start_dt - dts[0]).total_seconds() // 3600)
            eidx = int((end_dt - dts[0]).total_seconds() // 3600)
            sidx = max(0, min(T - 1, sidx))
            eidx = max(0, min(T - 1, eidx))
            if eidx <= sidx:
                continue
            if et == "repair":
                traffic[sidx : eidx + 1] *= float(rng.uniform(1.10, 1.30))
                noise[sidx : eidx + 1] += float(rng.uniform(2.0, 8.0))
            else:
                traffic[sidx : eidx + 1] *= float(rng.uniform(1.15, 1.40))
                noise[sidx : eidx + 1] += float(rng.uniform(10.0, 25.0))

        traffic = np.clip(traffic, 0.0, None)
        noise = np.clip(noise, 32.0, 95.0)
        pm = np.clip(pm, 4.0, 160.0)

        out[d.district_id] = {
            "temp_c": temp.astype(np.float32),
            "traffic_intensity": traffic.astype(np.float32),
            "noise_db": noise.astype(np.float32),
            "pm25": pm.astype(np.float32),
        }

    return out


def generate_docs(docs_dir: Path) -> None:
    ensure_dir(docs_dir)

    data_dict = """# CityGrid - Data Dictionary

This workspace describes the synthetic dataset CityGrid (smart city) stored in SQLite.

## Tables

### districts
- district_id (PK)
- name
- population
- area_km2
- center_lat, center_lon

### city_objects
- object_id (PK)
- district_id (FK -> districts)
- object_type: substation, streetlight, road_segment, stop, parking, building
- name
- lat, lon
- install_date (YYYY-MM-DD)
- status: active | inactive

### sensors
- sensor_id (PK)
- object_id (FK -> city_objects)
- sensor_type: noise_db | pm25 | traffic_intensity | temp_c
- unit
- is_active: 0/1

### smart_meters
- meter_id (PK)
- object_id (FK -> city_objects)
- utility_type: electricity_kwh | water_m3 | heating_gcal
- unit
- is_active: 0/1

### sensor_readings
- reading_id (PK)
- sensor_id (FK -> sensors)
- ts: YYYY-MM-DD HH:MM:SS
- value
- quality_flag: ok | missing | suspect

### meter_readings
- reading_id (PK)
- meter_id (FK -> smart_meters)
- ts
- value
- is_peak: 0/1

### municipal_events
- event_id (PK)
- district_id (FK)
- name
- event_type: concert | fair | football | parade | repair
- start_ts, end_ts
- attendance_est

### citizen_requests
- request_id (PK)
- district_id (FK)
- object_id (nullable FK -> city_objects)
- category: noise_complaint | pothole | broken_streetlight | water_leak | heating_issue | parking_issue
- created_ts
- status: open | in_progress | resolved
- resolved_ts (nullable)
- resolution_hours (nullable)
- priority: low | medium | high

### public_transport_trips
- trip_id (PK)
- route_no
- vehicle_id
- stop_object_id (FK -> city_objects, object_type='stop')
- scheduled_ts
- actual_ts
- passenger_est
"""

    kpi_defs = """# CityGrid - KPI definitions

## Peak consumption (meter_readings.is_peak)
For each meter, is_peak = 1 when hourly consumption is above the meter's 90th percentile over the generated period.

## Punctuality / delay
Delay (minutes) = actual_ts - scheduled_ts.
Delays depend on district traffic intensity and peak hours.

## Request resolution
If status = resolved:
resolved_ts = created_ts + resolution_hours.
Resolution time depends on category and priority.
"""

    sensor_specs = """# CityGrid - Sensor specs

## Sensor types and units
- temp_c: C, typical -12 .. +27
- traffic_intensity: veh/h
- noise_db: dB, typical 32 .. 95
- pm25: ug/m3, typical 4 .. 160

## quality_flag
- ok: normal
- missing: downtime window (value filled with 0 but flagged)
- suspect: rare anomaly spike
"""

    report_tpl = """# CityGrid - Mini report template

## 1. Goal
State the analytical question.

## 2. Data
Period: last N days, hourly.
Tables: sensor_readings, meter_readings, citizen_requests, municipal_events, public_transport_trips.

## 3. Key metrics
- Top districts by requests (last 30 days)
- Noise vs noise complaints (by district)
- Traffic before/after event
- Punctuality by route
- Peaks in utilities

## 4. Findings
Trends, top contributors, anomalies (missing/suspect), event impact.

## 5. Recommendations
Operational actions and monitoring.

## 6. Limitations
Synthetic nature; missing/suspect; synthetic coordinates.
"""

    policy = """# CityGrid - Citizen request handling policy (SLA)

Statuses: open, in_progress, resolved.
Priority: high, medium, low.

Target resolution ranges (hours):
- water_leak: high 2-24, medium 6-72, low 24-168
- heating_issue: high 2-24, medium 6-72, low 24-168
- broken_streetlight: high 6-48, medium 12-96, low 24-168
- pothole: high 12-96, medium 24-168, low 48-240
- noise_complaint: high 2-24, medium 6-72, low 24-168
- parking_issue: high 6-48, medium 12-96, low 24-168
"""

    write_text(docs_dir / "data_dictionary.md", data_dict)
    write_text(docs_dir / "kpi_definitions.md", kpi_defs)
    write_text(docs_dir / "sensor_specs.md", sensor_specs)
    write_text(docs_dir / "report_template.md", report_tpl)
    write_text(docs_dir / "incident_policy.md", policy)


def gen_sensor_readings(
    conn: sqlite3.Connection,
    rng: np.random.Generator,
    sensors_rows: List[Tuple],
    sensor2dist: Dict[int, int],
    sensor2type: Dict[int, str],
    dist_series: Dict[int, Dict[str, np.ndarray]],
    dts: List[datetime],
    missing_rate: Tuple[float, float] = (0.03, 0.07),
    suspect_rate: Tuple[float, float] = (0.01, 0.02),
) -> int:
    T = len(dts)
    ts_str = [iso_no_tz(dt) for dt in dts]

    sensor_ids = np.array([r[0] for r in sensors_rows], dtype=int)

    n_missing = int(len(sensor_ids) * float(rng.uniform(*missing_rate)))
    missing_sensors = set(rng.choice(sensor_ids, size=max(1, n_missing), replace=False).tolist())
    missing_windows: Dict[int, Tuple[int, int]] = {}
    for sid in missing_sensors:
        start = int(rng.integers(0, max(1, T - 48)))
        dur = int(rng.integers(6, 49))
        end = min(T - 1, start + dur)
        missing_windows[int(sid)] = (start, end)

    n_suspect = int(len(sensor_ids) * float(rng.uniform(*suspect_rate)))
    suspect_sensors = set(rng.choice(sensor_ids, size=max(1, n_suspect), replace=False).tolist())
    suspect_points: Dict[int, List[int]] = {}
    for sid in suspect_sensors:
        k = int(rng.integers(2, 8))
        idx = rng.choice(np.arange(T), size=k, replace=False).astype(int).tolist()
        suspect_points[int(sid)] = idx

    cur = conn.cursor()
    insert_sql = "INSERT INTO sensor_readings(sensor_id, ts, value, quality_flag) VALUES (?, ?, ?, ?)"

    total = 0
    buf: List[Tuple] = []
    buf_max = 50000

    for sid, oid, st, unit, is_active in sensors_rows:
        did = sensor2dist[int(sid)]
        base = dist_series[did][st].astype(np.float32)

        if st == "temp_c":
            mult = float(rng.uniform(0.95, 1.05))
            noise = rng.normal(0.0, 0.7, size=T)
            values = base * mult + noise
        elif st == "traffic_intensity":
            mult = float(rng.uniform(0.85, 1.25))
            noise = rng.normal(0.0, max(8.0, float(base.mean()) * 0.10), size=T)
            values = np.clip(base * mult + noise, 0.0, None)
        elif st == "noise_db":
            mult = float(rng.uniform(0.95, 1.08))
            noise = rng.normal(0.0, 1.8, size=T)
            values = np.clip(base * mult + noise, 30.0, 98.0)
        else:  # pm25
            mult = float(rng.uniform(0.90, 1.20))
            noise = rng.normal(0.0, 2.4, size=T)
            values = np.clip(base * mult + noise, 2.0, 200.0)

        flags = np.full(T, "ok", dtype=object)

        if int(sid) in missing_windows:
            s, e = missing_windows[int(sid)]
            flags[s : e + 1] = "missing"
            values[s : e + 1] = 0.0

        if int(sid) in suspect_points:
            for idx in suspect_points[int(sid)]:
                flags[idx] = "suspect"
                if st == "traffic_intensity":
                    values[idx] *= float(rng.uniform(1.8, 3.2))
                elif st == "noise_db":
                    values[idx] += float(rng.uniform(12.0, 28.0))
                elif st == "pm25":
                    values[idx] += float(rng.uniform(30.0, 90.0))
                else:
                    values[idx] += float(rng.uniform(-6.0, 6.0))

        if st == "temp_c":
            values = np.clip(values, -20.0, 40.0)
        elif st == "noise_db":
            values = np.clip(values, 30.0, 110.0)
        elif st == "pm25":
            values = np.clip(values, 2.0, 240.0)

        for i in range(T):
            buf.append((int(sid), ts_str[i], float(values[i]), str(flags[i])))
            if len(buf) >= buf_max:
                cur.executemany(insert_sql, buf)
                total += len(buf)
                buf.clear()

    if buf:
        cur.executemany(insert_sql, buf)
        total += len(buf)

    return total


def gen_meter_readings(
    conn: sqlite3.Connection,
    rng: np.random.Generator,
    meters_rows: List[Tuple],
    obj2dist: Dict[int, int],
    objects_rows: List[Tuple],
    dist_series: Dict[int, Dict[str, np.ndarray]],
    dts: List[datetime],
) -> int:
    T = len(dts)
    ts_str = [iso_no_tz(dt) for dt in dts]

    road_ids = [r[0] for r in objects_rows if r[2] == "road_segment"]
    n_leaky = max(1, int(len(road_ids) * float(rng.uniform(0.01, 0.02))))
    leaky_roads = set(rng.choice(np.array(road_ids, dtype=int), size=n_leaky, replace=False).tolist())

    cur = conn.cursor()
    insert_sql = "INSERT INTO meter_readings(meter_id, ts, value, is_peak) VALUES (?, ?, ?, ?)"

    hours = np.array([dt.hour for dt in dts], dtype=np.float32)
    morning = gaussian_bump(hours, mu=8.0, sigma=2.0, amp=1.0)
    evening = gaussian_bump(hours, mu=19.0, sigma=2.2, amp=1.2)
    base_profile = 0.45 + 0.55 * morning + 0.75 * evening

    total = 0
    buf: List[Tuple] = []
    buf_max = 50000

    for mid, oid, ut, unit, is_active in meters_rows:
        did = obj2dist[int(oid)]
        temp = dist_series[did]["temp_c"].astype(np.float32)

        if ut == "electricity_kwh":
            base = float(rng.uniform(1.2, 6.5))
            cold_boost = np.clip((0.0 - temp) / 12.0, 0.0, 1.0)
            values = base * base_profile * (1.0 + 0.45 * cold_boost) + rng.normal(0.0, 0.25, size=T)
            values = np.clip(values, 0.05, None)
        elif ut == "water_m3":
            base = float(rng.uniform(0.05, 0.40))
            values = base * (0.75 + 0.35 * base_profile) + rng.normal(0.0, 0.03, size=T)
            values = np.clip(values, 0.0, None)
            if int(oid) in leaky_roads:
                values *= float(rng.uniform(2.5, 6.0))
        else:  # heating_gcal
            base = float(rng.uniform(0.10, 0.55))
            demand = np.clip((5.0 - temp) / 18.0, 0.0, 1.4)
            values = base * (0.85 + 0.15 * base_profile) * (1.0 + 1.8 * demand) + rng.normal(0.0, 0.05, size=T)
            values = np.clip(values, 0.0, None)

        thr = float(np.quantile(values, 0.90))
        is_peak = (values >= thr).astype(np.int8)

        for i in range(T):
            buf.append((int(mid), ts_str[i], float(values[i]), int(is_peak[i])))
            if len(buf) >= buf_max:
                cur.executemany(insert_sql, buf)
                total += len(buf)
                buf.clear()

    if buf:
        cur.executemany(insert_sql, buf)
        total += len(buf)

    return total


def gen_citizen_requests(
    conn: sqlite3.Connection,
    rng: np.random.Generator,
    districts: List[District],
    objects_rows: List[Tuple],
    obj2dist: Dict[int, int],
    dist_series: Dict[int, Dict[str, np.ndarray]],
    dts: List[datetime],
    events_rows: List[Tuple],
    n_requests: int,
) -> int:
    T = len(dts)
    district_ids = np.array([d.district_id for d in districts], dtype=int)
    pop = np.array([d.population for d in districts], dtype=float)
    dist_prob = pop / pop.sum()

    streetlights = np.array([r[0] for r in objects_rows if r[2] == "streetlight"], dtype=int)
    roads = np.array([r[0] for r in objects_rows if r[2] == "road_segment"], dtype=int)

    n_bad_lights = max(1, int(len(streetlights) * float(rng.uniform(0.03, 0.05))))
    bad_lights = set(rng.choice(streetlights, size=n_bad_lights, replace=False).tolist())

    n_bad_roads = max(1, int(len(roads) * float(rng.uniform(0.01, 0.02))))
    bad_roads = set(rng.choice(roads, size=n_bad_roads, replace=False).tolist())

    event_after_mask: Dict[int, np.ndarray] = {d.district_id: np.zeros(T, dtype=np.float32) for d in districts}
    for row in events_rows:
        _, did, _, et, start_s, end_s, _ = row
        did = int(did)
        end_dt = datetime.strptime(end_s, "%Y-%m-%d %H:%M:%S")
        sidx = int((end_dt - dts[0]).total_seconds() // 3600)
        eidx = min(T - 1, sidx + 24)
        if 0 <= sidx < T:
            event_after_mask[did][sidx : eidx + 1] += 1.0

    noise_w: Dict[int, np.ndarray] = {}
    heating_w: Dict[int, np.ndarray] = {}
    pothole_w: Dict[int, np.ndarray] = {}
    parking_w: Dict[int, np.ndarray] = {}

    for d in districts:
        nser = dist_series[d.district_id]["noise_db"]
        tser = dist_series[d.district_id]["temp_c"]

        noise_w[d.district_id] = (nser > 65.0).astype(np.float32) + 0.05
        heating_w[d.district_id] = (tser < 0.0).astype(np.float32) + 0.03

        dtemp = np.abs(np.diff(tser, prepend=tser[0]))
        pothole_w[d.district_id] = (
            (np.clip(1.0 - np.abs(tser) / 6.0, 0.0, 1.0) + 0.6 * np.clip(dtemp / 4.0, 0.0, 1.0)) + 0.05
        )

        parking_w[d.district_id] = (0.05 + 0.35 * event_after_mask[d.district_id] + (0.08 if d.is_central else 0.0)).astype(np.float32)

    base_mix = {
        "noise_complaint": 0.16,
        "parking_issue": 0.18,
        "pothole": 0.12,
        "broken_streetlight": 0.16,
        "water_leak": 0.12,
        "heating_issue": 0.26,
    }
    cats = np.array(list(base_mix.keys()), dtype=object)
    probs = np.array([base_mix[c] for c in cats], dtype=float)
    probs = probs / probs.sum()

    pr_probs = np.array([0.55, 0.33, 0.12], dtype=float)

    sla = {
        "water_leak": {"low": (24, 168), "medium": (6, 72), "high": (2, 24)},
        "heating_issue": {"low": (24, 168), "medium": (6, 72), "high": (2, 24)},
        "broken_streetlight": {"low": (24, 168), "medium": (12, 96), "high": (6, 48)},
        "pothole": {"low": (48, 240), "medium": (24, 168), "high": (12, 96)},
        "noise_complaint": {"low": (24, 168), "medium": (6, 72), "high": (2, 24)},
        "parking_issue": {"low": (24, 168), "medium": (12, 96), "high": (6, 48)},
    }

    def sample_time_for_category(did: int, cat: str) -> int:
        if cat == "noise_complaint":
            w = noise_w[did]
        elif cat == "heating_issue":
            w = heating_w[did]
        elif cat == "pothole":
            w = pothole_w[did]
        elif cat == "parking_issue":
            w = parking_w[did]
        else:
            return int(rng.integers(0, T))
        s = float(w.sum())
        if s <= 0:
            return int(rng.integers(0, T))
        return int(rng.choice(np.arange(T), p=(w / s)))

    def pick_object_for(cat: str, did: int) -> Optional[int]:
        if cat == "broken_streetlight":
            cand_bad = [oid for oid in bad_lights if obj2dist[int(oid)] == did]
            cand_all = [oid for oid in streetlights.tolist() if obj2dist[int(oid)] == did]
            if cand_bad and rng.random() < 0.70:
                return int(rng.choice(np.array(cand_bad, dtype=int)))
            if cand_all:
                return int(rng.choice(np.array(cand_all, dtype=int)))
            return None
        if cat == "water_leak":
            cand_bad = [oid for oid in bad_roads if obj2dist[int(oid)] == did]
            cand_all = [oid for oid in roads.tolist() if obj2dist[int(oid)] == did]
            if cand_bad and rng.random() < 0.75:
                return int(rng.choice(np.array(cand_bad, dtype=int)))
            if cand_all:
                return int(rng.choice(np.array(cand_all, dtype=int)))
            return None
        if cat == "pothole":
            cand = [oid for oid in roads.tolist() if obj2dist[int(oid)] == did]
            return int(rng.choice(np.array(cand, dtype=int))) if cand else None
        return None

    # enforce min counts for acceptance
    min_noise = 1000
    min_parking = 1000

    counts = rng.multinomial(n_requests, probs)
    cat2n = {str(cats[i]): int(counts[i]) for i in range(len(cats))}
    if cat2n["noise_complaint"] < min_noise:
        diff = min_noise - cat2n["noise_complaint"]
        cat2n["noise_complaint"] += diff
        cat2n["heating_issue"] = max(0, cat2n["heating_issue"] - diff)
    if cat2n["parking_issue"] < min_parking:
        diff = min_parking - cat2n["parking_issue"]
        cat2n["parking_issue"] += diff
        cat2n["heating_issue"] = max(0, cat2n["heating_issue"] - diff)

    rows: List[Tuple] = []
    req_id = 1
    for cat, n_cat in cat2n.items():
        for _ in range(n_cat):
            did = int(rng.choice(district_ids, p=dist_prob))
            tidx = sample_time_for_category(did, cat)
            created = dts[tidx]

            priority = str(rng.choice(REQUEST_PRIORITIES, p=pr_probs))

            resolved = rng.random() < float(rng.uniform(0.75, 0.90))
            if resolved:
                status = "resolved"
                lo, hi = sla[cat][priority]
                resolution_hours = float(rng.uniform(lo, hi))
                resolved_ts = created + timedelta(hours=resolution_hours)
                if resolved_ts > dts[-1] + timedelta(hours=48):
                    status = str(rng.choice(["open", "in_progress"], p=[0.6, 0.4]))
                    resolved_ts_s = None
                    resolution_hours_v = None
                else:
                    resolved_ts_s = iso_no_tz(resolved_ts)
                    resolution_hours_v = resolution_hours
            else:
                status = str(rng.choice(["open", "in_progress"], p=[0.7, 0.3]))
                resolved_ts_s = None
                resolution_hours_v = None

            oid = pick_object_for(cat, did)

            rows.append(
                (
                    req_id,
                    did,
                    oid,
                    cat,
                    iso_no_tz(created),
                    status,
                    resolved_ts_s,
                    resolution_hours_v,
                    priority,
                )
            )
            req_id += 1

    insert_sql = (
        "INSERT INTO citizen_requests(request_id, district_id, object_id, category, created_ts, status, resolved_ts, resolution_hours, priority) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    conn.cursor().executemany(insert_sql, rows)
    return len(rows)


def gen_public_transport_trips(
    conn: sqlite3.Connection,
    rng: np.random.Generator,
    objects_rows: List[Tuple],
    obj2dist: Dict[int, int],
    dist_series: Dict[int, Dict[str, np.ndarray]],
    dts: List[datetime],
    n_trips: int,
) -> int:
    stop_ids = np.array([r[0] for r in objects_rows if r[2] == "stop"], dtype=int)
    if len(stop_ids) == 0:
        return 0

    n_routes = int(rng.integers(10, 31))
    routes = [f"R{idx:02d}" for idx in range(1, n_routes + 1)]

    route_stops: Dict[str, np.ndarray] = {}
    for r in routes:
        k = int(rng.integers(8, min(25, len(stop_ids)) + 1))
        route_stops[r] = rng.choice(stop_ids, size=k, replace=False)

    T = len(dts)
    hours = np.array([dt.hour for dt in dts], dtype=np.int16)
    peak = (((hours >= 7) & (hours <= 10)) | ((hours >= 17) & (hours <= 20))).astype(np.float32)

    cur = conn.cursor()
    insert_sql = (
        "INSERT INTO public_transport_trips(trip_id, route_no, vehicle_id, stop_object_id, scheduled_ts, actual_ts, passenger_est) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    rows: List[Tuple] = []
    trip_id = 1

    for _ in range(n_trips):
        route = str(rng.choice(routes))
        stop = int(rng.choice(route_stops[route]))
        did = obj2dist[stop]

        tidx = int(rng.integers(0, T))
        sched = dts[tidx]
        traffic = float(dist_series[did]["traffic_intensity"][tidx])

        base_delay = float(rng.uniform(0.0, 4.0))
        traffic_term = (traffic / 400.0) * float(rng.uniform(2.0, 10.0))
        peak_term = float(peak[tidx]) * float(rng.uniform(2.0, 8.0))
        delay_min = base_delay + traffic_term + peak_term
        delay_min = float(np.clip(delay_min + rng.normal(0.0, 1.5), 0.0, 35.0))

        actual = sched + timedelta(minutes=delay_min)

        base_p = int(rng.integers(5, 35))
        passenger_est = int(base_p + peak[tidx] * rng.integers(20, 90) + min(120, traffic / 8.0))

        vehicle_id = f"V{int(rng.integers(1, 180)):03d}"

        rows.append((trip_id, route, vehicle_id, stop, iso_no_tz(sched), iso_no_tz(actual), passenger_est))
        trip_id += 1

        if len(rows) >= 50000:
            cur.executemany(insert_sql, rows)
            rows.clear()

    if rows:
        cur.executemany(insert_sql, rows)

    return n_trips


def validate_acceptance(conn: sqlite3.Connection) -> Dict[str, object]:
    cur = conn.cursor()
    res: Dict[str, object] = {}

    tables = [
        "districts",
        "city_objects",
        "sensors",
        "smart_meters",
        "sensor_readings",
        "meter_readings",
        "municipal_events",
        "citizen_requests",
        "public_transport_trips",
    ]
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        res[f"count_{t}"] = int(cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM districts")
    res["ok_min_districts"] = int(cur.fetchone()[0]) >= 10

    cur.execute("SELECT COUNT(*) FROM city_objects WHERE lat IS NOT NULL AND lon IS NOT NULL")
    res["ok_min_objects_with_coords"] = int(cur.fetchone()[0]) >= 1000

    cur.execute(
        """
        SELECT d.district_id,
               SUM(CASE WHEN s.sensor_type='noise_db' THEN 1 ELSE 0 END) AS n_noise,
               SUM(CASE WHEN s.sensor_type='traffic_intensity' THEN 1 ELSE 0 END) AS n_traffic,
               SUM(CASE WHEN s.sensor_type='temp_c' THEN 1 ELSE 0 END) AS n_temp,
               SUM(CASE WHEN s.sensor_type='pm25' THEN 1 ELSE 0 END) AS n_pm
        FROM districts d
        LEFT JOIN city_objects o ON o.district_id=d.district_id
        LEFT JOIN sensors s ON s.object_id=o.object_id
        GROUP BY d.district_id
        """
    )
    coverage = cur.fetchall()
    res["ok_sensor_coverage_all_districts"] = all((r[1] > 0 and r[2] > 0 and r[3] > 0 and r[4] > 0) for r in coverage)

    cur.execute("SELECT COUNT(*) FROM municipal_events")
    res["ok_min_events"] = int(cur.fetchone()[0]) >= 10

    cur.execute("SELECT COUNT(*) FROM citizen_requests WHERE category='noise_complaint'")
    res["ok_min_noise_complaint"] = int(cur.fetchone()[0]) >= 1000

    cur.execute("SELECT COUNT(*) FROM citizen_requests WHERE category='parking_issue'")
    res["ok_min_parking_issue"] = int(cur.fetchone()[0]) >= 1000

    cur.execute("SELECT COUNT(*) FROM sensor_readings WHERE quality_flag='missing'")
    res["ok_has_missing"] = int(cur.fetchone()[0]) > 0

    # Queries should return non-empty
    queries = {
        "top_districts_requests_30d": """
            SELECT d.name, COUNT(*) AS cnt
            FROM citizen_requests r
            JOIN districts d ON d.district_id=r.district_id
            WHERE r.created_ts >= datetime('now','-30 day')
            GROUP BY d.name
            ORDER BY cnt DESC
            LIMIT 10;
        """,
        "corr_noise_vs_complaints": """
            WITH hourly AS (
              SELECT o.district_id, sr.ts,
                     AVG(CASE WHEN s.sensor_type='noise_db' THEN sr.value END) AS noise_avg
              FROM sensor_readings sr
              JOIN sensors s ON s.sensor_id=sr.sensor_id
              JOIN city_objects o ON o.object_id=s.object_id
              GROUP BY o.district_id, sr.ts
            ),
            complaints AS (
              SELECT district_id, created_ts AS ts, COUNT(*) AS n
              FROM citizen_requests
              WHERE category='noise_complaint'
              GROUP BY district_id, created_ts
            )
            SELECT h.district_id,
                   AVG(h.noise_avg) AS avg_noise,
                   SUM(COALESCE(c.n,0)) AS complaints
            FROM hourly h
            LEFT JOIN complaints c ON c.district_id=h.district_id AND c.ts=h.ts
            GROUP BY h.district_id
            ORDER BY complaints DESC
            LIMIT 10;
        """,
        "event_impact_traffic": """
            WITH ev AS (
              SELECT event_id, district_id, start_ts, end_ts
              FROM municipal_events
              ORDER BY attendance_est DESC
              LIMIT 1
            ),
            traffic AS (
              SELECT o.district_id, sr.ts, AVG(sr.value) AS v
              FROM sensor_readings sr
              JOIN sensors s ON s.sensor_id=sr.sensor_id
              JOIN city_objects o ON o.object_id=s.object_id
              WHERE s.sensor_type='traffic_intensity'
              GROUP BY o.district_id, sr.ts
            )
            SELECT
              (SELECT district_id FROM ev) AS district_id,
              AVG(CASE WHEN t.ts BETWEEN (SELECT start_ts FROM ev) AND (SELECT end_ts FROM ev) THEN t.v END) AS during_avg,
              AVG(CASE WHEN t.ts BETWEEN datetime((SELECT start_ts FROM ev),'-24 hour') AND (SELECT start_ts FROM ev) THEN t.v END) AS before_avg
            FROM traffic t
            WHERE t.district_id = (SELECT district_id FROM ev);
        """,
        "punctuality_by_route": """
            SELECT route_no,
                   AVG((julianday(actual_ts) - julianday(scheduled_ts)) * 24.0 * 60.0) AS avg_delay_min,
                   AVG(CASE WHEN (julianday(actual_ts) - julianday(scheduled_ts)) * 24.0 * 60.0 <= 5 THEN 1.0 ELSE 0.0 END) AS share_on_time
            FROM public_transport_trips
            GROUP BY route_no
            ORDER BY avg_delay_min DESC
            LIMIT 10;
        """,
    }
    for k, q in queries.items():
        cur.execute(q)
        res[f"ok_query_{k}"] = len(cur.fetchall()) > 0

    return res


# -----------------------------
# Main
# -----------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    preset = SCALE_PRESETS[args.scale]
    seed = int(args.seed)
    rng = np.random.default_rng(seed)

    db_path = Path(args.db_path)
    exports_dir = Path(args.exports_dir)
    docs_dir = Path(args.docs_dir)
    log_path = Path(args.log_path)

    ensure_dir(log_path.parent)
    ensure_dir(Path("scripts"))
    ensure_dir(Path("data"))
    ensure_dir(Path("outputs"))
    ensure_dir(Path("docs_workspace"))

    dts, hours, dow, day_index = make_time_index(days=int(args.days), step_hours=int(args.step_hours))

    with log_path.open("w", encoding="utf-8") as lf:
        lf.write("CityGrid generation log\n")
        lf.write(f"generated_at: {iso_no_tz(datetime.now())}\n")
        lf.write(f"seed: {seed}\n")
        lf.write(f"scale: {args.scale}\n")
        lf.write(f"days: {args.days}\n")
        lf.write(f"step_hours: {args.step_hours}\n")
        lf.write(f"timeline_points: {len(dts)}\n")

        conn = connect_db(db_path)
        try:
            create_schema(conn)

            districts = gen_districts(rng, int(preset["districts"]))
            insert_many(
                conn,
                "INSERT INTO districts(district_id, name, population, area_km2, center_lat, center_lon) VALUES (?, ?, ?, ?, ?, ?)",
                [(d.district_id, d.name, d.population, d.area_km2, d.center_lat, d.center_lon) for d in districts],
                chunk=1000,
            )
            lf.write(f"districts: {len(districts)}\n")

            objects_rows, obj2dist, obj2type = gen_city_objects(rng, districts, int(preset["city_objects"]))
            insert_many(
                conn,
                "INSERT INTO city_objects(object_id, district_id, object_type, name, lat, lon, install_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                objects_rows,
                chunk=5000,
            )
            lf.write(f"city_objects: {len(objects_rows)}\n")

            sensors_rows, sensor2dist, sensor2type = gen_sensors(rng, districts, objects_rows, obj2dist, int(preset["sensors"]))
            insert_many(
                conn,
                "INSERT INTO sensors(sensor_id, object_id, sensor_type, unit, is_active) VALUES (?, ?, ?, ?, ?)",
                sensors_rows,
                chunk=5000,
            )
            lf.write(f"sensors: {len(sensors_rows)}\n")

            meters_rows, meter2obj, meter2type = gen_meters(rng, objects_rows, obj2type, int(preset["smart_meters"]))
            insert_many(
                conn,
                "INSERT INTO smart_meters(meter_id, object_id, utility_type, unit, is_active) VALUES (?, ?, ?, ?, ?)",
                meters_rows,
                chunk=5000,
            )
            lf.write(f"smart_meters: {len(meters_rows)}\n")

            events_rows = gen_municipal_events(rng, districts, dts, int(preset["municipal_events"]))
            insert_many(
                conn,
                "INSERT INTO municipal_events(event_id, district_id, name, event_type, start_ts, end_ts, attendance_est) VALUES (?, ?, ?, ?, ?, ?, ?)",
                events_rows,
                chunk=5000,
            )
            lf.write(f"municipal_events: {len(events_rows)}\n")

            dist_series = district_time_series(rng, districts, dts, hours, dow, day_index, events_rows)

            lf.write("sensor_readings: generating...\n")
            n_sr = gen_sensor_readings(conn, rng, sensors_rows, sensor2dist, sensor2type, dist_series, dts)
            lf.write(f"sensor_readings: {n_sr}\n")

            lf.write("meter_readings: generating...\n")
            n_mr = gen_meter_readings(conn, rng, meters_rows, obj2dist, objects_rows, dist_series, dts)
            lf.write(f"meter_readings: {n_mr}\n")

            n_req = gen_citizen_requests(conn, rng, districts, objects_rows, obj2dist, dist_series, dts, events_rows, int(preset["citizen_requests"]))
            lf.write(f"citizen_requests: {n_req}\n")

            n_tr = gen_public_transport_trips(conn, rng, objects_rows, obj2dist, dist_series, dts, int(preset["public_transport_trips"]))
            lf.write(f"public_transport_trips: {n_tr}\n")

            conn.commit()

            generate_docs(docs_dir)
            lf.write(f"docs_workspace: {docs_dir.resolve()}\n")

            if args.export_csv:
                ensure_dir(exports_dir)
                tables = [
                    "districts",
                    "city_objects",
                    "sensors",
                    "smart_meters",
                    "municipal_events",
                    "citizen_requests",
                    "public_transport_trips",
                ]
                for t in tables:
                    export_table_to_csv(conn, t, exports_dir / f"{t}.csv")
                lf.write(f"csv_exports_dir: {exports_dir.resolve()}\n")

            val = validate_acceptance(conn)
            lf.write("\nVALIDATION:\n")
            for k in sorted(val.keys()):
                lf.write(f"{k}: {val[k]}\n")

        finally:
            conn.close()

    print(f"OK: generated {db_path} (log: {log_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
