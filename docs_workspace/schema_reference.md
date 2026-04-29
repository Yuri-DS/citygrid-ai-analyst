# CityGrid Database Schema Reference

## Overview
CityGrid database contains 10 tables with urban infrastructure data.

**To get actual row counts:** `SELECT COUNT(*) FROM <table_name>`
**To find data time period:** `SELECT MIN(ts), MAX(ts) FROM sensor_readings`

---

## 1. districts
Administrative districts of the city.

| Column | Type | Description |
|--------|------|-------------|
| district_id | INTEGER | Primary key |
| name | TEXT | District name (e.g., "District 1") |
| type | TEXT | Type: residential, commercial, industrial, mixed, recreational, educational |
| population | INTEGER | Number of residents |
| area_km2 | REAL | Area in square kilometers |
| density | TEXT | Density level: low, medium, high, very_high |
| income_level | TEXT | Income level: low, medium, high |
| industrial_coeff | REAL | Industrial coefficient [0..1] |
| center_lat | REAL | Latitude of district center |
| center_lon | REAL | Longitude of district center |
| geometry | TEXT | WKT polygon of district boundaries (nullable) |

**Example queries:**
```sql
-- All districts with population
SELECT name, population, area_km2, type FROM districts ORDER BY population DESC;

-- Calculate population density
SELECT name, population, area_km2, 
       ROUND(population * 1.0 / area_km2, 2) as population_density
FROM districts ORDER BY population_density DESC;

-- Districts by type
SELECT type, COUNT(*) as count, SUM(population) as total_population 
FROM districts GROUP BY type;
```

---

## 2. road_network_nodes
Nodes of the road network graph (intersections, junctions).

| Column | Type | Description |
|--------|------|-------------|
| node_id | INTEGER | Primary key |
| lat | REAL | Latitude |
| lon | REAL | Longitude |
| type | TEXT | Type: intersection, junction, terminal |
| is_connected_to_district_center | INTEGER | 1 if connected to district center, 0 otherwise |

**Example query:**
```sql
SELECT type, COUNT(*) as count FROM road_network_nodes GROUP BY type;
```

---

## 3. city_objects
City infrastructure objects (buildings, roads, streetlights, etc.).

| Column | Type | Description |
|--------|------|-------------|
| object_id | INTEGER | Primary key |
| district_id | INTEGER | FK to districts |
| object_type | TEXT | Type: building, road_segment, streetlight, stop, parking, substation, park |
| name | TEXT | Object name |
| lat | REAL | Latitude |
| lon | REAL | Longitude |
| install_date | TEXT | Installation date |
| status | TEXT | Status: active, inactive, under_repair |
| capacity | INTEGER | Capacity (for stop, parking) - nullable |
| length_m | REAL | Length in meters (for road_segment) - nullable |
| from_node_id | INTEGER | Start node FK (for road_segment) - nullable |
| to_node_id | INTEGER | End node FK (for road_segment) - nullable |
| road_type | TEXT | Road type: highway, arterial, local, alley (for road_segment) - nullable |
| max_speed_kmh | INTEGER | Speed limit (for road_segment) - nullable |
| lanes_count | INTEGER | Number of lanes (for road_segment) - nullable |
| direction | TEXT | Direction: both, forward, backward (for road_segment) - nullable |
| condition | TEXT | Condition: good, fair, poor (for road_segment) - nullable |
| start_lat | REAL | Start latitude (for road_segment) - nullable |
| start_lon | REAL | Start longitude (for road_segment) - nullable |
| end_lat | REAL | End latitude (for road_segment) - nullable |
| end_lon | REAL | End longitude (for road_segment) - nullable |

**Example queries:**
```sql
-- Objects by type
SELECT object_type, COUNT(*) as count 
FROM city_objects GROUP BY object_type ORDER BY count DESC;

-- Road segments by condition
SELECT condition, COUNT(*) as count 
FROM city_objects 
WHERE object_type = 'road_segment' 
GROUP BY condition;

-- Roads by type
SELECT road_type, COUNT(*) as count, ROUND(AVG(length_m), 2) as avg_length
FROM city_objects 
WHERE object_type = 'road_segment' 
GROUP BY road_type;
```

---

## 4. sensors
IoT sensors deployed across the city.

| Column | Type | Description |
|--------|------|-------------|
| sensor_id | INTEGER | Primary key |
| object_id | INTEGER | FK to city_objects (where sensor is installed) |
| sensor_type | TEXT | Type: noise_db, pm25, traffic_intensity, temp_c |
| unit | TEXT | Measurement unit (dB, ug/m3, veh/h, C) |
| is_active | INTEGER | 1 = active, 0 = inactive |
| last_calibration | TEXT | Last calibration date (nullable) |
| accuracy | REAL | Sensor accuracy (nullable) |

**Sensor types and units:**
- `noise_db` - Noise level in decibels (dB), typical: 30-90
- `pm25` - Air quality, PM2.5 particles (ug/m3), typical: 5-120
- `traffic_intensity` - Traffic flow (veh/h), typical: 20-500
- `temp_c` - Temperature in Celsius (C), typical: -30 to +35

**Example query:**
```sql
SELECT sensor_type, unit, COUNT(*) as count 
FROM sensors GROUP BY sensor_type, unit;
```

---

## 5. smart_meters
Smart meters for utilities monitoring.

| Column | Type | Description |
|--------|------|-------------|
| meter_id | INTEGER | Primary key |
| object_id | INTEGER | FK to city_objects (building where meter is installed) |
| utility_type | TEXT | Type: electricity_kwh, water_m3, heating_gcal |
| unit | TEXT | Measurement unit |
| is_active | INTEGER | 1 = active, 0 = inactive |

**Example query:**
```sql
SELECT utility_type, unit, COUNT(*) as count 
FROM smart_meters GROUP BY utility_type, unit;
```

---

## 6. sensor_readings ⚠️ LARGE TABLE
Time series of sensor measurements. **ALWAYS use time filter!**

| Column | Type | Description |
|--------|------|-------------|
| reading_id | INTEGER | Primary key |
| sensor_id | INTEGER | FK to sensors |
| ts | TEXT | Timestamp (ISO format: YYYY-MM-DD HH:MM:SS) |
| value | REAL | Measured value |
| quality_flag | TEXT | Quality: ok, missing, suspect |
| anomaly_score | REAL | Anomaly score (0 for ok/missing, >0 for suspect) |

**⚠️ REQUIRED: Always include time filter!**
```sql
SELECT * FROM sensor_readings 
WHERE sensor_id = 123 
  AND ts >= '2024-01-01' AND ts < '2024-01-02';
```

---

## 7. meter_readings ⚠️ LARGE TABLE
Time series of meter measurements. **ALWAYS use time filter!**

| Column | Type | Description |
|--------|------|-------------|
| reading_id | INTEGER | Primary key |
| meter_id | INTEGER | FK to smart_meters |
| ts | TEXT | Timestamp (ISO format) |
| value | REAL | Measured value |
| is_peak | INTEGER | 1 if peak consumption, 0 otherwise |

**⚠️ REQUIRED: Always include time filter!**

---

## 8. municipal_events
City events (concerts, construction, accidents, etc.).

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Primary key |
| district_id | INTEGER | FK to districts |
| name | TEXT | Event name |
| event_type | TEXT | Type: concert, construction, accident, protest, festival, sports_event |
| start_ts | TEXT | Start timestamp |
| end_ts | TEXT | End timestamp |
| expected_attendance | INTEGER | Expected number of attendees |
| lat | REAL | Event latitude |
| lon | REAL | Event longitude |
| impact_radius_km | REAL | Impact radius in kilometers |
| noise_increase_db | REAL | Expected noise increase |
| traffic_increase_percent | REAL | Expected traffic increase percentage |

**Example query:**
```sql
SELECT event_type, COUNT(*) as count, 
       ROUND(AVG(expected_attendance), 0) as avg_attendance
FROM municipal_events 
GROUP BY event_type 
ORDER BY count DESC;
```

---

## 9. citizen_requests
Citizen complaints and service requests (311 system).

| Column | Type | Description |
|--------|------|-------------|
| request_id | INTEGER | Primary key |
| district_id | INTEGER | FK to districts |
| object_id | INTEGER | FK to city_objects (related object) - nullable |
| category | TEXT | Category: noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality |
| created_ts | TEXT | Creation timestamp |
| status | TEXT | Status: new, in_progress, resolved, rejected |
| resolved_ts | TEXT | Resolution timestamp (nullable) |
| resolution_hours | REAL | Hours to resolve (nullable) |
| priority | TEXT | Priority: low, medium, high |
| description | TEXT | Request description (nullable) |

**Example queries:**
```sql
-- Requests by category
SELECT category, COUNT(*) as count 
FROM citizen_requests GROUP BY category ORDER BY count DESC;

-- Requests by status and priority
SELECT status, priority, COUNT(*) as count 
FROM citizen_requests 
GROUP BY status, priority 
ORDER BY status, count DESC;

-- Average resolution time by category
SELECT category, 
       ROUND(AVG(resolution_hours), 2) as avg_hours,
       COUNT(*) as resolved_count
FROM citizen_requests 
WHERE status = 'resolved' AND resolution_hours IS NOT NULL
GROUP BY category 
ORDER BY avg_hours DESC;
```

---

## 10. public_transport_trips
Public transport trip records.

| Column | Type | Description |
|--------|------|-------------|
| trip_id | INTEGER | Primary key |
| route_no | TEXT | Route number |
| vehicle_id | TEXT | Vehicle identifier |
| stop_object_id | INTEGER | FK to city_objects (stop) |
| scheduled_ts | TEXT | Scheduled arrival time |
| actual_ts | TEXT | Actual arrival time |
| delay_minutes | INTEGER | Delay in minutes (0 = on time) |
| passenger_estimate | INTEGER | Estimated passengers |
| weather_condition | TEXT | Weather: clear, rain, snow, fog (nullable) |

**Example queries:**
```sql
-- Average delay by route
SELECT route_no, 
       ROUND(AVG(delay_minutes), 2) as avg_delay,
       COUNT(*) as trip_count
FROM public_transport_trips 
GROUP BY route_no 
ORDER BY avg_delay DESC LIMIT 10;

-- Delays by weather
SELECT weather_condition, 
       ROUND(AVG(delay_minutes), 2) as avg_delay,
       COUNT(*) as trip_count
FROM public_transport_trips 
GROUP BY weather_condition 
ORDER BY avg_delay DESC;
```

---

## Common Calculations

**Population density (calculated):**
```sql
SELECT name, population, area_km2, 
       ROUND(population * 1.0 / area_km2, 2) as population_density
FROM districts;
```

**Join sensors with districts:**
```sql
SELECT d.name, s.sensor_type, COUNT(*) as sensor_count
FROM sensors s
JOIN city_objects co ON s.object_id = co.object_id
JOIN districts d ON co.district_id = d.district_id
GROUP BY d.name, s.sensor_type;
```

**Requests per district with population:**
```sql
SELECT d.name, d.population, COUNT(cr.request_id) as requests,
       ROUND(COUNT(cr.request_id) * 10000.0 / d.population, 2) as requests_per_10k
FROM districts d
LEFT JOIN citizen_requests cr ON d.district_id = cr.district_id
GROUP BY d.district_id
ORDER BY requests_per_10k DESC;
```