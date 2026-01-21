#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import math
import json
import time
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional, Set

import numpy as np
import pandas as pd
import yaml
from scipy import stats
from scipy.spatial import Delaunay, Voronoi


# ----------------------------
# Utils
# ----------------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float) -> np.ndarray:
    r = 6371.0
    phi1 = np.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * math.cos(phi2) * np.sin(dlmb / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return r * c


def haversine_km_scalar(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def dt_range(start_date: str, days: int, step_hours: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(start_date + " 00:00:00")
    periods = int((days * 24) / step_hours)
    return pd.date_range(start=start, periods=periods, freq=pd.Timedelta(hours=step_hours))


def ts_to_str(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def write_text_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


# ----------------------------
# Config + scale
# ----------------------------

SCALE_DEFAULTS = {
    "small": {
        "districts": 5, "nodes": 100, "objects": 500, "sensors": 750,
        "meters": 300, "events": 75, "requests": 10_000, "trips": 50_000
    },
    "medium": {
        "districts": 10, "nodes": 250, "objects": 2000, "sensors": 3000,
        "meters": 1200, "events": 300, "requests": 40_000, "trips": 200_000
    },
    "large": {
        "districts": 15, "nodes": 400, "objects": 4000, "sensors": 6000,
        "meters": 2500, "events": 600, "requests": 80_000, "trips": 400_000
    },
    "extra-large": {
        "districts": 20, "nodes": 600, "objects": 6000, "sensors": 9000,
        "meters": 3600, "events": 1200, "requests": 160_000, "trips": 800_000
    },
}


@dataclass(frozen=True)
class CityBounds:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


@dataclass(frozen=True)
class QualityCfg:
    missing_sensor_share_min: float
    missing_sensor_share_max: float
    missing_window_hours_min: int
    missing_window_hours_max: int
    suspect_sensor_share_min: float
    suspect_sensor_share_max: float


@dataclass(frozen=True)
class GenCfg:
    seed: int
    start_date: str
    days: int
    step_hours: int
    scale: str
    timezone: str
    enable_long_term_trends: bool
    traffic_growth_percent_per_year: float
    infrastructure_degradation_percent_per_year: float


@dataclass(frozen=True)
class OutputCfg:
    sqlite_path: str
    csv_dir: str
    log_file: str
    docs_dir: str


@dataclass(frozen=True)
class FullCfg:
    generation: GenCfg
    output: OutputCfg
    geography_bounds: CityBounds
    quality: QualityCfg


def load_config(path: Path) -> FullCfg:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    g = data["generation"]
    o = data["output"]
    b = data["geography"]["city_bounds"]
    q = data["quality"]

    return FullCfg(
        generation=GenCfg(
            seed=int(g["seed"]),
            start_date=str(g["start_date"]),
            days=int(g["days"]),
            step_hours=int(g["step_hours"]),
            scale=str(g["scale"]).lower(),
            timezone=str(g.get("timezone", "GMT+3")),
            enable_long_term_trends=bool(g.get("enable_long_term_trends", True)),
            traffic_growth_percent_per_year=float(g.get("traffic_growth_percent_per_year", 2.5)),
            infrastructure_degradation_percent_per_year=float(
                g.get("infrastructure_degradation_percent_per_year", 1.0)),
        ),
        output=OutputCfg(
            sqlite_path=str(o["sqlite_path"]),
            csv_dir=str(o["csv_dir"]),
            log_file=str(o["log_file"]),
            docs_dir=str(o["docs_dir"]),
        ),
        geography_bounds=CityBounds(
            lat_min=float(b["lat_min"]),
            lat_max=float(b["lat_max"]),
            lon_min=float(b["lon_min"]),
            lon_max=float(b["lon_max"]),
        ),
        quality=QualityCfg(
            missing_sensor_share_min=float(q["missing_sensor_share_min"]),
            missing_sensor_share_max=float(q["missing_sensor_share_max"]),
            missing_window_hours_min=int(q["missing_window_hours_min"]),
            missing_window_hours_max=int(q["missing_window_hours_max"]),
            suspect_sensor_share_min=float(q["suspect_sensor_share_min"]),
            suspect_sensor_share_max=float(q["suspect_sensor_share_max"]),
        ),
    )


# ----------------------------
# DB schema
# ----------------------------

DDL = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS public_transport_trips;
DROP TABLE IF EXISTS citizen_requests;
DROP TABLE IF EXISTS municipal_events;
DROP TABLE IF EXISTS meter_readings;
DROP TABLE IF EXISTS sensor_readings;
DROP TABLE IF EXISTS smart_meters;
DROP TABLE IF EXISTS sensors;
DROP TABLE IF EXISTS city_objects;
DROP TABLE IF EXISTS road_network_nodes;
DROP TABLE IF EXISTS districts;

CREATE TABLE districts (
    district_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('residential','commercial','industrial','mixed','recreational','educational')),
    population INTEGER NOT NULL,
    area_km2 REAL NOT NULL,
    density TEXT NOT NULL CHECK(density IN ('low','medium','high','very_high')),
    income_level TEXT NOT NULL CHECK(income_level IN ('low','medium','high')),
    industrial_coeff REAL NOT NULL CHECK(industrial_coeff BETWEEN 0 AND 1),
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    geometry TEXT NULL
);

CREATE TABLE road_network_nodes (
    node_id INTEGER PRIMARY KEY,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('intersection', 'junction', 'terminal')),
    is_connected_to_district_center INTEGER NOT NULL CHECK(is_connected_to_district_center IN (0,1))
);

CREATE TABLE city_objects (
    object_id INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(district_id),
    object_type TEXT NOT NULL CHECK(object_type IN ('building','road_segment','streetlight','stop','parking','substation','park')),
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    install_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','inactive','under_repair')),
    capacity INTEGER NULL,
    length_m REAL NULL,
    from_node_id INTEGER NULL REFERENCES road_network_nodes(node_id),
    to_node_id INTEGER NULL REFERENCES road_network_nodes(node_id),
    road_type TEXT NULL CHECK(road_type IN ('highway', 'arterial', 'local', 'alley')),
    max_speed_kmh INTEGER NULL,
    lanes_count INTEGER NULL,
    direction TEXT NULL CHECK(direction IN ('both', 'forward', 'backward')),
    condition TEXT NULL CHECK(condition IN ('good', 'fair', 'poor')),
    start_lat REAL NULL,
    start_lon REAL NULL,
    end_lat REAL NULL,
    end_lon REAL NULL
);

CREATE TABLE sensors (
    sensor_id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES city_objects(object_id),
    sensor_type TEXT NOT NULL CHECK(sensor_type IN ('noise_db','pm25','traffic_intensity','temp_c')),
    unit TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
    last_calibration TEXT NULL,
    accuracy REAL NULL
);

CREATE TABLE smart_meters (
    meter_id INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL REFERENCES city_objects(object_id),
    utility_type TEXT NOT NULL CHECK(utility_type IN ('electricity_kwh','water_m3','heating_gcal')),
    unit TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK(is_active IN (0,1))
);

CREATE TABLE sensor_readings (
    reading_id INTEGER PRIMARY KEY,
    sensor_id INTEGER NOT NULL REFERENCES sensors(sensor_id),
    ts TEXT NOT NULL,
    value REAL NOT NULL,
    quality_flag TEXT NOT NULL CHECK(quality_flag IN ('ok','missing','suspect')),
    anomaly_score REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE meter_readings (
    reading_id INTEGER PRIMARY KEY,
    meter_id INTEGER NOT NULL REFERENCES smart_meters(meter_id),
    ts TEXT NOT NULL,
    value REAL NOT NULL,
    is_peak INTEGER NOT NULL CHECK(is_peak IN (0,1))
);

CREATE TABLE municipal_events (
    event_id INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(district_id),
    name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('concert','construction','accident','protest','festival','sports_event')),
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    expected_attendance INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    impact_radius_km REAL NOT NULL,
    noise_increase_db REAL NOT NULL,
    traffic_increase_percent REAL NOT NULL
);

CREATE TABLE citizen_requests (
    request_id INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(district_id),
    object_id INTEGER NULL REFERENCES city_objects(object_id),
    category TEXT NOT NULL CHECK(category IN (
        'noise_complaint','pothole','broken_streetlight','water_leak',
        'heating_issue','parking_issue','air_quality'
    )),
    created_ts TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('new','in_progress','resolved','rejected')),
    resolved_ts TEXT NULL,
    resolution_hours REAL NULL,
    priority TEXT NOT NULL CHECK(priority IN ('low','medium','high')),
    description TEXT NULL
);

CREATE TABLE public_transport_trips (
    trip_id INTEGER PRIMARY KEY,
    route_no TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    stop_object_id INTEGER NOT NULL REFERENCES city_objects(object_id),
    scheduled_ts TEXT NOT NULL,
    actual_ts TEXT NOT NULL,
    delay_minutes INTEGER NOT NULL,
    passenger_estimate INTEGER NOT NULL,
    weather_condition TEXT NULL CHECK(weather_condition IN ('clear','rain','snow','fog'))
);
"""

INDEXES = """
CREATE INDEX idx_sensor_readings_sensor_ts ON sensor_readings(sensor_id, ts);
CREATE INDEX idx_meter_readings_meter_ts ON meter_readings(meter_id, ts);
CREATE INDEX idx_citizen_requests_district_ts ON citizen_requests(district_id, created_ts);
CREATE INDEX idx_citizen_requests_category ON citizen_requests(category);
CREATE INDEX idx_municipal_events_district_time ON municipal_events(district_id, start_ts);
CREATE INDEX idx_city_objects_district_type ON city_objects(district_id, object_type);
CREATE INDEX idx_city_objects_type ON city_objects(object_type);
CREATE INDEX idx_sensors_type ON sensors(sensor_type);
CREATE INDEX idx_public_transport_route_time ON public_transport_trips(route_no, scheduled_ts);
CREATE INDEX idx_road_segments_nodes ON city_objects(from_node_id, to_node_id) WHERE object_type='road_segment';
CREATE INDEX idx_road_segments_type ON city_objects(road_type) WHERE object_type='road_segment';
CREATE INDEX idx_road_segments_condition ON city_objects(condition) WHERE object_type='road_segment';
CREATE INDEX idx_road_nodes_location ON road_network_nodes(lat, lon);
CREATE INDEX idx_road_nodes_type ON road_network_nodes(type);
"""

# ----------------------------
# Workspace docs
# ----------------------------

DOC_DATA_DICTIONARY = """# CityGrid - Data Dictionary

## districts
- district_id: PK
- type: residential/commercial/industrial/mixed/recreational/educational
- industrial_coeff: [0..1]
- center_lat, center_lon: центр района
- geometry: WKT полигона

## road_network_nodes
- node_id: PK
- type: intersection/junction/terminal
- is_connected_to_district_center: флаг связи с центром района

## city_objects
- object_id: PK
- object_type: building/road_segment/streetlight/stop/parking/substation/park
- capacity: только для stop/parking
- Поля для road_segment: length_m, from_node_id, to_node_id, road_type, max_speed_kmh, lanes_count, direction, condition, start_lat/lon, end_lat/lon

## sensors
- sensor_type: noise_db/pm25/traffic_intensity/temp_c

## sensor_readings
- quality_flag: ok/missing/suspect
- anomaly_score: 0 для ok/missing, >0 для suspect

## meter_readings
- is_peak: 1 если value >= 90-й перцентиль
"""

DOC_KPI_DEFINITIONS = """# CityGrid - KPI Definitions

## Transport Performance
- On-time share: доля поездок с delay_minutes = 0
- Avg delay: средняя задержка по маршруту

## Citizen Engagement
- Complaint rate: кол-во обращений на 10k населения
- Resolution rate: доля resolved среди всех обращений

## Event Impact
- Traffic change: сравнение traffic_intensity до/во время события
- Noise change: сравнение noise_db до/во время события

## Road Network
- Network connectivity: все районы связаны
- Avg road condition: распределение good/fair/poor
"""

DOC_SENSOR_SPECS = """# CityGrid - Sensor Specs

## noise_db
Единицы: dB
Типичные значения: 30-90
Связи: зависит от traffic_intensity, повышается во время событий

## traffic_intensity
Единицы: veh/h
Типичные значения: 20-500
Связи: пики 07-10 и 17-20, растет во время событий

## pm25
Единицы: ug/m3
Типичные значения: 5-120
Связи: растет с traffic_intensity и industrial_coeff

## temp_c
Единицы: C
Типичные значения: -30..35
Связи: влияет на heating_gcal
"""

DOC_REPORT_TEMPLATE = """# CityGrid - Report Template

## 1. Период и масштаб
- Период: <start> .. <end>
- Масштаб: small/medium/large/extra-large

## 2. Ключевые метрики
- Топ-районы по обращениям (30 дней)
- Пунктуальность транспорта
- Эффект событий
- Связь pm25 и air_quality обращений
- Состояние дорожной сети

## 3. Аномалии и качество данных
- missing %, suspect %
- Примеры аномальных точек

## 4. Выводы и рекомендации
"""

DOC_INCIDENT_POLICY = """# CityGrid - Incident Policy

## Severity
- Low: единичные обращения
- Medium: всплеск в 1 районе
- High: затронуто 2+ района или длительность > 24h

## Response
- Triage: подтвердить по датчикам
- Identify scope: район, радиус, время
- Mitigation: назначить ремонт
"""

DOC_ROAD_NETWORK_ANALYSIS = """# Road Network Analysis

## Graph Structure
Дорожная сеть представлена графом:
- Вершины: road_network_nodes
- Рёбра: city_objects с object_type='road_segment'

## Generation Algorithm
Используется триангуляция Делоне:
1. Опорные точки: центры районов + важные объекты
2. Триангуляция создаёт рёбра
3. Назначение атрибутов по длине и типу района

## Key Metrics
- Connectivity: все районы связаны
- Avg path length: средняя длина пути
- Road condition distribution: good/fair/poor
"""

DOC_TEMPORAL_PATTERNS = """# Temporal Patterns

## Daily Seasonality
- Traffic peaks: 07-10, 17-20
- Noise reduction at night
- Consumption profiles vary by utility type

## Weekly Patterns
- Weekend traffic -30%
- Commercial areas quieter on weekends

## Annual Trends (for periods > 180 days)
- Traffic growth: 2-3% per year
- Infrastructure degradation: 1-2% per year
- Seasonal heating/cooling patterns
"""


def ensure_workspace_docs(docs_dir: Path) -> None:
    ensure_dir(docs_dir)
    write_text_if_missing(docs_dir / "data_dictionary.md", DOC_DATA_DICTIONARY)
    write_text_if_missing(docs_dir / "kpi_definitions.md", DOC_KPI_DEFINITIONS)
    write_text_if_missing(docs_dir / "sensor_specs.md", DOC_SENSOR_SPECS)
    write_text_if_missing(docs_dir / "report_template.md", DOC_REPORT_TEMPLATE)
    write_text_if_missing(docs_dir / "incident_policy.md", DOC_INCIDENT_POLICY)
    write_text_if_missing(docs_dir / "road_network_analysis.md", DOC_ROAD_NETWORK_ANALYSIS)
    write_text_if_missing(docs_dir / "temporal_patterns.md", DOC_TEMPORAL_PATTERNS)


# ----------------------------
# Models
# ----------------------------

DISTRICT_TYPES = ["residential", "commercial", "industrial", "mixed", "recreational", "educational"]
DENSITY_LEVELS = ["low", "medium", "high", "very_high"]
INCOME_LEVELS = ["low", "medium", "high"]
OBJECT_TYPES = ["building", "road_segment", "streetlight", "stop", "parking", "substation", "park"]
SENSOR_TYPES = ["noise_db", "pm25", "traffic_intensity", "temp_c"]
UTILITY_TYPES = ["electricity_kwh", "water_m3", "heating_gcal"]
EVENT_TYPES = ["concert", "construction", "accident", "protest", "festival", "sports_event"]
REQUEST_CATEGORIES = ["noise_complaint", "pothole", "broken_streetlight", "water_leak", "heating_issue",
                      "parking_issue", "air_quality"]
WEATHER_CONDITIONS = ["clear", "rain", "snow", "fog"]


def pick_density(pop: int, area: float) -> str:
    dens = pop / max(area, 0.1)
    if dens < 2500:
        return "low"
    if dens < 5000:
        return "medium"
    if dens < 9000:
        return "high"
    return "very_high"


def density_mult(d: str) -> float:
    return {"low": 0.6, "medium": 0.9, "high": 1.2, "very_high": 1.6}[d]


def type_traffic_mult(t: str) -> float:
    return \
        {"residential": 0.9, "commercial": 1.4, "industrial": 1.1, "mixed": 1.3, "recreational": 0.7,
         "educational": 0.8}[t]


def daily_traffic_profile(hours: np.ndarray) -> np.ndarray:
    h = hours.astype(float)
    peak1 = stats.norm.pdf(h, loc=8.5, scale=1.3)
    peak2 = stats.norm.pdf(h, loc=18.0, scale=1.5)
    midday = stats.norm.pdf(h, loc=13.0, scale=3.0)
    base = 0.45 + 5.2 * peak1 + 6.0 * peak2 + 1.3 * midday
    return base / base.mean()


def ar1_noise(rng: np.random.Generator, n: int, phi: float, sigma: float) -> np.ndarray:
    e = rng.normal(0.0, sigma, size=n)
    x = np.empty(n, dtype=float)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


# ----------------------------
# DB operations
# ----------------------------

def create_connection(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -200000;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEXES)
    conn.commit()


def insert_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, df.itertuples(index=False, name=None))


def log_line(log_path: Path, msg: str) -> None:
    ensure_dir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{now_str()}] {msg}\n")


# ------------------------------------------------------------
# Helpers: Voronoi finite polygons + clipping to bbox + WKT
# ------------------------------------------------------------

def _voronoi_finite_polygons_2d(vor: Voronoi, radius: float | None = None):
    """
    Reconstruct infinite Voronoi regions in a 2D diagram to finite regions.
    Returns:
        regions: list[list[int]] - indices of vertices for each region
        vertices: np.ndarray - vertex coordinates
    Source idea: common SciPy Voronoi finite polygons recipe.
    """
    if vor.points.shape[1] != 2:
        raise ValueError("Voronoi input must be 2D")

    new_regions = []
    new_vertices = vor.vertices.tolist()

    center = vor.points.mean(axis=0)
    if radius is None:
        radius = vor.points.ptp(axis=0).max() * 2

    # Map ridge vertices to ridges per point
    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region_idx in enumerate(vor.point_region):
        vertices = vor.regions[region_idx]

        # Finite region
        if all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue

        # Reconstruct infinite region
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]

        for p2, v1, v2 in ridges:
            if v1 >= 0 and v2 >= 0:
                continue

            # One of vertices is at infinity
            v = v1 if v1 >= 0 else v2
            tangent = vor.points[p2] - vor.points[p1]
            tangent /= (np.linalg.norm(tangent) + 1e-12)
            normal = np.array([-tangent[1], tangent[0]])

            midpoint = (vor.points[p1] + vor.points[p2]) / 2
            direction = np.sign(np.dot(midpoint - center, normal)) * normal

            far_point = vor.vertices[v] + direction * radius
            new_vertices.append(far_point.tolist())
            new_region.append(len(new_vertices) - 1)

        # Sort region vertices counterclockwise
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = [v for _, v in sorted(zip(angles, new_region))]

        new_regions.append(new_region)

    return new_regions, np.asarray(new_vertices)


def _clip_polygon_to_bbox(poly_xy: list[tuple[float, float]],
                          bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """
    Sutherland-Hodgman polygon clipping to axis-aligned bbox.
    bbox = (xmin, ymin, xmax, ymax)
    """
    xmin, ymin, xmax, ymax = bbox

    def clip_edge(points, inside_fn, intersect_fn):
        if not points:
            return []
        out = []
        prev = points[-1]
        prev_inside = inside_fn(prev)
        for cur in points:
            cur_inside = inside_fn(cur)
            if cur_inside:
                if not prev_inside:
                    out.append(intersect_fn(prev, cur))
                out.append(cur)
            elif prev_inside:
                out.append(intersect_fn(prev, cur))
            prev, prev_inside = cur, cur_inside
        return out

    def intersect(p1, p2, x=None, y=None):
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        dy = y2 - y1
        if x is not None:
            t = (x - x1) / (dx + 1e-12)
            return (x, y1 + t * dy)
        if y is not None:
            t = (y - y1) / (dy + 1e-12)
            return (x1 + t * dx, y)
        return p2

    pts = poly_xy

    # Left
    pts = clip_edge(
        pts,
        inside_fn=lambda p: p[0] >= xmin,
        intersect_fn=lambda a, b: intersect(a, b, x=xmin),
    )
    # Right
    pts = clip_edge(
        pts,
        inside_fn=lambda p: p[0] <= xmax,
        intersect_fn=lambda a, b: intersect(a, b, x=xmax),
    )
    # Bottom
    pts = clip_edge(
        pts,
        inside_fn=lambda p: p[1] >= ymin,
        intersect_fn=lambda a, b: intersect(a, b, y=ymin),
    )
    # Top
    pts = clip_edge(
        pts,
        inside_fn=lambda p: p[1] <= ymax,
        intersect_fn=lambda a, b: intersect(a, b, y=ymax),
    )

    # Remove tiny artifacts
    if len(pts) >= 3:
        cleaned = [pts[0]]
        for p in pts[1:]:
            if (abs(p[0] - cleaned[-1][0]) + abs(p[1] - cleaned[-1][1])) > 1e-9:
                cleaned.append(p)
        pts = cleaned

    return pts


def _poly_area_xy(poly_xy: list[tuple[float, float]]) -> float:
    """Shoelace area for polygon in XY coords."""
    if len(poly_xy) < 3:
        return 0.0
    s = 0.0
    for (x1, y1), (x2, y2) in zip(poly_xy, poly_xy[1:] + [poly_xy[0]]):
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _poly_to_wkt_lonlat(poly_lonlat: list[tuple[float, float]]) -> str:
    """Build WKT POLYGON((lon lat, ...)) with closed ring."""
    if len(poly_lonlat) < 3:
        return "POLYGON(())"
    ring = poly_lonlat[:]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    coords = ",".join([f"{lon:.6f} {lat:.6f}" for lon, lat in ring])
    return f"POLYGON(({coords}))"


# ------------------------------------------------------------
# Main: districts with Voronoi geometry
# ------------------------------------------------------------

def gen_districts(rng: np.random.Generator, bounds, n: int) -> pd.DataFrame:
    """
    Districts geometry is generated via Voronoi cells inside city bounds.
    - centers: random points inside bounds
    - geometry: Voronoi cell clipped to bbox, returned as WKT polygon
    - area_km2: computed from Voronoi polygon area (km^2)
    """

    # Если районов слишком мало - Voronoi может быть вырожден
    if n < 4:
        # fallback: старые прямоугольники (как было)
        type_probs = np.array([0.34, 0.14, 0.12, 0.22, 0.10, 0.08], dtype=float)
        type_probs = type_probs / type_probs.sum()

        rows = []
        for i in range(1, n + 1):
            t = rng.choice(DISTRICT_TYPES, p=type_probs)
            area = float(rng.uniform(6.0, 35.0))
            lat = float(rng.uniform(bounds.lat_min + 0.01, bounds.lat_max - 0.01))
            lon = float(rng.uniform(bounds.lon_min + 0.01, bounds.lon_max - 0.01))

            base_density = {
                "residential": rng.uniform(3500, 9000),
                "commercial": rng.uniform(2500, 7000),
                "industrial": rng.uniform(1500, 5000),
                "mixed": rng.uniform(3500, 9500),
                "recreational": rng.uniform(800, 2500),
                "educational": rng.uniform(1500, 4500),
            }[t]
            pop = int(max(5000, base_density * area + rng.normal(0, 3500)))
            dens = pick_density(pop, area)

            if t in ("commercial", "mixed"):
                income = rng.choice(INCOME_LEVELS, p=[0.18, 0.48, 0.34])
            elif t == "industrial":
                income = rng.choice(INCOME_LEVELS, p=[0.45, 0.43, 0.12])
            else:
                income = rng.choice(INCOME_LEVELS, p=[0.30, 0.55, 0.15])

            ic = {
                "industrial": rng.uniform(0.55, 0.95),
                "mixed": rng.uniform(0.25, 0.65),
                "commercial": rng.uniform(0.10, 0.35),
                "residential": rng.uniform(0.05, 0.25),
                "recreational": rng.uniform(0.00, 0.15),
                "educational": rng.uniform(0.05, 0.20),
            }[t]
            ic = float(clamp(ic + rng.normal(0, 0.03), 0.0, 1.0))

            side_km = math.sqrt(area)
            dlat = (side_km / 111.0) / 2.0
            dlon = (side_km / (111.0 * math.cos(math.radians(lat)) + 1e-9)) / 2.0
            lat1 = clamp(lat - dlat, bounds.lat_min, bounds.lat_max)
            lat2 = clamp(lat + dlat, bounds.lat_min, bounds.lat_max)
            lon1 = clamp(lon - dlon, bounds.lon_min, bounds.lon_max)
            lon2 = clamp(lon + dlon, bounds.lon_min, bounds.lon_max)
            wkt = f"POLYGON(({lon1} {lat1},{lon2} {lat1},{lon2} {lat2},{lon1} {lat2},{lon1} {lat1}))"

            rows.append({
                "district_id": i,
                "name": f"District {i}",
                "type": t,
                "population": pop,
                "area_km2": area,
                "density": dens,
                "income_level": income,
                "industrial_coeff": ic,
                "center_lat": lat,
                "center_lon": lon,
                "geometry": wkt,
            })
        return pd.DataFrame(rows)

    # 1) Генерим центры районов (seed points)
    type_probs = np.array([0.34, 0.14, 0.12, 0.22, 0.10, 0.08], dtype=float)
    type_probs = type_probs / type_probs.sum()

    centers_lat = rng.uniform(bounds.lat_min + 0.01, bounds.lat_max - 0.01, size=n).astype(float)
    centers_lon = rng.uniform(bounds.lon_min + 0.01, bounds.lon_max - 0.01, size=n).astype(float)
    types = rng.choice(DISTRICT_TYPES, size=n, p=type_probs)

    # 2) Проекция lat/lon -> локальные XY в километрах
    lat0 = (bounds.lat_min + bounds.lat_max) / 2.0
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(lat0))

    x = (centers_lon - bounds.lon_min) * km_per_deg_lon
    y = (centers_lat - bounds.lat_min) * km_per_deg_lat
    pts = np.column_stack([x, y])

    # 3) BBox в XY (км)
    x_min = 0.0
    y_min = 0.0
    x_max = (bounds.lon_max - bounds.lon_min) * km_per_deg_lon
    y_max = (bounds.lat_max - bounds.lat_min) * km_per_deg_lat
    bbox = (x_min, y_min, x_max, y_max)

    # 4) Вороной и превращение бесконечных ячеек в конечные
    vor = Voronoi(pts)
    regions, vertices = _voronoi_finite_polygons_2d(vor, radius=max(x_max, y_max) * 2.0)

    # 5) Собираем районы: клиппинг полигона по bbox, считаем площадь, WKT
    rows = []
    for i in range(n):
        t = types[i]
        region = regions[i]
        poly_xy = [(float(vertices[v, 0]), float(vertices[v, 1])) for v in region]

        # Обрезаем по границам города
        poly_xy = _clip_polygon_to_bbox(poly_xy, bbox)

        # Если вдруг полигон развалился (редко), fallback - маленький квадрат вокруг центра
        if len(poly_xy) < 3:
            cx, cy = float(pts[i, 0]), float(pts[i, 1])
            s = 0.8  # км (условно)
            poly_xy = [(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]

        area_km2 = _poly_area_xy(poly_xy)
        area_km2 = float(max(area_km2, 1.0))  # защита от нулевой площади

        base_density = {
            "residential": rng.uniform(3500, 9000),
            "commercial": rng.uniform(2500, 7000),
            "industrial": rng.uniform(1500, 5000),
            "mixed": rng.uniform(3500, 9500),
            "recreational": rng.uniform(800, 2500),
            "educational": rng.uniform(1500, 4500),
        }[t]
        pop = int(max(5000, base_density * area_km2 + rng.normal(0, 3500)))
        dens = pick_density(pop, area_km2)

        if t in ("commercial", "mixed"):
            income = rng.choice(INCOME_LEVELS, p=[0.18, 0.48, 0.34])
        elif t == "industrial":
            income = rng.choice(INCOME_LEVELS, p=[0.45, 0.43, 0.12])
        else:
            income = rng.choice(INCOME_LEVELS, p=[0.30, 0.55, 0.15])

        ic = {
            "industrial": rng.uniform(0.55, 0.95),
            "mixed": rng.uniform(0.25, 0.65),
            "commercial": rng.uniform(0.10, 0.35),
            "residential": rng.uniform(0.05, 0.25),
            "recreational": rng.uniform(0.00, 0.15),
            "educational": rng.uniform(0.05, 0.20),
        }[t]
        ic = float(clamp(ic + rng.normal(0, 0.03), 0.0, 1.0))

        # XY -> обратно в lon/lat для WKT (lon lat)
        poly_lonlat = []
        for px, py in poly_xy:
            lon = px / km_per_deg_lon + bounds.lon_min
            lat = py / km_per_deg_lat + bounds.lat_min
            poly_lonlat.append((float(lon), float(lat)))

        wkt = _poly_to_wkt_lonlat(poly_lonlat)

        rows.append({
            "district_id": i + 1,
            "name": f"District {i + 1}",
            "type": t,
            "population": pop,
            "area_km2": area_km2,
            "density": dens,
            "income_level": income,
            "industrial_coeff": ic,
            "center_lat": float(centers_lat[i]),
            "center_lon": float(centers_lon[i]),
            "geometry": wkt,
        })

    return pd.DataFrame(rows)


def gen_road_network(
        rng: np.random.Generator,
        bounds: CityBounds,
        districts: pd.DataFrame,
        n_nodes_target: int,
) -> Tuple[pd.DataFrame, List[Tuple[int, int, float, float, float, float]]]:
    """
    Returns: (nodes_df, edges_list)
    edges_list: [(from_nid, to_nid, start_lat, start_lon, end_lat, end_lon), ...]
    """
    points = []
    point_info = []

    # District centers
    for _, row in districts.iterrows():
        points.append((row["center_lat"], row["center_lon"]))
        point_info.append({"type": "district_center", "district_id": row["district_id"]})

    # Additional points per district - INCREASED to generate more edges
    n_districts = len(districts)
    # Calculate to reach target nodes
    extra_per_district = max(3, (n_nodes_target - n_districts) // n_districts)

    for _, row in districts.iterrows():
        for _ in range(extra_per_district):
            # Spread points more to create longer edges
            dlat = rng.uniform(-0.025, 0.025)
            dlon = rng.uniform(-0.025, 0.025)
            lat = clamp(row["center_lat"] + dlat, bounds.lat_min, bounds.lat_max)
            lon = clamp(row["center_lon"] + dlon, bounds.lon_min, bounds.lon_max)
            points.append((lat, lon))
            point_info.append({"type": "interior", "district_id": row["district_id"]})

    # Add random points across the city to ensure connectivity
    n_current = len(points)
    n_remaining = n_nodes_target - n_current
    if n_remaining > 0:
        for _ in range(n_remaining):
            lat = float(rng.uniform(bounds.lat_min + 0.01, bounds.lat_max - 0.01))
            lon = float(rng.uniform(bounds.lon_min + 0.01, bounds.lon_max - 0.01))
            points.append((lat, lon))
            # Assign to nearest district
            nearest_did = rng.choice(districts["district_id"].to_numpy())
            point_info.append({"type": "interior", "district_id": nearest_did})

    # Delaunay triangulation
    points_arr = np.array(points)
    tri = Delaunay(points_arr)

    # Extract edges from triangulation
    edges_set = set()
    for simplex in tri.simplices:
        for i in range(3):
            j = (i + 1) % 3
            a, b = simplex[i], simplex[j]
            if a > b:
                a, b = b, a
            edges_set.add((a, b))

    # Create nodes dataframe
    node_rows = []
    for nid, ((lat, lon), info) in enumerate(zip(points, point_info), start=1):
        ntype = "junction" if info["type"] == "district_center" else "intersection"
        is_dc = 1 if info["type"] == "district_center" else 0
        node_rows.append({
            "node_id": nid,
            "lat": lat,
            "lon": lon,
            "type": ntype,
            "is_connected_to_district_center": is_dc,
        })

    nodes_df = pd.DataFrame(node_rows)

    # Create edges list with coordinates
    edges_list = []
    for a, b in edges_set:
        from_nid = a + 1
        to_nid = b + 1
        start_lat, start_lon = points[a]
        end_lat, end_lon = points[b]
        edges_list.append((from_nid, to_nid, start_lat, start_lon, end_lat, end_lon))

    return nodes_df, edges_list


def gen_city_objects(
        rng: np.random.Generator,
        bounds: CityBounds,
        districts: pd.DataFrame,
        nodes_df: pd.DataFrame,
        road_edges: List[Tuple[int, int, float, float, float, float]],
        n_objects: int,
        start_date: str,
) -> pd.DataFrame:
    """Generate city objects including road segments from network edges"""

    # 30% of objects should be road segments
    n_road_segments = int(round(n_objects * 0.30))
    n_other_objects = n_objects - n_road_segments

    # Road segments from edges
    road_rows = []
    district_ids = districts["district_id"].to_numpy()

    # FIXED: Make sure we have enough edges, otherwise use all available
    n_available_edges = len(road_edges)
    n_road_segments_actual = min(n_road_segments, n_available_edges)

    if n_road_segments_actual < n_road_segments:
        print(f"⚠️ Warning: Only {n_available_edges} edges available, but {n_road_segments} road segments requested.")
        print(
            f"   Using all {n_available_edges} edges and creating {n_road_segments - n_available_edges} additional non-road objects.")
        n_other_objects = n_objects - n_road_segments_actual

    # Sample edges for road segments
    selected_edges = rng.choice(n_available_edges, size=n_road_segments_actual, replace=False)

    node_to_district = {}
    for _, row in nodes_df.iterrows():
        nid = row["node_id"]
        lat, lon = row["lat"], row["lon"]
        # Find closest district
        dists = haversine_km(
            districts["center_lat"].to_numpy(),
            districts["center_lon"].to_numpy(),
            lat, lon
        )
        node_to_district[nid] = district_ids[np.argmin(dists)]

    for idx, edge_idx in enumerate(selected_edges, start=1):
        from_nid, to_nid, start_lat, start_lon, end_lat, end_lon = road_edges[edge_idx]

        # Calculate length in meters
        length_m = haversine_km_scalar(start_lat, start_lon, end_lat, end_lon) * 1000

        # Assign to district
        did = node_to_district.get(from_nid, rng.choice(district_ids))

        # Determine road type based on length
        if length_m > 2000:
            road_type = "highway"
            max_speed = rng.integers(90, 111)
            lanes = rng.integers(2, 5)
        elif length_m > 500:
            road_type = "arterial"
            max_speed = rng.integers(60, 81)
            lanes = rng.integers(1, 4)
        else:
            road_type = "local"
            max_speed = rng.integers(30, 51)
            lanes = rng.integers(1, 3)

        # 5% alleys in residential
        district_info = districts[districts["district_id"] == did].iloc[0]
        if district_info["type"] == "residential" and rng.random() < 0.05:
            road_type = "alley"
            max_speed = rng.integers(20, 31)
            lanes = 1

        # Direction
        direction = rng.choice(["both", "forward", "backward"], p=[0.9, 0.05, 0.05])

        # Condition based on income level
        income = district_info["income_level"]
        if income == "high":
            condition = rng.choice(["good", "fair", "poor"], p=[0.7, 0.25, 0.05])
        elif income == "medium":
            condition = rng.choice(["good", "fair", "poor"], p=[0.5, 0.35, 0.15])
        else:
            condition = rng.choice(["good", "fair", "poor"], p=[0.3, 0.45, 0.25])

        # Center point
        center_lat = (start_lat + end_lat) / 2
        center_lon = (start_lon + end_lon) / 2

        # Install date
        start_ts = pd.Timestamp(start_date + " 00:00:00")
        min_ts = start_ts - pd.Timedelta(days=365 * 10)
        inst = min_ts + pd.Timedelta(seconds=int(rng.integers(0, int((start_ts - min_ts).total_seconds()))))

        status = rng.choice(["active", "under_repair", "inactive"], p=[0.90, 0.08, 0.02])

        road_rows.append({
            "object_id": idx,
            "district_id": did,
            "object_type": "road_segment",
            "name": f"road_{did}_{idx}",
            "lat": center_lat,
            "lon": center_lon,
            "install_date": ts_to_str(inst),
            "status": status,
            "capacity": None,
            "length_m": length_m,
            "from_node_id": from_nid,
            "to_node_id": to_nid,
            "road_type": road_type,
            "max_speed_kmh": max_speed,
            "lanes_count": lanes,
            "direction": direction,
            "condition": condition,
            "start_lat": start_lat,
            "start_lon": start_lon,
            "end_lat": end_lat,
            "end_lon": end_lon,
        })

    # Other objects
    weights = (districts["population"].to_numpy(dtype=float) * 0.7 +
               districts["area_km2"].to_numpy(dtype=float) * 3000.0)
    weights = weights / weights.sum()

    chosen_districts = rng.choice(district_ids, size=n_other_objects, replace=True, p=weights)

    dens_sigma_km = {"low": 1.8, "medium": 1.3, "high": 0.9, "very_high": 0.65}
    dmap = districts.set_index("district_id").to_dict(orient="index")

    other_rows = []
    start_id = n_road_segments + 1

    for i, did in enumerate(chosen_districts, start=start_id):
        info = dmap[int(did)]

        # Object type (excluding road_segment)
        other_types = ["building", "streetlight", "stop", "parking", "substation", "park"]
        if info["type"] == "residential":
            probs = [0.50, 0.21, 0.10, 0.08, 0.05, 0.06]
        elif info["type"] == "commercial":
            probs = [0.35, 0.18, 0.19, 0.18, 0.05, 0.05]
        elif info["type"] == "industrial":
            probs = [0.32, 0.16, 0.08, 0.10, 0.24, 0.10]
        elif info["type"] == "mixed":
            probs = [0.40, 0.19, 0.16, 0.13, 0.07, 0.05]
        elif info["type"] == "recreational":
            probs = [0.18, 0.21, 0.10, 0.13, 0.05, 0.33]
        else:  # educational
            probs = [0.40, 0.18, 0.13, 0.13, 0.08, 0.08]

        probs = np.array(probs) / sum(probs)
        ot = rng.choice(other_types, p=probs)

        sigma_km = dens_sigma_km[info["density"]]
        dx_km = float(rng.normal(0.0, sigma_km))
        dy_km = float(rng.normal(0.0, sigma_km))

        lat = float(info["center_lat"] + (dy_km / 111.0))
        lon = float(info["center_lon"] + (dx_km / (111.0 * math.cos(math.radians(info["center_lat"])) + 1e-9)))
        lat = clamp(lat, bounds.lat_min, bounds.lat_max)
        lon = clamp(lon, bounds.lon_min, bounds.lon_max)

        status = rng.choice(["active", "under_repair", "inactive"], p=[0.92, 0.06, 0.02])

        start_ts = pd.Timestamp(start_date + " 00:00:00")
        min_ts = start_ts - pd.Timedelta(days=365 * 10)
        inst = min_ts + pd.Timedelta(seconds=int(rng.integers(0, int((start_ts - min_ts).total_seconds()))))

        cap = None
        if ot == "stop":
            cap = int(rng.integers(30, 240))
        elif ot == "parking":
            cap = int(rng.integers(50, 520))

        other_rows.append({
            "object_id": i,
            "district_id": int(did),
            "object_type": ot,
            "name": f"{ot}_{did}_{i}",
            "lat": lat,
            "lon": lon,
            "install_date": ts_to_str(inst),
            "status": status,
            "capacity": cap,
            "length_m": None,
            "from_node_id": None,
            "to_node_id": None,
            "road_type": None,
            "max_speed_kmh": None,
            "lanes_count": None,
            "direction": None,
            "condition": None,
            "start_lat": None,
            "start_lon": None,
            "end_lat": None,
            "end_lon": None,
        })

    all_rows = road_rows + other_rows
    return pd.DataFrame(all_rows)


def gen_sensors(rng: np.random.Generator, objects_df: pd.DataFrame, n_sensors: int) -> pd.DataFrame:
    shares = {"traffic_intensity": 0.35, "noise_db": 0.30, "pm25": 0.20, "temp_c": 0.15}
    counts = {k: int(round(v * n_sensors)) for k, v in shares.items()}
    diff = n_sensors - sum(counts.values())
    if diff != 0:
        counts["traffic_intensity"] += diff

    obj_by_type = {}
    for ot in OBJECT_TYPES:
        obj_by_type[ot] = objects_df.loc[objects_df["object_type"] == ot, "object_id"].to_numpy()

    def pick_from(pool: np.ndarray, size: int) -> np.ndarray:
        if pool.size == 0:
            all_ids = objects_df["object_id"].to_numpy()
            return rng.choice(all_ids, size=size, replace=True)
        return rng.choice(pool, size=size, replace=True)

    rows = []
    sid = 1

    # traffic_intensity on roads
    n = counts["traffic_intensity"]
    pool = np.concatenate([obj_by_type["road_segment"], obj_by_type["stop"], obj_by_type["parking"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "traffic_intensity",
            "unit": "veh/h",
            "is_active": 1 if rng.random() < 0.94 else 0,
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.95, 0.02), 0.85, 0.99)),
        })
        sid += 1

    # noise_db
    n = counts["noise_db"]
    pool = np.concatenate([obj_by_type["road_segment"], obj_by_type["streetlight"],
                           obj_by_type["park"], obj_by_type["stop"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "noise_db",
            "unit": "dB",
            "is_active": 1 if rng.random() < 0.94 else 0,
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.93, 0.03), 0.80, 0.99)),
        })
        sid += 1

    # pm25
    n = counts["pm25"]
    pool = np.concatenate([obj_by_type["park"], obj_by_type["substation"], obj_by_type["road_segment"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "pm25",
            "unit": "ug/m3",
            "is_active": 1 if rng.random() < 0.93 else 0,
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.90, 0.04), 0.75, 0.99)),
        })
        sid += 1

    # temp_c
    n = counts["temp_c"]
    pool = np.concatenate([obj_by_type["park"], obj_by_type["substation"], obj_by_type["building"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "temp_c",
            "unit": "C",
            "is_active": 1 if rng.random() < 0.95 else 0,
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.97, 0.01), 0.90, 0.995)),
        })
        sid += 1

    df = pd.DataFrame(rows)

    # Calibration dates
    calib_mask = df["is_active"].to_numpy() == 1
    n_active = int(calib_mask.sum())
    if n_active > 0:
        offsets = rng.integers(30, 180, size=n_active)
        base = pd.Timestamp.now().normalize()
        calib_dates = [ts_to_str(base - pd.Timedelta(days=int(d))) for d in offsets]
        df.loc[calib_mask, "last_calibration"] = calib_dates

    return df


def gen_meters(rng: np.random.Generator, objects_df: pd.DataFrame, n_meters: int) -> pd.DataFrame:
    shares = {"electricity_kwh": 0.50, "water_m3": 0.30, "heating_gcal": 0.20}
    counts = {k: int(round(v * n_meters)) for k, v in shares.items()}
    diff = n_meters - sum(counts.values())
    if diff != 0:
        counts["electricity_kwh"] += diff

    obj_building = objects_df.loc[objects_df["object_type"] == "building", "object_id"].to_numpy()
    obj_substation = objects_df.loc[objects_df["object_type"] == "substation", "object_id"].to_numpy()
    obj_road = objects_df.loc[objects_df["object_type"] == "road_segment", "object_id"].to_numpy()

    def pick_from(pool: np.ndarray, size: int) -> np.ndarray:
        if pool.size == 0:
            all_ids = objects_df["object_id"].to_numpy()
            return rng.choice(all_ids, size=size, replace=True)
        return rng.choice(pool, size=size, replace=True)

    rows = []
    mid = 1

    # electricity
    n = counts["electricity_kwh"]
    pool = np.concatenate([obj_building, obj_substation])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "electricity_kwh",
            "unit": "kWh",
            "is_active": 1 if rng.random() < 0.96 else 0,
        })
        mid += 1

    # water
    n = counts["water_m3"]
    pool = np.concatenate([obj_building, obj_road])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "water_m3",
            "unit": "m3",
            "is_active": 1 if rng.random() < 0.96 else 0,
        })
        mid += 1

    # heating
    n = counts["heating_gcal"]
    obj_ids = pick_from(obj_building, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "heating_gcal",
            "unit": "Gcal",
            "is_active": 1 if rng.random() < 0.95 else 0,
        })
        mid += 1

    return pd.DataFrame(rows)


def gen_events(
        rng: np.random.Generator,
        bounds: CityBounds,
        districts: pd.DataFrame,
        dt_idx: pd.DatetimeIndex,
        n_events: int,
) -> pd.DataFrame:
    dmap = districts.set_index("district_id").to_dict(orient="index")
    district_ids = districts["district_id"].to_numpy()

    start_min = dt_idx[0]
    start_max = dt_idx[-1] - pd.Timedelta(hours=8)

    rows = []
    for eid in range(1, n_events + 1):
        did = int(rng.choice(district_ids))
        info = dmap[did]
        et = str(rng.choice(EVENT_TYPES, p=[0.15, 0.25, 0.20, 0.10, 0.15, 0.15]))

        delta_sec = int((start_max - start_min).total_seconds())
        start_ts = start_min + pd.Timedelta(seconds=int(rng.integers(0, max(delta_sec, 1))))

        if et in ("concert", "sports_event", "festival"):
            dur_h = int(rng.integers(3, 8))
        elif et == "protest":
            dur_h = int(rng.integers(2, 6))
        else:
            dur_h = int(rng.integers(4, 16))
        end_ts = start_ts + pd.Timedelta(hours=dur_h)

        dx_km = float(rng.normal(0.0, 0.9))
        dy_km = float(rng.normal(0.0, 0.9))
        lat = float(info["center_lat"] + (dy_km / 111.0))
        lon = float(info["center_lon"] + (dx_km / (111.0 * math.cos(math.radians(info["center_lat"])) + 1e-9)))
        lat = clamp(lat, bounds.lat_min, bounds.lat_max)
        lon = clamp(lon, bounds.lon_min, bounds.lon_max)

        radius = float(clamp(rng.normal(0.85, 0.35), 0.25, 1.8))

        if et in ("concert", "festival", "sports_event"):
            noise_inc = float(clamp(rng.normal(10.0, 3.0), 4.0, 18.0))
            traffic_inc = float(clamp(rng.normal(28.0, 10.0), 8.0, 65.0))
        elif et in ("construction", "accident"):
            noise_inc = float(clamp(rng.normal(7.0, 3.5), 2.0, 16.0))
            traffic_inc = float(clamp(rng.normal(22.0, 12.0), 5.0, 70.0))
        else:
            noise_inc = float(clamp(rng.normal(6.0, 2.5), 2.0, 14.0))
            traffic_inc = float(clamp(rng.normal(18.0, 10.0), 5.0, 55.0))

        pop = int(info["population"])
        if et in ("concert", "festival", "sports_event"):
            attend = int(clamp(rng.normal(pop * 0.010, pop * 0.002), 300, 25000))
        elif et == "protest":
            attend = int(clamp(rng.normal(pop * 0.006, pop * 0.002), 120, 15000))
        else:
            attend = int(clamp(rng.normal(pop * 0.0035, pop * 0.0015), 80, 8000))

        rows.append({
            "event_id": eid,
            "district_id": did,
            "name": f"{et}_{did}_{eid}",
            "event_type": et,
            "start_ts": ts_to_str(start_ts),
            "end_ts": ts_to_str(end_ts),
            "expected_attendance": attend,
            "lat": lat,
            "lon": lon,
            "impact_radius_km": radius,
            "noise_increase_db": noise_inc,
            "traffic_increase_percent": traffic_inc,
        })
    return pd.DataFrame(rows)


def build_district_time_models(
        rng: np.random.Generator,
        districts: pd.DataFrame,
        dt_idx: pd.DatetimeIndex,
        events_df: pd.DataFrame,
        cfg: GenCfg,
) -> Dict[int, Dict[str, np.ndarray]]:
    T = len(dt_idx)
    hours = dt_idx.hour.to_numpy()
    dow = dt_idx.dayofweek.to_numpy()
    is_weekend = (dow >= 5).astype(float)

    # Temperature
    day_of_year = dt_idx.dayofyear.to_numpy()
    seasonal = 6.0 + 14.5 * np.sin(2.0 * np.pi * (day_of_year / 365.25) - np.pi / 2.0)
    diurnal = 3.5 * np.sin(2.0 * np.pi * (hours / 24.0) - np.pi / 2.0)
    temp_global = seasonal + diurnal + ar1_noise(rng, T, phi=0.88, sigma=0.9) + rng.normal(0.0, 0.6, size=T)
    temp_global = np.clip(temp_global, -30.0, 35.0)

    traffic_shape = daily_traffic_profile(hours)
    weekend_factor = 1.0 - 0.28 * is_weekend

    # Long-term trends
    trend_traffic = np.ones(T)
    if cfg.enable_long_term_trends and cfg.days > 180:
        years = np.arange(T) / (365.25 * 24 / cfg.step_hours)
        trend_traffic = 1.0 + (cfg.traffic_growth_percent_per_year / 100.0) * years

    ev_by_d: Dict[int, List[Dict[str, Any]]] = {}
    for r in events_df.to_dict(orient="records"):
        did = int(r["district_id"])
        ev_by_d.setdefault(did, []).append(r)

    models: Dict[int, Dict[str, np.ndarray]] = {}

    for row in districts.to_dict(orient="records"):
        did = int(row["district_id"])
        t = str(row["type"])
        dens = str(row["density"])
        ic = float(row["industrial_coeff"])

        temp_offset = float(rng.normal(0.0, 0.6))
        temp = temp_global + temp_offset

        base = 120.0 * density_mult(dens) * type_traffic_mult(t)
        traffic = base * traffic_shape * weekend_factor * trend_traffic
        traffic = traffic * (1.0 + 0.08 * ar1_noise(rng, T, phi=0.80, sigma=0.25))
        traffic = traffic + rng.normal(0.0, 8.0, size=T)
        traffic = np.clip(traffic, 5.0, 900.0)

        pm = (8.0 + 28.0 * ic) + 0.055 * traffic + ar1_noise(rng, T, phi=0.75, sigma=1.2) + rng.normal(0.0, 1.2, size=T)

        episodes = max(1, int(len(dt_idx) / (24 * 50)))
        if ic > 0.35 and rng.random() < 0.65:
            episodes += 1

        pm_add = np.zeros(T, dtype=float)
        for _ in range(episodes):
            start_i = int(rng.integers(0, max(T - 48, 1)))
            dur = int(rng.integers(24, 72))
            amp = float(rng.uniform(12.0, 35.0)) * (0.7 + 0.6 * ic)
            end_i = min(T, start_i + dur)
            pm_add[start_i:end_i] += amp

        pm = pm + pm_add
        pm = np.clip(pm, 2.0, 180.0)

        event_active = np.zeros(T, dtype=bool)
        event_after = np.zeros(T, dtype=bool)
        event_ca = np.zeros(T, dtype=bool)

        for ev in ev_by_d.get(did, []):
            s = pd.Timestamp(ev["start_ts"])
            e = pd.Timestamp(ev["end_ts"])
            s_i = int(np.searchsorted(dt_idx.values, s.to_datetime64(), side="left"))
            e_i = int(np.searchsorted(dt_idx.values, e.to_datetime64(), side="right"))
            s_i = int(clamp(s_i, 0, T))
            e_i = int(clamp(e_i, 0, T))
            event_active[s_i:e_i] = True

            after_end = e + pd.Timedelta(hours=24)
            a_i1 = e_i
            a_i2 = int(np.searchsorted(dt_idx.values, after_end.to_datetime64(), side="right"))
            a_i2 = int(clamp(a_i2, 0, T))
            event_after[a_i1:a_i2] = True

            if ev["event_type"] in ("construction", "accident"):
                event_ca[s_i:e_i] = True
                event_ca[a_i1:a_i2] = True

            traffic_mult = 1.0 + float(ev["traffic_increase_percent"]) / 100.0
            traffic[s_i:e_i] = traffic[s_i:e_i] * traffic_mult

            if ev["event_type"] in ("construction", "accident"):
                pm[s_i:e_i] = pm[s_i:e_i] + float(rng.uniform(3.0, 12.0))

        models[did] = {
            "temp_c_proxy": temp,
            "traffic_proxy": traffic,
            "pm25_proxy": pm,
            "event_active": event_active,
            "event_after_24h": event_after,
            "event_ca": event_ca,
        }

    return models


def build_sensor_impacts(
        sensors_df: pd.DataFrame,
        objects_df: pd.DataFrame,
        events_df: pd.DataFrame,
        dt_idx: pd.DatetimeIndex,
) -> List[List[Tuple[int, int, float, float, str]]]:
    T = len(dt_idx)
    obj_coords = objects_df.set_index("object_id")[["lat", "lon"]]
    s_obj = sensors_df.set_index("sensor_id")["object_id"].to_dict()

    s_lat = np.zeros(len(sensors_df) + 1, dtype=float)
    s_lon = np.zeros(len(sensors_df) + 1, dtype=float)
    for sid, oid in s_obj.items():
        lat = float(obj_coords.loc[oid, "lat"])
        lon = float(obj_coords.loc[oid, "lon"])
        s_lat[int(sid)] = lat
        s_lon[int(sid)] = lon

    impacts: List[List[Tuple[int, int, float, float, str]]] = [[] for _ in range(len(sensors_df) + 1)]

    dt_values = dt_idx.values

    for ev in events_df.to_dict(orient="records"):
        ev_lat = float(ev["lat"])
        ev_lon = float(ev["lon"])
        radius = float(ev["impact_radius_km"])
        noise_inc = float(ev["noise_increase_db"])
        traffic_inc = float(ev["traffic_increase_percent"])
        et = str(ev["event_type"])

        s = pd.Timestamp(ev["start_ts"]).to_datetime64()
        e = pd.Timestamp(ev["end_ts"]).to_datetime64()
        s_i = int(np.searchsorted(dt_values, s, side="left"))
        e_i = int(np.searchsorted(dt_values, e, side="right"))
        s_i = int(clamp(s_i, 0, T))
        e_i = int(clamp(e_i, 0, T))
        if e_i <= s_i:
            continue

        d = haversine_km(s_lat[1:], s_lon[1:], ev_lat, ev_lon)
        affected = np.where(d <= radius)[0] + 1
        if affected.size == 0:
            continue

        traffic_mult = 1.0 + traffic_inc / 100.0
        for sid in affected.tolist():
            impacts[sid].append((s_i, e_i, noise_inc, traffic_mult, et))

    return impacts


def gen_sensor_series(
        rng: np.random.Generator,
        sensor_row: Dict[str, Any],
        object_row: Dict[str, Any],
        district_row: Dict[str, Any],
        models: Dict[int, Dict[str, np.ndarray]],
        impacts: List[Tuple[int, int, float, float, str]],
        dt_idx: pd.DatetimeIndex,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    did = int(object_row["district_id"])
    m = models[did]
    T = len(dt_idx)
    hours = dt_idx.hour.to_numpy()

    st = str(sensor_row["sensor_type"])
    dens = str(district_row["density"])
    dtype = str(district_row["type"])
    ic = float(district_row["industrial_coeff"])

    ot = str(object_row["object_type"])
    if ot == "road_segment":
        obj_f = 1.15
    elif ot in ("stop", "parking"):
        obj_f = 1.05
    elif ot == "streetlight":
        obj_f = 0.95
    elif ot == "park":
        obj_f = 0.80
    else:
        obj_f = 1.00

    traffic = m["traffic_proxy"]

    if st == "temp_c":
        vals = m["temp_c_proxy"] + rng.normal(0.0, 0.35, size=T)
        vals = np.clip(vals, -35.0, 45.0)
    elif st == "traffic_intensity":
        vals = traffic * obj_f + rng.normal(0.0, 10.0, size=T)
        vals = np.clip(vals, 0.0, 1200.0)
        for (s_i, e_i, _noise_add, traffic_mult, _et) in impacts:
            vals[s_i:e_i] = vals[s_i:e_i] * traffic_mult
    elif st == "noise_db":
        night = ((hours <= 5) | (hours >= 23)).astype(float)
        night_floor = 28.0 + 2.0 * (dtype in ("commercial", "mixed"))
        base = 33.0 + 4.0 * density_mult(dens) + 2.0 * (dtype in ("commercial", "mixed"))
        vals = base + 0.065 * (traffic * obj_f) - 7.5 * night + night_floor * night
        vals = vals + ar1_noise(rng, T, phi=0.70, sigma=0.9) + rng.normal(0.0, 1.1, size=T)
        for (s_i, e_i, noise_add, _traffic_mult, _et) in impacts:
            vals[s_i:e_i] = vals[s_i:e_i] + noise_add
        vals = np.clip(vals, 20.0, 110.0)
    else:  # pm25
        pm = m["pm25_proxy"]
        vals = pm * (0.85 + 0.30 * obj_f) + rng.normal(0.0, 2.0, size=T)
        for (s_i, e_i, _noise_add, _traffic_mult, et) in impacts:
            if et in ("construction", "accident"):
                vals[s_i:e_i] = vals[s_i:e_i] + float(rng.uniform(2.0, 10.0))
        vals = np.clip(vals, 1.0, 250.0)

    q = np.zeros(T, dtype=np.int8)
    anomaly = np.zeros(T, dtype=float)
    return vals.astype(float), q, anomaly


def apply_quality_policy(
        rng: np.random.Generator,
        vals: np.ndarray,
        q: np.ndarray,
        anomaly: np.ndarray,
        missing_windows: Optional[List[Tuple[int, int]]],
        spikes: Optional[List[int]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    T = int(vals.shape[0])

    if missing_windows:
        for (s_i, e_i) in missing_windows:
            s_i = int(clamp(s_i, 0, T))
            e_i = int(clamp(e_i, 0, T))
            if e_i > s_i:
                q[s_i:e_i] = 1
                vals[s_i:e_i] = 0.0
                anomaly[s_i:e_i] = 0.0

    applied_spikes: List[int] = []
    if spikes:
        for idx in spikes:
            idx = int(idx)
            if 0 <= idx < T and q[idx] != 1:
                q[idx] = 2
                amp = float(rng.uniform(1.6, 3.2))
                vals[idx] = float(vals[idx] * amp + rng.normal(0.0, 1.5))
                applied_spikes.append(idx)

    if applied_spikes:
        v_for_calc = vals.astype(float).copy()
        v_for_calc[q == 1] = np.nan

        s = pd.Series(v_for_calc)
        med = s.rolling(window=24, min_periods=12, center=True).median()
        mad = (s - med).abs().rolling(window=24, min_periods=12, center=True).median()

        eps = 1e-6
        K = 6.0
        global_med = float(np.nanmedian(v_for_calc)) if np.any(~np.isnan(v_for_calc)) else 0.0
        global_mad = float(np.nanmedian(np.abs(v_for_calc - global_med))) if np.any(~np.isnan(v_for_calc)) else 1.0
        global_mad = max(global_mad, eps)

        for idx in applied_spikes:
            m = med.iloc[idx]
            d = mad.iloc[idx]

            m_val = float(m) if pd.notna(m) else global_med
            d_val = float(d) if pd.notna(d) else global_mad
            d_val = max(d_val, eps)

            score = abs(float(vals[idx]) - m_val) / (d_val + eps) / K
            score = float(min(1.0, max(0.05, score)))
            anomaly[idx] = score

    anomaly[q == 0] = 0.0
    anomaly[q == 1] = 0.0

    return vals, q, anomaly


def gen_sensor_readings_and_insert(
        rng: np.random.Generator,
        conn: sqlite3.Connection,
        sensors_df: pd.DataFrame,
        objects_df: pd.DataFrame,
        districts_df: pd.DataFrame,
        models: Dict[int, Dict[str, np.ndarray]],
        sensor_impacts: List[List[Tuple[int, int, float, float, str]]],
        quality_cfg: QualityCfg,
        dt_idx: pd.DatetimeIndex,
        log_path: Path,
        flush_rows: int = 120_000,
) -> None:
    T = len(dt_idx)
    n_sensors = len(sensors_df)
    total_readings = n_sensors * T

    # Target shares for quality flags (as required by validation)
    # missing: 3-7%, suspect: 1-2%
    target_missing_share = float(rng.uniform(0.038, 0.052))  # 3.8-5.2% target (conservative to stay under 7%)
    target_suspect_share = float(rng.uniform(0.012, 0.016))  # 1.2-1.6% target

    # Use more sensors with issues to distribute the load better
    # This reduces per-sensor burden and minimizes overlap
    missing_sensor_share = float(rng.uniform(
        max(quality_cfg.missing_sensor_share_min, 0.15),  # At least 15%
        max(quality_cfg.missing_sensor_share_max, 0.25)  # Up to 25%
    ))
    suspect_sensor_share = float(rng.uniform(
        max(quality_cfg.suspect_sensor_share_min, 0.12),  # At least 12%
        max(quality_cfg.suspect_sensor_share_max, 0.20)  # Up to 20%
    ))

    n_missing_sensors = int(round(n_sensors * missing_sensor_share))
    n_suspect_sensors = int(round(n_sensors * suspect_sensor_share))

    # Ensure at least some sensors have issues
    n_missing_sensors = max(n_missing_sensors, 50)
    n_suspect_sensors = max(n_suspect_sensors, 50)

    # Calculate readings per affected sensor to achieve target shares
    target_missing_readings = int(target_missing_share * total_readings)
    target_suspect_readings = int(target_suspect_share * total_readings)

    # Account for window overlap - use higher factor since windows overlap significantly
    # Also account for suspect readings that might fall on missing slots
    overlap_factor_missing = 1.6  # Windows overlap ~40%
    overlap_factor_suspect = 1.2  # Some spikes may land on same positions

    readings_per_missing_sensor = int(target_missing_readings * overlap_factor_missing / n_missing_sensors)
    readings_per_suspect_sensor = int(target_suspect_readings * overlap_factor_suspect / n_suspect_sensors)

    # Clamp to reasonable ranges but allow more readings
    readings_per_missing_sensor = max(48, min(readings_per_missing_sensor, T * 2 // 3))
    readings_per_suspect_sensor = max(30, min(readings_per_suspect_sensor, T // 2))

    sensor_ids = sensors_df["sensor_id"].to_numpy()
    missing_sids = set(
        rng.choice(sensor_ids, size=min(n_missing_sensors, len(sensor_ids)), replace=False).tolist()
    ) if n_missing_sensors > 0 else set()

    remaining = np.array([sid for sid in sensor_ids if sid not in missing_sids], dtype=int)
    suspect_sids = set(
        rng.choice(remaining, size=min(n_suspect_sensors, len(remaining)), replace=False).tolist()
    ) if n_suspect_sensors > 0 and len(remaining) > 0 else set()

    obj_map = objects_df.set_index("object_id").to_dict(orient="index")
    dist_map = districts_df.set_index("district_id").to_dict(orient="index")

    insert_sql = "INSERT INTO sensor_readings (sensor_id, ts, value, quality_flag, anomaly_score) VALUES (?,?,?,?,?)"
    buffer: List[Tuple[int, str, float, str, float]] = []

    for i, srow in enumerate(sensors_df.to_dict(orient="records"), start=1):
        sid = int(srow["sensor_id"])
        oid = int(srow["object_id"])
        did = int(obj_map[oid]["district_id"])

        vals, q, anomaly = gen_sensor_series(
            rng=rng,
            sensor_row=srow,
            object_row=obj_map[oid],
            district_row=dist_map[did],
            models=models,
            impacts=sensor_impacts[sid],
            dt_idx=dt_idx,
        )

        missing_windows = None
        if sid in missing_sids:
            # Calculate windows to achieve target readings per sensor
            target_hours = readings_per_missing_sensor

            # Use fewer, larger windows to reduce overlap
            n_windows = int(rng.integers(3, 7))
            avg_hours_per_window = target_hours // n_windows

            missing_windows = []
            for _ in range(n_windows):
                # Vary window size around the average
                win_h = int(rng.integers(
                    max(quality_cfg.missing_window_hours_min, avg_hours_per_window * 2 // 3),
                    max(quality_cfg.missing_window_hours_max * 2, avg_hours_per_window * 4 // 3) + 1
                ))
                win_h = min(win_h, T // 2)  # Allow larger windows
                start_i = int(rng.integers(0, max(T - win_h, 1)))
                missing_windows.append((start_i, start_i + win_h))

        spikes = None
        if sid in suspect_sids:
            # Calculate spikes to achieve target readings per sensor
            n_spikes = readings_per_suspect_sensor
            # Add some randomness but keep close to target
            n_spikes = int(rng.integers(max(n_spikes * 3 // 4, 20), n_spikes + n_spikes // 4 + 1))
            n_spikes = min(n_spikes, T * 2 // 3)  # Allow more spikes
            spikes = rng.integers(0, T, size=n_spikes).tolist()

        vals, q, anomaly = apply_quality_policy(rng, vals, q, anomaly, missing_windows, spikes)

        q_str = np.where(q == 0, "ok", np.where(q == 1, "missing", "suspect"))

        for t_i, ts in enumerate(dt_idx):
            buffer.append((sid, ts_to_str(ts), float(vals[t_i]), str(q_str[t_i]), float(anomaly[t_i])))

        if len(buffer) >= flush_rows:
            conn.executemany(insert_sql, buffer)
            buffer.clear()
            if i % 250 == 0:
                log_line(log_path, f"sensor_readings inserted for {i} sensors")

    if buffer:
        conn.executemany(insert_sql, buffer)
        buffer.clear()

    log_line(log_path,
             f"sensor_readings done (target_missing={target_missing_share:.4f}, target_suspect={target_suspect_share:.4f}, missing_sensors={n_missing_sensors}, suspect_sensors={n_suspect_sensors})")


def gen_meter_readings_and_insert(
        rng: np.random.Generator,
        conn: sqlite3.Connection,
        meters_df: pd.DataFrame,
        objects_df: pd.DataFrame,
        districts_df: pd.DataFrame,
        models: Dict[int, Dict[str, np.ndarray]],
        dt_idx: pd.DatetimeIndex,
        log_path: Path,
        flush_rows: int = 120_000,
) -> None:
    T = len(dt_idx)
    hours = dt_idx.hour.to_numpy()

    def daily_consumption_profile(hours: np.ndarray, kind: str) -> np.ndarray:
        h = hours.astype(float)
        if kind == "electricity":
            m1 = stats.norm.pdf(h, loc=8.0, scale=2.0)
            m2 = stats.norm.pdf(h, loc=19.0, scale=2.5)
            base = 0.55 + 2.3 * m1 + 2.9 * m2
            return base / base.mean()
        if kind == "water":
            m1 = stats.norm.pdf(h, loc=7.5, scale=2.2)
            m2 = stats.norm.pdf(h, loc=20.0, scale=2.0)
            base = 0.65 + 1.6 * m1 + 1.8 * m2
            return base / base.mean()
        m1 = stats.norm.pdf(h, loc=7.0, scale=2.8)
        m2 = stats.norm.pdf(h, loc=21.0, scale=3.0)
        base = 0.75 + 1.1 * m1 + 1.2 * m2
        return base / base.mean()

    prof_e = daily_consumption_profile(hours, "electricity")
    prof_w = daily_consumption_profile(hours, "water")
    prof_h = daily_consumption_profile(hours, "heating")

    obj_map = objects_df.set_index("object_id")[["district_id", "object_type"]].to_dict(orient="index")
    dmap = districts_df.set_index("district_id")[["density", "income_level"]].to_dict(orient="index")

    insert_sql = "INSERT INTO meter_readings (meter_id, ts, value, is_peak) VALUES (?,?,?,?)"
    buffer: List[Tuple[int, str, float, int]] = []

    for i, mrow in enumerate(meters_df.to_dict(orient="records"), start=1):
        mid = int(mrow["meter_id"])
        oid = int(mrow["object_id"])
        ut = str(mrow["utility_type"])

        did = int(obj_map[oid]["district_id"])
        den = str(dmap[did]["density"])
        inc = str(dmap[did]["income_level"])

        temp = models[did]["temp_c_proxy"]

        if ut == "electricity_kwh":
            base = 0.9 + 0.35 * density_mult(den) + (0.18 if inc == "high" else 0.0) - (0.08 if inc == "low" else 0.0)
            cold = np.clip((5.0 - temp) / 30.0, 0.0, 1.0)
            vals = base * prof_e * (1.0 + 0.75 * cold) + rng.normal(0.0, 0.07, size=T)
            vals = np.clip(vals, 0.05, None)
        elif ut == "water_m3":
            base = 0.11 + 0.03 * density_mult(den) + (0.01 if inc == "high" else 0.0)
            vals = base * prof_w + rng.normal(0.0, 0.01, size=T)
            vals = np.clip(vals, 0.01, None)
        else:
            heat_need = np.clip((18.0 - temp) / 18.0, 0.0, 1.7)
            base = 0.06 + 0.03 * density_mult(den)
            vals = base * prof_h * (0.2 + 1.35 * heat_need) + rng.normal(0.0, 0.015, size=T)
            vals = np.clip(vals, 0.0, None)

        thr = float(np.quantile(vals, 0.9))
        is_peak = (vals >= thr).astype(int)

        for t_i, ts in enumerate(dt_idx):
            buffer.append((mid, ts_to_str(ts), float(vals[t_i]), int(is_peak[t_i])))

        if len(buffer) >= flush_rows:
            conn.executemany(insert_sql, buffer)
            buffer.clear()
            if i % 200 == 0:
                log_line(log_path, f"meter_readings inserted for {i} meters")

    if buffer:
        conn.executemany(insert_sql, buffer)
        buffer.clear()

    log_line(log_path, "meter_readings done")


def gen_citizen_requests(
        rng: np.random.Generator,
        districts: pd.DataFrame,
        objects_df: pd.DataFrame,
        models: Dict[int, Dict[str, np.ndarray]],
        dt_idx: pd.DatetimeIndex,
        n_requests: int,
) -> pd.DataFrame:
    T = len(dt_idx)
    district_ids = districts["district_id"].to_numpy()

    w = districts["population"].to_numpy(dtype=float)
    w = w / w.sum()

    dmap = districts.set_index("district_id").to_dict(orient="index")

    obj_by_d_and_type: Dict[Tuple[int, str], np.ndarray] = {}
    for did in district_ids.tolist():
        did = int(did)
        for ot in OBJECT_TYPES:
            arr = objects_df.loc[
                (objects_df["district_id"] == did) & (objects_df["object_type"] == ot), "object_id"].to_numpy()
            obj_by_d_and_type[(did, ot)] = arr

    def pick_obj(did: int, category: str) -> Optional[int]:
        if category == "pothole":
            # Prefer poor condition roads for pothole complaints
            pool_all = obj_by_d_and_type[(did, "road_segment")]
            if pool_all.size > 0:
                # Get road conditions
                road_conditions = objects_df.loc[objects_df["object_id"].isin(pool_all), ["object_id", "condition"]]
                poor_roads = road_conditions[road_conditions["condition"] == "poor"]["object_id"].to_numpy()
                fair_roads = road_conditions[road_conditions["condition"] == "fair"]["object_id"].to_numpy()
                good_roads = road_conditions[road_conditions["condition"] == "good"]["object_id"].to_numpy()

                # 60% chance to pick from poor roads, 30% fair, 10% good
                r = rng.random()
                if r < 0.6 and poor_roads.size > 0:
                    return int(rng.choice(poor_roads))
                elif r < 0.9 and fair_roads.size > 0:
                    return int(rng.choice(fair_roads))
                elif good_roads.size > 0:
                    return int(rng.choice(good_roads))
                # Fallback to any road
                return int(rng.choice(pool_all))
            return None
        elif category == "broken_streetlight":
            pool = obj_by_d_and_type[(did, "streetlight")]
        elif category == "parking_issue":
            pool = np.concatenate([obj_by_d_and_type[(did, "parking")], obj_by_d_and_type[(did, "stop")]])
        elif category == "water_leak":
            pool = obj_by_d_and_type[(did, "road_segment")]
        elif category == "heating_issue":
            pool = obj_by_d_and_type[(did, "building")]
        elif category == "noise_complaint":
            pool = np.concatenate([obj_by_d_and_type[(did, "road_segment")], obj_by_d_and_type[(did, "stop")],
                                   obj_by_d_and_type[(did, "parking")]])
        else:
            pool = np.concatenate([obj_by_d_and_type[(did, "park")], obj_by_d_and_type[(did, "road_segment")]])
        if pool.size == 0:
            return None
        return int(rng.choice(pool))

    hours = dt_idx.hour.to_numpy()
    tod = (0.35 + 0.65 * (
            stats.norm.pdf(hours.astype(float), loc=12.0, scale=4.0) / stats.norm.pdf(12.0, loc=12.0, scale=4.0)))
    tod = tod / tod.sum()

    rows = []
    for rid in range(1, n_requests + 1):
        did = int(rng.choice(district_ids, p=w))
        info = dmap[did]
        m = models[did]

        if rng.random() < 0.70:
            t_i = int(rng.choice(np.arange(T), p=tod))
        else:
            t_i = int(rng.integers(0, T))
        created = dt_idx[t_i]
        created_ts = ts_to_str(created)

        temp = float(m["temp_c_proxy"][t_i])
        pm = float(m["pm25_proxy"][t_i])
        ev_after = bool(m["event_after_24h"][t_i])
        ev_ca = bool(m["event_ca"][t_i])

        p = np.array([0.16, 0.14, 0.12, 0.10, 0.10, 0.16, 0.22], dtype=float)
        if ev_after:
            p[0] *= 2.1
            p[5] *= 1.9
            if ev_ca:
                p[1] *= 1.6
        if temp < 0.0:
            cold_mult = 1.0 + min(1.2, (-temp) / 10.0)
            if info["income_level"] == "low":
                cold_mult *= 1.25
            if info["density"] in ("high", "very_high"):
                cold_mult *= 1.15
            p[4] *= cold_mult
        # C: Trафик -> Загрязнение -> Жалобы
        # При высоком traffic_intensity (> порога):
        # растет pm25 (коэффициент 0.005-0.01)
        # Если pm25 > 35 мкг/м³ в течение 4+ часов:
        # растет вероятность air_quality обращений в 3-5 раз
        if pm > 35.0:
            # УСИЛЕНО: при высоком PM2.5 вероятность air_quality жалоб растёт сильнее
            pm_factor = 1.0 + min(6.0, (pm - 35.0) / 15.0)  # До 7x при очень высоком PM
            p[6] *= pm_factor

        p = p / p.sum()
        category = str(rng.choice(REQUEST_CATEGORIES, p=p))

        obj_id = pick_obj(did, category)

        pr = "low"
        if category in ("water_leak", "heating_issue"):
            pr = str(rng.choice(["medium", "high"], p=[0.7, 0.3])) if (temp < 0.0 or rng.random() < 0.35) else "medium"
        elif category in ("air_quality", "noise_complaint"):
            pr = str(rng.choice(["low", "medium", "high"], p=[0.55, 0.35, 0.10]))
        else:
            pr = str(rng.choice(["low", "medium", "high"], p=[0.65, 0.30, 0.05]))

        status = str(rng.choice(["new", "in_progress", "resolved", "rejected"], p=[0.18, 0.22, 0.55, 0.05]))
        resolved_ts = None
        resolution_hours = None
        if status == "resolved":
            rh = float(clamp(rng.lognormal(mean=2.2, sigma=0.55), 1.0, 240.0))
            resolution_hours = rh
            resolved_ts = ts_to_str(created + pd.Timedelta(hours=rh))
        elif status == "rejected":
            if rng.random() < 0.6:
                rh = float(clamp(rng.uniform(1.0, 12.0), 0.5, 48.0))
                resolution_hours = rh
                resolved_ts = ts_to_str(created + pd.Timedelta(hours=rh))

        desc = None
        if rng.random() < 0.45:
            desc = f"{category} reported by citizen; district={did}"

        rows.append({
            "request_id": rid,
            "district_id": did,
            "object_id": obj_id,
            "category": category,
            "created_ts": created_ts,
            "status": status,
            "resolved_ts": resolved_ts,
            "resolution_hours": resolution_hours,
            "priority": pr,
            "description": desc,
        })

    return pd.DataFrame(rows)


def gen_public_transport_trips(
        rng: np.random.Generator,
        objects_df: pd.DataFrame,
        models: Dict[int, Dict[str, np.ndarray]],
        dt_idx: pd.DatetimeIndex,
        n_trips: int,
) -> pd.DataFrame:
    stops = objects_df.loc[objects_df["object_type"] == "stop", ["object_id", "district_id"]]
    if stops.empty:
        stops = objects_df.sample(min(50, len(objects_df)), random_state=1)[["object_id", "district_id"]]

    stop_ids = stops["object_id"].to_numpy()
    stop_did = stops["district_id"].to_numpy()

    routes = [f"R{str(i).zfill(2)}" for i in range(1, 21)]
    vehicles = [f"V{str(i).zfill(3)}" for i in range(1, 201)]

    T = len(dt_idx)

    rows = []
    for tid in range(1, n_trips + 1):
        rno = str(rng.choice(routes))
        vid = str(rng.choice(vehicles))

        j = int(rng.integers(0, len(stop_ids)))
        soid = int(stop_ids[j])
        did = int(stop_did[j])

        t_i = int(rng.integers(0, T))
        base_ts = dt_idx[t_i]
        minute = int(rng.integers(0, 60))
        scheduled = base_ts.replace(minute=minute, second=0)
        scheduled_ts = ts_to_str(scheduled)

        m = models[did]
        traffic = float(m["traffic_proxy"][t_i])
        temp = float(m["temp_c_proxy"][t_i])
        ev_ca = bool(m["event_ca"][t_i])

        w = "clear"
        u = rng.random()
        if temp < -2.5 and u < 0.55:
            w = "snow"
        elif u < 0.12:
            w = "rain"
        elif u < 0.17:
            w = "fog"

        base_delay = 0.6 + 0.018 * max(0.0, traffic - 110.0)
        if w == "rain":
            base_delay += 1.3
        elif w == "snow":
            base_delay += 2.6
        elif w == "fog":
            base_delay += 1.0
        if ev_ca:
            base_delay += 1.8

        noise = float(rng.normal(0.0, 1.2))
        delay = int(max(0, round(base_delay + noise)))

        actual = scheduled + pd.Timedelta(minutes=delay)
        actual_ts = ts_to_str(actual)

        hour = int(base_ts.hour)
        peak = 1.0 + 0.45 * (7 <= hour <= 10) + 0.55 * (17 <= hour <= 20)
        weekend = 0.85 if base_ts.dayofweek >= 5 else 1.0
        pax = int(max(0, rng.normal(18.0 * peak * weekend + 0.03 * traffic, 6.0)))
        pax = int(clamp(pax, 0, 160))

        rows.append({
            "trip_id": tid,
            "route_no": rno,
            "vehicle_id": vid,
            "stop_object_id": soid,
            "scheduled_ts": scheduled_ts,
            "actual_ts": actual_ts,
            "delay_minutes": delay,
            "passenger_estimate": pax,
            "weather_condition": w,
        })

    return pd.DataFrame(rows)


def export_csv(conn: sqlite3.Connection, csv_dir: Path, tables: List[str]) -> None:
    ensure_dir(csv_dir)
    for t in tables:
        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
        df.to_csv(csv_dir / f"{t}.csv", index=False, encoding="utf-8")


def main() -> None:
    # Переход в корень проекта (на уровень выше scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    cfg_path = Path("configs/citygrid_generation.yaml")
    if len(os.sys.argv) >= 2:
        cfg_path = Path(os.sys.argv[1])

    cfg = load_config(cfg_path)

    scale = cfg.generation.scale
    if scale not in SCALE_DEFAULTS:
        raise ValueError(f"Unknown scale: {scale}")

    counts = dict(SCALE_DEFAULTS[scale])
    n_districts = int(counts["districts"])
    n_nodes = int(counts["nodes"])
    n_objects = int(counts["objects"])
    n_sensors = int(counts["sensors"])
    n_meters = int(counts["meters"])
    n_events = int(counts["events"])
    n_requests = int(counts["requests"])
    n_trips = int(counts["trips"])

    out_db = Path(cfg.output.sqlite_path)
    out_csv = Path(cfg.output.csv_dir)
    out_log = Path(cfg.output.log_file)
    out_docs = Path(cfg.output.docs_dir)
    ensure_dir(out_log.parent)

    out_log.write_text("", encoding="utf-8")

    log_line(out_log, "START build_db with road network")
    log_line(out_log, f"config={cfg_path}")
    log_line(out_log,
             f"seed={cfg.generation.seed}, start_date={cfg.generation.start_date}, days={cfg.generation.days}, scale={scale}")

    ensure_workspace_docs(out_docs)

    rng = np.random.default_rng(cfg.generation.seed)
    dt_idx = dt_range(cfg.generation.start_date, cfg.generation.days, cfg.generation.step_hours)

    conn = create_connection(out_db)
    try:
        init_db(conn)
        log_line(out_log, "DB initialized")

        # Districts
        districts = gen_districts(rng, cfg.geography_bounds, n_districts)
        with conn:
            insert_df(conn, "districts", districts)
        log_line(out_log, f"districts inserted: {len(districts)}")

        # Road network
        nodes_df, road_edges = gen_road_network(rng, cfg.geography_bounds, districts, n_nodes)
        with conn:
            insert_df(conn, "road_network_nodes", nodes_df)
        log_line(out_log, f"road_network_nodes inserted: {len(nodes_df)}, edges: {len(road_edges)}")

        # Objects (including road segments)
        objects_df = gen_city_objects(rng, cfg.geography_bounds, districts, nodes_df, road_edges, n_objects,
                                      cfg.generation.start_date)
        with conn:
            insert_df(conn, "city_objects", objects_df)
        log_line(out_log,
                 f"city_objects inserted: {len(objects_df)}, road_segments: {len(objects_df[objects_df['object_type'] == 'road_segment'])}")

        # Sensors
        sensors_df = gen_sensors(rng, objects_df, n_sensors)
        with conn:
            insert_df(conn, "sensors", sensors_df)
        log_line(out_log, f"sensors inserted: {len(sensors_df)}")

        # Meters
        meters_df = gen_meters(rng, objects_df, n_meters)
        with conn:
            insert_df(conn, "smart_meters", meters_df)
        log_line(out_log, f"smart_meters inserted: {len(meters_df)}")

        # Events
        events_df = gen_events(rng, cfg.geography_bounds, districts, dt_idx, n_events)
        with conn:
            insert_df(conn, "municipal_events", events_df)
        log_line(out_log, f"municipal_events inserted: {len(events_df)}")

        # District time models
        models = build_district_time_models(rng, districts, dt_idx, events_df, cfg.generation)
        log_line(out_log, "district time models built")

        # Sensor impacts
        sensor_impacts = build_sensor_impacts(sensors_df, objects_df, events_df, dt_idx)
        log_line(out_log, "sensor impacts built")

        # Citizen requests
        requests_df = gen_citizen_requests(rng, districts, objects_df, models, dt_idx, n_requests)
        with conn:
            insert_df(conn, "citizen_requests", requests_df)
        log_line(out_log, f"citizen_requests inserted: {len(requests_df)}")

        # Transport trips
        trips_df = gen_public_transport_trips(rng, objects_df, models, dt_idx, n_trips)
        with conn:
            insert_df(conn, "public_transport_trips", trips_df)
        log_line(out_log, f"public_transport_trips inserted: {len(trips_df)}")

        # Readings (large tables)
        with conn:
            gen_sensor_readings_and_insert(
                rng=rng,
                conn=conn,
                sensors_df=sensors_df,
                objects_df=objects_df,
                districts_df=districts,
                models=models,
                sensor_impacts=sensor_impacts,
                quality_cfg=cfg.quality,
                dt_idx=dt_idx,
                log_path=out_log,
            )

        with conn:
            gen_meter_readings_and_insert(
                rng=rng,
                conn=conn,
                meters_df=meters_df,
                objects_df=objects_df,
                districts_df=districts,
                models=models,
                dt_idx=dt_idx,
                log_path=out_log,
            )

        # Indexes
        create_indexes(conn)
        log_line(out_log, "indexes created")

        # CSV exports
        export_csv(conn, out_csv, [
            "districts", "road_network_nodes", "city_objects", "sensors", "smart_meters",
            "municipal_events", "citizen_requests", "public_transport_trips",
        ])
        log_line(out_log, "csv export done")

        # Meta
        meta = {
            "seed": cfg.generation.seed,
            "start_date": cfg.generation.start_date,
            "days": cfg.generation.days,
            "step_hours": cfg.generation.step_hours,
            "scale": scale,
            "timezone": cfg.generation.timezone,
            "counts": {
                "districts": n_districts,
                "nodes": n_nodes,
                "objects": n_objects,
                "road_segments": len(objects_df[objects_df['object_type'] == 'road_segment']),
                "sensors": n_sensors,
                "meters": n_meters,
                "events": n_events,
                "requests": n_requests,
                "trips": n_trips,
                "time_points": len(dt_idx),
            },
        }
        meta_path = Path("outputs") / "generation_meta.json"
        ensure_dir(meta_path.parent)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log_line(out_log, f"meta saved: {meta_path}")

        log_line(out_log, "DONE build_db")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
