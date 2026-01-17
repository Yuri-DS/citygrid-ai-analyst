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
from typing import Any, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import yaml
from scipy import stats  # обязательная зависимость по ТЗ


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
    # Векторизованная гаверсин-формула
    r = 6371.0
    phi1 = np.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * math.cos(phi2) * np.sin(dlmb / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
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


def safe_int(x: Any) -> int:
    if x is None:
        return 0
    return int(x)


# ----------------------------
# Config + scale
# ----------------------------

SCALE_DEFAULTS = {
    "small":  {"districts": 5,  "objects": 500,  "sensors": 750,  "meters": 300,  "events": 75,  "requests": 10_000, "trips": 50_000},
    "medium": {"districts": 10, "objects": 2000, "sensors": 3000, "meters": 1200, "events": 300, "requests": 40_000, "trips": 200_000},
    "large":  {"districts": 15, "objects": 4000, "sensors": 6000, "meters": 2500, "events": 600, "requests": 80_000, "trips": 400_000},
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

CREATE TABLE city_objects (
    object_id INTEGER PRIMARY KEY,
    district_id INTEGER NOT NULL REFERENCES districts(district_id),
    object_type TEXT NOT NULL CHECK(object_type IN ('building','road_segment','streetlight','stop','parking','substation','park')),
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    install_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','inactive','under_repair')),
    capacity INTEGER NULL
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

CREATE INDEX idx_sensors_type ON sensors(sensor_type);

CREATE INDEX idx_public_transport_route_time ON public_transport_trips(route_no, scheduled_ts);
"""


# ----------------------------
# Workspace docs templates
# ----------------------------

DOC_DATA_DICTIONARY = """# CityGrid - Data Dictionary

Ниже краткое описание таблиц и ключевых полей.

## districts
- district_id: PK
- type: residential/commercial/industrial/mixed/recreational/educational
- industrial_coeff: [0..1]
- center_lat, center_lon: центр района
- geometry: WKT (опционально)

## city_objects
- object_id: PK
- district_id: FK -> districts
- object_type: building/road_segment/streetlight/stop/parking/substation/park
- capacity: только для stop/parking

## sensors
- sensor_id: PK
- object_id: FK -> city_objects
- sensor_type: noise_db/pm25/traffic_intensity/temp_c
- unit: единицы измерения

## smart_meters
- meter_id: PK
- object_id: FK -> city_objects
- utility_type: electricity_kwh/water_m3/heating_gcal

## sensor_readings
- reading_id: PK
- sensor_id: FK -> sensors
- ts: YYYY-MM-DD HH:MM:SS (GMT+3)
- quality_flag: ok/missing/suspect
- anomaly_score: 0 для ok/missing, >0 для suspect

## meter_readings
- reading_id: PK
- meter_id: FK -> smart_meters
- is_peak: 1 если value >= 90-й перцентиль для данного meter

## municipal_events
- event_id: PK
- district_id: FK -> districts
- impact_radius_km: радиус влияния
- noise_increase_db, traffic_increase_percent: эффекты

## citizen_requests
- request_id: PK
- district_id: FK -> districts
- object_id: опционально
- category: тип обращения
- resolution_hours: время решения (если решено)

## public_transport_trips
- trip_id: PK
- stop_object_id: FK -> city_objects(object_type=stop)
- delay_minutes: задержка
"""

DOC_KPI_DEFINITIONS = """# CityGrid - KPI Definitions

## On-time share (транспорт)
Доля поездок с delay_minutes = 0 по маршруту за период.

## Avg delay (транспорт)
Средняя задержка по маршруту за период (minutes).

## Complaint rate (обращения)
Кол-во обращений на 10k населения района за период.

## Event impact (события)
Сравнение средних значений:
- traffic_intensity до события vs во время события (в зоне влияния)
- noise_db до события vs во время события (в зоне влияния)

## Air quality pressure
Часы, когда pm25 превышает порог (например 35 ug/m3) в районе.
"""

DOC_SENSOR_SPECS = """# CityGrid - Sensor Specs

## noise_db
Единицы: dB
Типичные значения: 30-90
Связи: зависит от traffic_intensity, повышается во время событий.

## traffic_intensity
Единицы: veh/h
Типичные значения: 20-500
Связи: пики 07-10 и 17-20, на выходных ниже, растет во время событий.

## pm25
Единицы: ug/m3
Типичные значения: 5-120
Связи: растет с traffic_intensity и industrial_coeff, возможны эпизоды смога 1-3 дня.

## temp_c
Единицы: C
Типичные значения: -30..35
Связи: влияет на heating_gcal и вероятность heating_issue при temp < 0.
"""

DOC_REPORT_TEMPLATE = """# CityGrid - Report Template

## 1. Период и масштаб
- Период: <start> .. <end>
- Масштаб: small/medium/large

## 2. Ключевые метрики
- Топ-районы по обращениям (30 дней)
- Пунктуальность транспорта по маршрутам
- Эффект событий: трафик и шум до/во время
- Связь pm25 и air_quality обращений

## 3. Аномалии и качество данных
- missing %, suspect %
- Примеры аномальных точек (suspect)

## 4. Выводы и рекомендации
- Где проблема (районы, категории)
- Что проверить (инфраструктура/сервис/план работ)

## 5. Ограничения
- Синтетические данные, упрощенные зависимости
- Не все факторы реального мира смоделированы
"""

DOC_INCIDENT_POLICY = """# CityGrid - Incident Policy (simplified)

## Severity
- Low: единичные обращения, без роста метрик
- Medium: всплеск обращений или метрик в 1 районе
- High: затронуто 2+ районов или длительность > 24h

## Response
- Triage: подтвердить по датчикам/счетчикам
- Identify scope: район, радиус, время
- Mitigation: назначить ремонт/патруль/уведомление
- Post-mortem: причина, профилактика, метрики контроля
"""


def ensure_workspace_docs(docs_dir: Path) -> None:
    ensure_dir(docs_dir)
    write_text_if_missing(docs_dir / "data_dictionary.md", DOC_DATA_DICTIONARY)
    write_text_if_missing(docs_dir / "kpi_definitions.md", DOC_KPI_DEFINITIONS)
    write_text_if_missing(docs_dir / "sensor_specs.md", DOC_SENSOR_SPECS)
    write_text_if_missing(docs_dir / "report_template.md", DOC_REPORT_TEMPLATE)
    write_text_if_missing(docs_dir / "incident_policy.md", DOC_INCIDENT_POLICY)


# ----------------------------
# Synthetic models (district-level)
# ----------------------------

DISTRICT_TYPES = ["residential", "commercial", "industrial", "mixed", "recreational", "educational"]
DENSITY_LEVELS = ["low", "medium", "high", "very_high"]
INCOME_LEVELS = ["low", "medium", "high"]

OBJECT_TYPES = ["building", "road_segment", "streetlight", "stop", "parking", "substation", "park"]
SENSOR_TYPES = ["noise_db", "pm25", "traffic_intensity", "temp_c"]
UTILITY_TYPES = ["electricity_kwh", "water_m3", "heating_gcal"]
EVENT_TYPES = ["concert", "construction", "accident", "protest", "festival", "sports_event"]
REQUEST_CATEGORIES = [
    "noise_complaint", "pothole", "broken_streetlight", "water_leak",
    "heating_issue", "parking_issue", "air_quality",
]
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
    return {
        "residential": 0.9,
        "commercial": 1.4,
        "industrial": 1.1,
        "mixed": 1.3,
        "recreational": 0.7,
        "educational": 0.8,
    }[t]


def object_type_probs(district_type: str) -> Dict[str, float]:
    # Грубая, но правдоподобная смесь
    if district_type == "residential":
        return {"building": 0.38, "road_segment": 0.22, "streetlight": 0.16, "stop": 0.08, "parking": 0.06, "substation": 0.04, "park": 0.06}
    if district_type == "commercial":
        return {"building": 0.26, "road_segment": 0.22, "streetlight": 0.14, "stop": 0.14, "parking": 0.14, "substation": 0.05, "park": 0.05}
    if district_type == "industrial":
        return {"building": 0.24, "road_segment": 0.26, "streetlight": 0.12, "stop": 0.06, "parking": 0.08, "substation": 0.16, "park": 0.08}
    if district_type == "mixed":
        return {"building": 0.30, "road_segment": 0.22, "streetlight": 0.14, "stop": 0.12, "parking": 0.10, "substation": 0.06, "park": 0.06}
    if district_type == "recreational":
        return {"building": 0.14, "road_segment": 0.18, "streetlight": 0.16, "stop": 0.08, "parking": 0.10, "substation": 0.04, "park": 0.30}
    # educational
    return {"building": 0.30, "road_segment": 0.20, "streetlight": 0.14, "stop": 0.10, "parking": 0.10, "substation": 0.06, "park": 0.10}


def daily_traffic_profile(hours: np.ndarray) -> np.ndarray:
    # Два пика + базовый фон. Используем scipy.stats.norm.pdf (как требование "scipy")
    h = hours.astype(float)
    peak1 = stats.norm.pdf(h, loc=8.5, scale=1.3)
    peak2 = stats.norm.pdf(h, loc=18.0, scale=1.5)
    midday = stats.norm.pdf(h, loc=13.0, scale=3.0)
    base = 0.45 + 5.2 * peak1 + 6.0 * peak2 + 1.3 * midday
    return base / base.mean()


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
    # heating - более ровный, но чуть выше утром и вечером
    m1 = stats.norm.pdf(h, loc=7.0, scale=2.8)
    m2 = stats.norm.pdf(h, loc=21.0, scale=3.0)
    base = 0.75 + 1.1 * m1 + 1.2 * m2
    return base / base.mean()


def ar1_noise(rng: np.random.Generator, n: int, phi: float, sigma: float) -> np.ndarray:
    e = rng.normal(0.0, sigma, size=n)
    x = np.empty(n, dtype=float)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


# ----------------------------
# Generation
# ----------------------------

def create_connection(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -200000;")  # ~200MB cache
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(INDEXES)
    conn.commit()


def export_csv(conn: sqlite3.Connection, csv_dir: Path, tables: List[str]) -> None:
    ensure_dir(csv_dir)
    for t in tables:
        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
        df.to_csv(csv_dir / f"{t}.csv", index=False, encoding="utf-8")


def log_line(log_path: Path, msg: str) -> None:
    ensure_dir(log_path.parent)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{now_str()}] {msg}\n")


def gen_districts(rng: np.random.Generator, bounds: CityBounds, n: int) -> pd.DataFrame:
    # Типы районов - с легким приоритетом residential/mixed
    type_probs = np.array([0.34, 0.14, 0.12, 0.22, 0.10, 0.08], dtype=float)
    type_probs = type_probs / type_probs.sum()

    rows = []
    for i in range(1, n + 1):
        t = rng.choice(DISTRICT_TYPES, p=type_probs)
        area = float(rng.uniform(6.0, 35.0))
        lat = float(rng.uniform(bounds.lat_min + 0.01, bounds.lat_max - 0.01))
        lon = float(rng.uniform(bounds.lon_min + 0.01, bounds.lon_max - 0.01))

        # population коррелирует с типом и площадью
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

        # income level - больше в commercial/mixed
        if t in ("commercial", "mixed"):
            income = rng.choice(INCOME_LEVELS, p=[0.18, 0.48, 0.34])
        elif t == "industrial":
            income = rng.choice(INCOME_LEVELS, p=[0.45, 0.43, 0.12])
        else:
            income = rng.choice(INCOME_LEVELS, p=[0.30, 0.55, 0.15])

        # industrial coeff
        ic = {
            "industrial": rng.uniform(0.55, 0.95),
            "mixed": rng.uniform(0.25, 0.65),
            "commercial": rng.uniform(0.10, 0.35),
            "residential": rng.uniform(0.05, 0.25),
            "recreational": rng.uniform(0.00, 0.15),
            "educational": rng.uniform(0.05, 0.20),
        }[t]
        ic = float(clamp(ic + rng.normal(0, 0.03), 0.0, 1.0))

        # geometry: простой квадрат вокруг центра, площадь ~ area_km2
        # Перевод км в градусы (приближенно)
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


def gen_city_objects(
    rng: np.random.Generator,
    bounds: CityBounds,
    districts: pd.DataFrame,
    n_objects: int,
    start_date: str,
) -> pd.DataFrame:
    # Распределение объектов по районам - по населению и площади
    weights = (districts["population"].to_numpy(dtype=float) * 0.7 + districts["area_km2"].to_numpy(dtype=float) * 3000.0)
    weights = weights / weights.sum()

    district_ids = districts["district_id"].to_numpy()
    chosen_districts = rng.choice(district_ids, size=n_objects, replace=True, p=weights)

    # Для генерации координат берем центр + шум, разный для плотности
    dens_sigma_km = {"low": 1.8, "medium": 1.3, "high": 0.9, "very_high": 0.65}

    # Предподсчеты по районам
    dmap = districts.set_index("district_id").to_dict(orient="index")

    # install_date: от start_date - 10 лет до start_date
    start_ts = pd.Timestamp(start_date + " 00:00:00")
    min_ts = start_ts - pd.Timedelta(days=365 * 10)

    obj_rows = []
    for oid in range(1, n_objects + 1):
        did = int(chosen_districts[oid - 1])
        info = dmap[did]
        probs = object_type_probs(info["type"])
        types = np.array(list(probs.keys()))
        p = np.array(list(probs.values()), dtype=float)
        p = p / p.sum()
        ot = str(rng.choice(types, p=p))

        # coords in bbox: center + gaussian noise (km -> degrees approx)
        sigma_km = dens_sigma_km[str(info["density"])]
        dx_km = float(rng.normal(0.0, sigma_km))
        dy_km = float(rng.normal(0.0, sigma_km))

        lat = float(info["center_lat"] + (dy_km / 111.0))
        lon = float(info["center_lon"] + (dx_km / (111.0 * math.cos(math.radians(info["center_lat"])) + 1e-9)))

        lat = float(clamp(lat, bounds.lat_min, bounds.lat_max))
        lon = float(clamp(lon, bounds.lon_min, bounds.lon_max))

        # status
        if info["type"] == "industrial":
            status = rng.choice(["active", "under_repair", "inactive"], p=[0.88, 0.09, 0.03])
        else:
            status = rng.choice(["active", "under_repair", "inactive"], p=[0.92, 0.06, 0.02])

        # install date
        inst = min_ts + pd.Timedelta(seconds=int(rng.integers(0, int((start_ts - min_ts).total_seconds()))))
        install_date = ts_to_str(inst)

        cap: Optional[int] = None
        if ot == "stop":
            cap = int(rng.integers(30, 240))
        elif ot == "parking":
            cap = int(rng.integers(50, 520))

        obj_rows.append({
            "object_id": oid,
            "district_id": did,
            "object_type": ot,
            "name": f"{ot}_{did}_{oid}",
            "lat": lat,
            "lon": lon,
            "install_date": install_date,
            "status": str(status),
            "capacity": cap,
        })

    return pd.DataFrame(obj_rows)


def gen_sensors(
    rng: np.random.Generator,
    objects_df: pd.DataFrame,
    n_sensors: int,
) -> pd.DataFrame:
    # Доли типов
    shares = {
        "traffic_intensity": 0.35,
        "noise_db": 0.30,
        "pm25": 0.20,
        "temp_c": 0.15,
    }
    # округление
    counts = {k: int(round(v * n_sensors)) for k, v in shares.items()}
    # поправка суммы
    diff = n_sensors - sum(counts.values())
    if diff != 0:
        counts["traffic_intensity"] += diff

    obj_by_type = {
        "road_segment": objects_df.loc[objects_df["object_type"] == "road_segment", "object_id"].to_numpy(),
        "stop": objects_df.loc[objects_df["object_type"] == "stop", "object_id"].to_numpy(),
        "parking": objects_df.loc[objects_df["object_type"] == "parking", "object_id"].to_numpy(),
        "streetlight": objects_df.loc[objects_df["object_type"] == "streetlight", "object_id"].to_numpy(),
        "park": objects_df.loc[objects_df["object_type"] == "park", "object_id"].to_numpy(),
        "substation": objects_df.loc[objects_df["object_type"] == "substation", "object_id"].to_numpy(),
        "building": objects_df.loc[objects_df["object_type"] == "building", "object_id"].to_numpy(),
    }

    def pick_from(pool: np.ndarray, size: int) -> np.ndarray:
        if pool.size == 0:
            # fallback to any object
            all_ids = objects_df["object_id"].to_numpy()
            return rng.choice(all_ids, size=size, replace=True)
        return rng.choice(pool, size=size, replace=True)

    rows = []
    sid = 1

    # traffic_intensity - road_segment/stop/parking
    n = counts["traffic_intensity"]
    pool = np.concatenate([obj_by_type["road_segment"], obj_by_type["stop"], obj_by_type["parking"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "traffic_intensity",
            "unit": "veh/h",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.94, 0.03, 0.02, 0.01])),
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.95, 0.02), 0.85, 0.99)),
        })
        sid += 1

    # noise_db - road_segment/streetlight/park/stop
    n = counts["noise_db"]
    pool = np.concatenate([obj_by_type["road_segment"], obj_by_type["streetlight"], obj_by_type["park"], obj_by_type["stop"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "noise_db",
            "unit": "dB",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.94, 0.03, 0.02, 0.01])),
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.93, 0.03), 0.80, 0.99)),
        })
        sid += 1

    # pm25 - park/substation/road_segment
    n = counts["pm25"]
    pool = np.concatenate([obj_by_type["park"], obj_by_type["substation"], obj_by_type["road_segment"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "pm25",
            "unit": "ug/m3",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.93, 0.04, 0.02, 0.01])),
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.90, 0.04), 0.75, 0.99)),
        })
        sid += 1

    # temp_c - park/substation/building
    n = counts["temp_c"]
    pool = np.concatenate([obj_by_type["park"], obj_by_type["substation"], obj_by_type["building"]])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "sensor_id": sid,
            "object_id": int(oid),
            "sensor_type": "temp_c",
            "unit": "C",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.95, 0.03, 0.01, 0.01])),
            "last_calibration": None,
            "accuracy": float(clamp(rng.normal(0.97, 0.01), 0.90, 0.995)),
        })
        sid += 1

    df = pd.DataFrame(rows)

    # last_calibration - для активных (примерно раз в 30-180 дней)
    calib_mask = df["is_active"].to_numpy() == 1
    n_active = int(calib_mask.sum())
    if n_active > 0:
        offsets = rng.integers(30, 180, size=n_active)
        base = pd.Timestamp(df_date_floor(pd.Timestamp.now()))
        calib_dates = [ts_to_str(base - pd.Timedelta(days=int(d))) for d in offsets]
        df.loc[calib_mask, "last_calibration"] = calib_dates

    return df


def df_date_floor(ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=ts.year, month=ts.month, day=ts.day)


def gen_meters(
    rng: np.random.Generator,
    objects_df: pd.DataFrame,
    n_meters: int,
) -> pd.DataFrame:
    # utility shares
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

    # electricity - building/substation
    n = counts["electricity_kwh"]
    pool = np.concatenate([obj_building, obj_substation])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "electricity_kwh",
            "unit": "kWh",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.96, 0.02, 0.01, 0.01])),
        })
        mid += 1

    # water - building/road
    n = counts["water_m3"]
    pool = np.concatenate([obj_building, obj_road])
    obj_ids = pick_from(pool, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "water_m3",
            "unit": "m3",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.96, 0.02, 0.01, 0.01])),
        })
        mid += 1

    # heating - building only
    n = counts["heating_gcal"]
    obj_ids = pick_from(obj_building, n)
    for oid in obj_ids:
        rows.append({
            "meter_id": mid,
            "object_id": int(oid),
            "utility_type": "heating_gcal",
            "unit": "Gcal",
            "is_active": int(rng.choice([1, 1, 1, 0], p=[0.95, 0.03, 0.01, 0.01])),
        })
        mid += 1

    return pd.DataFrame(rows)


def gen_events(
    rng: np.random.Generator,
    bounds: CityBounds,
    districts: pd.DataFrame,
    objects_df: pd.DataFrame,
    dt_idx: pd.DatetimeIndex,
    n_events: int,
) -> pd.DataFrame:
    # координаты вокруг центра района
    dmap = districts.set_index("district_id").to_dict(orient="index")
    district_ids = districts["district_id"].to_numpy()

    start_min = dt_idx[0]
    start_max = dt_idx[-1] - pd.Timedelta(hours=8)

    rows = []
    for eid in range(1, n_events + 1):
        did = int(rng.choice(district_ids))
        info = dmap[did]
        et = str(rng.choice(EVENT_TYPES, p=[0.16, 0.20, 0.16, 0.10, 0.20, 0.18]))

        # start in time range
        delta_sec = int((start_max - start_min).total_seconds())
        start_ts = start_min + pd.Timedelta(seconds=int(rng.integers(0, max(delta_sec, 1))))

        # duration
        if et in ("concert", "sports_event", "festival"):
            dur_h = int(rng.integers(3, 8))
        elif et == "protest":
            dur_h = int(rng.integers(2, 6))
        else:
            dur_h = int(rng.integers(4, 16))
        end_ts = start_ts + pd.Timedelta(hours=dur_h)

        # location
        dx_km = float(rng.normal(0.0, 0.9))
        dy_km = float(rng.normal(0.0, 0.9))
        lat = float(info["center_lat"] + (dy_km / 111.0))
        lon = float(info["center_lon"] + (dx_km / (111.0 * math.cos(math.radians(info["center_lat"])) + 1e-9)))
        lat = float(clamp(lat, bounds.lat_min, bounds.lat_max))
        lon = float(clamp(lon, bounds.lon_min, bounds.lon_max))

        # impact radius
        radius = float(clamp(rng.normal(0.85, 0.35), 0.25, 1.8))

        # effects
        if et in ("concert", "festival", "sports_event"):
            noise_inc = float(clamp(rng.normal(10.0, 3.0), 4.0, 18.0))
            traffic_inc = float(clamp(rng.normal(28.0, 10.0), 8.0, 65.0))
        elif et in ("construction", "accident"):
            noise_inc = float(clamp(rng.normal(7.0, 3.5), 2.0, 16.0))
            traffic_inc = float(clamp(rng.normal(22.0, 12.0), 5.0, 70.0))
        else:
            noise_inc = float(clamp(rng.normal(6.0, 2.5), 2.0, 14.0))
            traffic_inc = float(clamp(rng.normal(18.0, 10.0), 5.0, 55.0))

        # attendance
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
) -> Dict[int, Dict[str, np.ndarray]]:
    """
    Возвращает модели по районам (T-ряд):
    - temp_c_proxy
    - traffic_proxy
    - pm25_proxy
    - event_active (bool)
    - event_after_24h (bool)
    - event_construction_or_accident (bool)
    """
    T = len(dt_idx)
    hours = dt_idx.hour.to_numpy()
    dow = dt_idx.dayofweek.to_numpy()
    is_weekend = (dow >= 5).astype(float)

    # Глобальная температура (сезон + суточность + AR(1))
    day_of_year = dt_idx.dayofyear.to_numpy()
    seasonal = 6.0 + 14.5 * np.sin(2.0 * np.pi * (day_of_year / 365.25) - np.pi / 2.0)
    diurnal = 3.5 * np.sin(2.0 * np.pi * (hours / 24.0) - np.pi / 2.0)
    temp_global = seasonal + diurnal + ar1_noise(rng, T, phi=0.88, sigma=0.9) + rng.normal(0.0, 0.6, size=T)
    temp_global = np.clip(temp_global, -30.0, 35.0)

    traffic_shape = daily_traffic_profile(hours)
    weekend_factor = 1.0 - 0.28 * is_weekend  # ниже в выходные

    # event flags per district
    ev_by_d: Dict[int, List[Dict[str, Any]]] = {}
    for r in events_df.to_dict(orient="records"):
        did = int(r["district_id"])
        ev_by_d.setdefault(did, []).append(r)

    idx_map = {ts_to_str(ts): i for i, ts in enumerate(dt_idx)}

    models: Dict[int, Dict[str, np.ndarray]] = {}

    for row in districts.to_dict(orient="records"):
        did = int(row["district_id"])
        t = str(row["type"])
        dens = str(row["density"])
        ic = float(row["industrial_coeff"])

        temp_offset = float(rng.normal(0.0, 0.6))
        temp = temp_global + temp_offset

        base = 120.0 * density_mult(dens) * type_traffic_mult(t)
        traffic = base * traffic_shape * weekend_factor
        traffic = traffic * (1.0 + 0.08 * ar1_noise(rng, T, phi=0.80, sigma=0.25))
        traffic = traffic + rng.normal(0.0, 8.0, size=T)
        traffic = np.clip(traffic, 5.0, 900.0)

        # PM25 proxy: traffic + industrial + smog episodes
        pm = (8.0 + 28.0 * ic) + 0.055 * traffic + ar1_noise(rng, T, phi=0.75, sigma=1.2) + rng.normal(0.0, 1.2, size=T)

        # Smog episodes 1-3 дня, 1-2 эпизода на 90 дней
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

            # district-level boost for traffic during events
            traffic_mult = 1.0 + float(ev["traffic_increase_percent"]) / 100.0
            traffic[s_i:e_i] = traffic[s_i:e_i] * traffic_mult

            # district-level pm25 slight bump for construction/accident
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
    """
    Для каждого sensor_id список эффектов:
    (start_i, end_i, noise_add_db, traffic_mult, event_type)
    """
    T = len(dt_idx)
    # sensor -> object coords
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

    # Перевод времени в индексы
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

        # какие сенсоры попали в радиус
        d = haversine_km(s_lat[1:], s_lon[1:], ev_lat, ev_lon)  # size N
        affected = np.where(d <= radius)[0] + 1  # sensor_id
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
    """
    Возвращает:
    values (float),
    quality_flag_code (0 ok, 1 missing, 2 suspect),
    anomaly_score
    """
    did = int(object_row["district_id"])
    m = models[did]
    T = len(dt_idx)
    hours = dt_idx.hour.to_numpy()
    dow = dt_idx.dayofweek.to_numpy()
    is_weekend = (dow >= 5).astype(float)

    st = str(sensor_row["sensor_type"])
    dens = str(district_row["density"])
    dtype = str(district_row["type"])
    ic = float(district_row["industrial_coeff"])

    # object factor
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
        # event multipliers for local sensor
        for (s_i, e_i, _noise_add, traffic_mult, _et) in impacts:
            vals[s_i:e_i] = vals[s_i:e_i] * traffic_mult
    elif st == "noise_db":
        # базовый шум + зависимость от трафика + ночной режим
        night = ((hours <= 5) | (hours >= 23)).astype(float)
        night_floor = 28.0 + 2.0 * (dtype in ("commercial", "mixed"))
        base = 33.0 + 4.0 * density_mult(dens) + 2.0 * (dtype in ("commercial", "mixed"))
        vals = base + 0.065 * (traffic * obj_f) - 7.5 * night + night_floor * night
        vals = vals + ar1_noise(rng, T, phi=0.70, sigma=0.9) + rng.normal(0.0, 1.1, size=T)
        # event additive noise
        for (s_i, e_i, noise_add, _traffic_mult, _et) in impacts:
            vals[s_i:e_i] = vals[s_i:e_i] + noise_add
        vals = np.clip(vals, 20.0, 110.0)
    else:  # pm25
        pm = m["pm25_proxy"]
        vals = pm * (0.85 + 0.30 * obj_f) + rng.normal(0.0, 2.0, size=T)
        # construction/accident short spike (local) - additive
        for (s_i, e_i, _noise_add, _traffic_mult, et) in impacts:
            if et in ("construction", "accident"):
                vals[s_i:e_i] = vals[s_i:e_i] + float(rng.uniform(2.0, 10.0))
        vals = np.clip(vals, 1.0, 250.0)

    # quality flags init: ok
    q = np.zeros(T, dtype=np.int8)  # 0 ok

    # missing and suspect will be applied outside per-sensor policy
    anomaly = np.zeros(T, dtype=float)
    return vals.astype(float), q, anomaly


def apply_quality_policy(
    rng: np.random.Generator,
    vals: np.ndarray,
    q: np.ndarray,
    anomaly: np.ndarray,
    missing_window: Optional[Tuple[int, int]],
    spikes: Optional[List[int]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    T = vals.shape[0]

    # missing window
    if missing_window is not None:
        s_i, e_i = missing_window
        s_i = int(clamp(s_i, 0, T))
        e_i = int(clamp(e_i, 0, T))
        if e_i > s_i:
            q[s_i:e_i] = 1  # missing
            vals[s_i:e_i] = 0.0
            anomaly[s_i:e_i] = 0.0

    # spikes -> suspect
    if spikes:
        for idx in spikes:
            if 0 <= idx < T:
                q[idx] = 2  # suspect
                # spike magnitude: multiplicative for non-temp
                amp = float(rng.uniform(1.6, 3.2))
                vals[idx] = float(vals[idx] * amp + rng.normal(0.0, 1.5))

        # anomaly_score based on rolling median/mad 24h
        # missing для расчета делаем NaN, чтобы не ломать медиану
        v_for_calc = vals.astype(float).copy()
        v_for_calc[q == 1] = np.nan

        s = pd.Series(v_for_calc)
        med = s.rolling(window=24, min_periods=12, center=True).median()
        mad = (s - med).abs().rolling(window=24, min_periods=12, center=True).median()

        eps = 1e-6
        K = 6.0
        for idx in spikes:
            if 0 <= idx < T and q[idx] == 2:
                m = float(med.iloc[idx]) if pd.notna(med.iloc[idx]) else float(np.nanmedian(v_for_calc))
                d = float(mad.iloc[idx]) if pd.notna(mad.iloc[idx]) else float(np.nanmedian(np.abs(v_for_calc - m)))
                d = max(d, eps)
                score = abs(float(vals[idx]) - m) / (d + eps) / K
                score = float(min(1.0, max(0.05, score)))  # >0
                anomaly[idx] = score

    # ok/missing -> 0
    anomaly[q == 0] = 0.0
    anomaly[q == 1] = 0.0

    return vals, q, anomaly


def insert_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    cols = list(df.columns)
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, df.itertuples(index=False, name=None))


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

    # веса - население
    w = districts["population"].to_numpy(dtype=float)
    w = w / w.sum()

    dmap = districts.set_index("district_id").to_dict(orient="index")

    # объектные пулы по категориям
    obj_by_d_and_type: Dict[Tuple[int, str], np.ndarray] = {}
    for did in district_ids.tolist():
        did = int(did)
        for ot in OBJECT_TYPES:
            arr = objects_df.loc[(objects_df["district_id"] == did) & (objects_df["object_type"] == ot), "object_id"].to_numpy()
            obj_by_d_and_type[(did, ot)] = arr

    def pick_obj(did: int, category: str) -> Optional[int]:
        if category == "pothole":
            pool = obj_by_d_and_type[(did, "road_segment")]
        elif category == "broken_streetlight":
            pool = obj_by_d_and_type[(did, "streetlight")]
        elif category == "parking_issue":
            pool = np.concatenate([obj_by_d_and_type[(did, "parking")], obj_by_d_and_type[(did, "stop")]])
        elif category == "water_leak":
            pool = obj_by_d_and_type[(did, "road_segment")]
        elif category == "heating_issue":
            pool = obj_by_d_and_type[(did, "building")]
        elif category == "noise_complaint":
            pool = np.concatenate([obj_by_d_and_type[(did, "road_segment")], obj_by_d_and_type[(did, "stop")], obj_by_d_and_type[(did, "parking")]])
        else:  # air_quality
            pool = np.concatenate([obj_by_d_and_type[(did, "park")], obj_by_d_and_type[(did, "road_segment")]])
        if pool.size == 0:
            return None
        return int(rng.choice(pool))

    # time-of-day bias for request creation
    hours = dt_idx.hour.to_numpy()
    tod = (0.35 + 0.65 * (stats.norm.pdf(hours.astype(float), loc=12.0, scale=4.0) / stats.norm.pdf(12.0, loc=12.0, scale=4.0)))
    tod = tod / tod.sum()

    rows = []
    for rid in range(1, n_requests + 1):
        did = int(rng.choice(district_ids, p=w))
        info = dmap[did]
        m = models[did]

        # pick time index with day bias + some uniformity
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

        # category probabilities with causality
        p = np.array([0.16, 0.14, 0.12, 0.10, 0.10, 0.16, 0.22], dtype=float)
        # event -> noise_complaint + parking_issue
        if ev_after:
            p[0] *= 2.1
            p[5] *= 1.9
            if ev_ca:
                p[1] *= 1.6  # pothole
        # cold -> heating_issue
        if temp < 0.0:
            cold_mult = 1.0 + min(1.2, (-temp) / 10.0)
            # сильнее в low income и high density
            if info["income_level"] == "low":
                cold_mult *= 1.25
            if info["density"] in ("high", "very_high"):
                cold_mult *= 1.15
            p[4] *= cold_mult
        # high pm -> air_quality
        if pm > 35.0:
            p[6] *= 1.0 + min(2.0, (pm - 35.0) / 40.0)

        p = p / p.sum()
        category = str(rng.choice(REQUEST_CATEGORIES, p=p))

        obj_id = pick_obj(did, category)

        # priority
        pr = "low"
        if category in ("water_leak", "heating_issue"):
            pr = str(rng.choice(["medium", "high"], p=[0.7, 0.3])) if (temp < 0.0 or rng.random() < 0.35) else "medium"
        elif category in ("air_quality", "noise_complaint"):
            pr = str(rng.choice(["low", "medium", "high"], p=[0.55, 0.35, 0.10]))
        else:
            pr = str(rng.choice(["low", "medium", "high"], p=[0.65, 0.30, 0.05]))

        # status + resolution
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
    districts: pd.DataFrame,
    objects_df: pd.DataFrame,
    models: Dict[int, Dict[str, np.ndarray]],
    dt_idx: pd.DatetimeIndex,
    n_trips: int,
) -> pd.DataFrame:
    stops = objects_df.loc[objects_df["object_type"] == "stop", ["object_id", "district_id"]]
    if stops.empty:
        # fallback: create from any objects
        stops = objects_df.sample(min(50, len(objects_df)), random_state=1)[["object_id", "district_id"]]

    stop_ids = stops["object_id"].to_numpy()
    stop_did = stops["district_id"].to_numpy()

    routes = [f"R{str(i).zfill(2)}" for i in range(1, 21)]
    vehicles = [f"V{str(i).zfill(3)}" for i in range(1, 201)]

    T = len(dt_idx)

    # minute schedule (0..59) + random seconds fixed 0
    rows = []
    for tid in range(1, n_trips + 1):
        rno = str(rng.choice(routes))
        vid = str(rng.choice(vehicles))

        j = int(rng.integers(0, len(stop_ids)))
        soid = int(stop_ids[j])
        did = int(stop_did[j])

        # choose time index and random minute
        t_i = int(rng.integers(0, T))
        base_ts = dt_idx[t_i]
        minute = int(rng.integers(0, 60))
        scheduled = base_ts.replace(minute=minute, second=0)
        scheduled_ts = ts_to_str(scheduled)

        m = models[did]
        traffic = float(m["traffic_proxy"][t_i])
        temp = float(m["temp_c_proxy"][t_i])
        ev_ca = bool(m["event_ca"][t_i])

        # weather
        w = "clear"
        u = rng.random()
        if temp < -2.5 and u < 0.55:
            w = "snow"
        elif u < 0.12:
            w = "rain"
        elif u < 0.17:
            w = "fog"

        # delay model: traffic + weather + construction/accident tail
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

        # passengers: day-time + traffic correlated + event attendance proxy
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
        else:  # heating_gcal
            # больше когда холодно
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

    # quality policy: which sensors get missing windows and spikes
    n_sensors = len(sensors_df)
    missing_share = float(rng.uniform(quality_cfg.missing_sensor_share_min, quality_cfg.missing_sensor_share_max))
    suspect_share = float(rng.uniform(quality_cfg.suspect_sensor_share_min, quality_cfg.suspect_sensor_share_max))

    n_missing = int(round(n_sensors * missing_share))
    n_suspect = int(round(n_sensors * suspect_share))

    sensor_ids = sensors_df["sensor_id"].to_numpy()
    missing_sids = set(rng.choice(sensor_ids, size=max(n_missing, 1), replace=False).tolist()) if n_missing > 0 else set()
    remaining = np.array([sid for sid in sensor_ids if sid not in missing_sids], dtype=int)
    suspect_sids = set(rng.choice(remaining, size=max(n_suspect, 1), replace=False).tolist()) if n_suspect > 0 else set()

    # pre-maps
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

        missing_window = None
        spikes = None

        if sid in missing_sids:
            win_h = int(rng.integers(quality_cfg.missing_window_hours_min, quality_cfg.missing_window_hours_max + 1))
            start_i = int(rng.integers(0, max(T - win_h, 1)))
            missing_window = (start_i, start_i + win_h)

        if sid in suspect_sids:
            n_spikes = int(rng.integers(1, 6))
            spikes = rng.integers(0, T, size=n_spikes).tolist()

        vals, q, anomaly = apply_quality_policy(rng, vals, q, anomaly, missing_window, spikes)

        # write rows
        # q code -> string
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

    log_line(log_path, f"sensor_readings done (missing_share={missing_share:.4f}, suspect_share={suspect_share:.4f})")


def main() -> None:
    cfg_path = Path("configs/citygrid_generation.yaml")
    if len(os.sys.argv) >= 2:
        cfg_path = Path(os.sys.argv[1])

    cfg = load_config(cfg_path)

    scale = cfg.generation.scale
    if scale not in SCALE_DEFAULTS:
        raise ValueError(f"Unknown scale: {scale}")

    counts = dict(SCALE_DEFAULTS[scale])
    n_districts = int(counts["districts"])
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

    # reset log
    out_log.write_text("", encoding="utf-8")

    log_line(out_log, "START build_db")
    log_line(out_log, f"config={cfg_path}")
    log_line(out_log, f"seed={cfg.generation.seed}, start_date={cfg.generation.start_date}, days={cfg.generation.days}, step_hours={cfg.generation.step_hours}, scale={scale}")

    ensure_workspace_docs(out_docs)

    rng = np.random.default_rng(cfg.generation.seed)

    dt_idx = dt_range(cfg.generation.start_date, cfg.generation.days, cfg.generation.step_hours)

    conn = create_connection(out_db)
    try:
        init_db(conn)
        log_line(out_log, "DB initialized")

        # districts
        districts = gen_districts(rng, cfg.geography_bounds, n_districts)
        with conn:
            insert_df(conn, "districts", districts)
        log_line(out_log, f"districts inserted: {len(districts)}")

        # objects
        objects_df = gen_city_objects(rng, cfg.geography_bounds, districts, n_objects, cfg.generation.start_date)
        with conn:
            insert_df(conn, "city_objects", objects_df)
        log_line(out_log, f"city_objects inserted: {len(objects_df)}")

        # sensors
        sensors_df = gen_sensors(rng, objects_df, n_sensors)
        with conn:
            insert_df(conn, "sensors", sensors_df)
        log_line(out_log, f"sensors inserted: {len(sensors_df)}")

        # meters
        meters_df = gen_meters(rng, objects_df, n_meters)
        with conn:
            insert_df(conn, "smart_meters", meters_df)
        log_line(out_log, f"smart_meters inserted: {len(meters_df)}")

        # events
        events_df = gen_events(rng, cfg.geography_bounds, districts, objects_df, dt_idx, n_events)
        with conn:
            insert_df(conn, "municipal_events", events_df)
        log_line(out_log, f"municipal_events inserted: {len(events_df)}")

        # district models
        models = build_district_time_models(rng, districts, dt_idx, events_df)
        log_line(out_log, "district time models built")

        # sensor impacts by events (radius-based)
        sensor_impacts = build_sensor_impacts(sensors_df, objects_df, events_df, dt_idx)
        log_line(out_log, "sensor impacts built")

        # citizen requests
        requests_df = gen_citizen_requests(rng, districts, objects_df, models, dt_idx, n_requests)
        with conn:
            insert_df(conn, "citizen_requests", requests_df)
        log_line(out_log, f"citizen_requests inserted: {len(requests_df)}")

        # public transport trips
        trips_df = gen_public_transport_trips(rng, districts, objects_df, models, dt_idx, n_trips)
        with conn:
            insert_df(conn, "public_transport_trips", trips_df)
        log_line(out_log, f"public_transport_trips inserted: {len(trips_df)}")

        # readings (big) - insert in chunks
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

        # indexes after bulk inserts
        create_indexes(conn)
        log_line(out_log, "indexes created")

        # csv exports (без больших readings)
        export_csv(conn, out_csv, [
            "districts", "city_objects", "sensors", "smart_meters",
            "municipal_events", "citizen_requests", "public_transport_trips",
        ])
        log_line(out_log, "csv export done (no readings)")

        # lightweight meta file for reproducibility
        meta = {
            "seed": cfg.generation.seed,
            "start_date": cfg.generation.start_date,
            "days": cfg.generation.days,
            "step_hours": cfg.generation.step_hours,
            "scale": scale,
            "timezone": cfg.generation.timezone,
            "counts": {
                "districts": n_districts,
                "objects": n_objects,
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
