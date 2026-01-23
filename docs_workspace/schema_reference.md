# CityGrid Database Schema Reference

## Overview
CityGrid database contains 10 tables with urban infrastructure data.
Total period: depends on generation scale (30 days to 2 years).

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
| density | TEXT | Density level: low, medium, high |
| income_level | TEXT | Income level: low, medium, high |
| industrial_coeff | REAL | Industrial coefficient [0..1] |
| center_lat | REAL | Latitude of district center |
| center_lon | REAL | Longitude of district center |
| geometry | TEXT | WKT polygon of district boundaries |

**Row count:** ~10 districts

**Example query:**
```sql
SELECT name, population, type FROM districts ORDER BY population DESC;
```

---

## 2. road_network_nodes
Nodes of the road network graph (intersections, junctions).

| Column | Type | Description |
|--------|------|-------------|
| node_id | INTEGER | Primary key |
| node_type | TEXT | Type: intersection, junction, terminal |
| lat | REAL | Latitude |
| lon | REAL | Longitude |
| district_id | INTEGER | FK to districts |

**Row count:** ~250 nodes

---

## 3. city_objects
City infrastructure objects (buildings, roads, streetlights, etc.).

| Column | Type | Description |
|--------|------|-------------|
| object_id | INTEGER | Primary key |
| object_type | TEXT | Type: building, road_segment, streetlight, stop, parking, substation, park |
| name | TEXT | Object name |
| district_id | INTEGER | FK to districts |
| lat | REAL | Latitude |
| lon | REAL | Longitude |
| status | TEXT | Status: active, inactive, under_repair |
| capacity | INTEGER | Capacity (for stop, parking) |
| length_m | REAL | Length in meters (for road_segment) |
| from_node_id | INTEGER | Start node (for road_segment) |
| to_node_id | INTEGER | End node (for road_segment) |
| road_type | TEXT | Road type: highway, primary, secondary, tertiary, residential (for road_segment) |
| max_speed_kmh | INTEGER | Speed limit (for road_segment) |
| lanes_count | INTEGER | Number of lanes (for road_segment) |
| direction | TEXT | Direction: oneway, twoway (for road_segment) |
| condition | TEXT | Condition: good, fair, poor (for road_segment) |
| start_lat | REAL | Start latitude (for road_segment) |
| start_lon | REAL | Start longitude (for road_segment) |
| end_lat | REAL | End latitude (for road_segment) |
| end_lon | REAL | End longitude (for road_segment) |

**Row count:** ~2000 objects

**Example query - roads by condition:**
```sql
SELECT condition, COUNT(*) as count 
FROM city_objects 
WHERE object_type = 'road_segment' 
GROUP BY condition;
```

---

## 4. sensors
IoT sensors deployed across the city.

| Column | Type | Description |
|--------|------|-------------|
| sensor_id | INTEGER | Primary key |
| sensor_type | TEXT | Type: noise_db, pm25, traffic_intensity, temp_c |
| object_id | INTEGER | FK to city_objects (where sensor is installed) |
| install_date | TEXT | Installation date |
| is_active | INTEGER | 1 = active, 0 = inactive |

**Row count:** ~3000 sensors

**Sensor types:**
- `noise_db` - Noise level in decibels (30-90 dB typical)
- `pm25` - Air quality, PM2.5 particles (5-120 μg/m³ typical)
- `traffic_intensity` - Traffic flow (20-500 vehicles/hour typical)
- `temp_c` - Temperature in Celsius (-30 to +35°C typical)

**Example query:**
```sql
SELECT sensor_type, COUNT(*) as count FROM sensors GROUP BY sensor_type;
```

---

## 5. smart_meters
Smart meters for utilities monitoring.

| Column | Type | Description |
|--------|------|-------------|
| meter_id | INTEGER | Primary key |
| meter_type | TEXT | Type: electricity_kwh, water_m3, heating_gcal |
| object_id | INTEGER | FK to city_objects (building where meter is installed) |
| install_date | TEXT | Installation date |
| is_active | INTEGER | 1 = active, 0 = inactive |

**Row count:** ~1200 meters

---

## 6. sensor_readings ⚠️ LARGE TABLE
Time series of sensor measurements. **ALWAYS use time filter!**

| Column | Type | Description |
|--------|------|-------------|
| reading_id | INTEGER | Primary key |
| sensor_id | INTEGER | FK to sensors |
| ts | TEXT | Timestamp (ISO format) |
| value | REAL | Measured value |
| quality_flag | TEXT | Quality: ok, missing, suspect |
| anomaly_score | REAL | Anomaly score (0 for ok/missing, >0 for suspect) |

**Row count:** ~63 million (for 2-year period)

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
| is_peak | INTEGER | 1 if value >= 90th percentile |

**Row count:** ~21 million (for 2-year period)

**⚠️ REQUIRED: Always include time filter!**

---

## 8. municipal_events
City events (concerts, construction, accidents, etc.).

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Primary key |
| event_type | TEXT | Type: concert, construction, accident, protest, festival, sports_event |
| name | TEXT | Event name |
| district_id | INTEGER | FK to districts |
| start_ts | TEXT | Start timestamp |
| end_ts | TEXT | End timestamp |
| expected_attendance | INTEGER | Expected number of attendees |
| impact_radius_km | REAL | Impact radius in kilometers |
| noise_increase_db | REAL | Expected noise increase |
| traffic_increase_percent | REAL | Expected traffic increase percentage |

**Row count:** ~300 events

**Example query:**
```sql
SELECT event_type, COUNT(*) as count 
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
| category | TEXT | Category: noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality |
| district_id | INTEGER | FK to districts |
| created_ts | TEXT | Creation timestamp |
| status | TEXT | Status: new, in_progress, resolved, rejected |
| resolution_hours | REAL | Hours to resolve (NULL if not resolved) |
| description | TEXT | Request description |
| lat | REAL | Latitude |
| lon | REAL | Longitude |

**Row count:** ~40,000 requests

**Example query - requests by category and status:**
```sql
SELECT category, status, COUNT(*) as count 
FROM citizen_requests 
GROUP BY category, status 
ORDER BY count DESC;
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
| delay_minutes | REAL | Delay in minutes (0 = on time) |
| passenger_estimate | INTEGER | Estimated passengers |
| weather_condition | TEXT | Weather: clear, rain, snow, fog |

**Row count:** ~200,000 trips

**Example query - average delay by route:**
```sql
SELECT route_no, AVG(delay_minutes) as avg_delay 
FROM public_transport_trips 
GROUP BY route_no 
ORDER BY avg_delay DESC 
LIMIT 10;
```

---

## Common Calculations

**Population density (calculated):**
```sql
SELECT name, population, area_km2, 
       ROUND(population / area_km2, 2) as population_density
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
