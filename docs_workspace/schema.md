# CityGrid Database Schema

## Tables Overview

The database contains 10 tables organized by domain:

| Table | Description | Approximate Size |
|-------|-------------|------------------|
| districts | Administrative areas | 5-20 rows |
| city_objects | Physical infrastructure | 500-6000 rows |
| road_network_nodes | Road graph nodes | 100-600 rows |
| sensors | IoT sensors | 750-9000 rows |
| smart_meters | Utility meters | 300-3600 rows |
| sensor_readings | Sensor time series | Millions (use time filter!) |
| meter_readings | Meter time series | Millions (use time filter!) |
| citizen_requests | Complaints/311 | 10k-160k rows |
| municipal_events | City events | 75-1200 rows |
| public_transport_trips | Transport data | 50k-800k rows |

---

## districts

Administrative districts of the city.

**Columns:**
- district_id (INTEGER, PK)
- name (TEXT) - e.g., "District 1"
- type (TEXT) - residential, commercial, industrial, mixed, recreational, educational
- population (INTEGER)
- area_km2 (REAL)
- density (TEXT) - low, medium, high, very_high
- income_level (TEXT) - low, medium, high
- industrial_coeff (REAL) - 0 to 1
- center_lat, center_lon (REAL) - district center coordinates
- geometry (TEXT, nullable) - WKT polygon

---

## city_objects

All physical infrastructure objects in one table. Use `object_type` to filter.

**Columns:**
- object_id (INTEGER, PK)
- district_id (INTEGER, FK → districts)
- object_type (TEXT) - building, road_segment, streetlight, stop, parking, substation, park
- name (TEXT)
- lat, lon (REAL) - object location
- install_date (TEXT)
- status (TEXT) - active, inactive, under_repair

**Additional columns for specific object_type:**

For `road_segment`:
- length_m (REAL)
- from_node_id, to_node_id (INTEGER, FK → road_network_nodes)
- road_type (TEXT) - highway, arterial, local, alley
- max_speed_kmh (INTEGER)
- lanes_count (INTEGER)
- direction (TEXT) - both, forward, backward
- condition (TEXT) - good, fair, poor
- start_lat, start_lon, end_lat, end_lon (REAL) - line coordinates

For `stop`, `parking`:
- capacity (INTEGER)

---

## road_network_nodes

Graph nodes for road network structure.

**Columns:**
- node_id (INTEGER, PK)
- lat, lon (REAL)
- type (TEXT) - intersection, junction, terminal
- is_connected_to_district_center (INTEGER) - 0 or 1

---

## sensors

IoT sensors attached to city objects.

**Columns:**
- sensor_id (INTEGER, PK)
- object_id (INTEGER, FK → city_objects)
- sensor_type (TEXT) - noise_db, pm25, traffic_intensity, temp_c
- unit (TEXT) - dB, ug/m3, veh/h, C
- is_active (INTEGER) - 0 or 1
- last_calibration (TEXT, nullable)
- accuracy (REAL, nullable)

**Note:** Sensors don't have direct coordinates. Join with city_objects for location.

---

## smart_meters

Utility meters in buildings.

**Columns:**
- meter_id (INTEGER, PK)
- object_id (INTEGER, FK → city_objects)
- utility_type (TEXT) - electricity_kwh, water_m3, heating_gcal
- unit (TEXT)
- is_active (INTEGER)

---

## sensor_readings

Time series from sensors. **Large table - always filter by time!**

**Columns:**
- reading_id (INTEGER, PK)
- sensor_id (INTEGER, FK → sensors)
- ts (TEXT) - timestamp, ISO format
- value (REAL)
- quality_flag (TEXT) - ok, missing, suspect
- anomaly_score (REAL) - 0 for normal, >0 for anomalies

---

## meter_readings

Time series from meters. **Large table - always filter by time!**

**Columns:**
- reading_id (INTEGER, PK)
- meter_id (INTEGER, FK → smart_meters)
- ts (TEXT) - timestamp
- value (REAL)
- is_peak (INTEGER) - 1 if peak consumption

---

## citizen_requests

Citizen complaints and service requests (311 system).

**Columns:**
- request_id (INTEGER, PK)
- district_id (INTEGER, FK → districts)
- object_id (INTEGER, FK → city_objects, nullable)
- category (TEXT) - noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality
- created_ts (TEXT)
- status (TEXT) - new, in_progress, resolved, rejected
- resolved_ts (TEXT, nullable)
- resolution_hours (REAL, nullable)
- priority (TEXT) - low, medium, high
- description (TEXT, nullable)

---

## municipal_events

City events that may affect traffic, noise, etc.

**Columns:**
- event_id (INTEGER, PK)
- district_id (INTEGER, FK → districts)
- name (TEXT)
- event_type (TEXT) - concert, construction, accident, protest, festival, sports_event
- start_ts, end_ts (TEXT)
- expected_attendance (INTEGER)
- lat, lon (REAL)
- impact_radius_km (REAL)
- noise_increase_db (REAL)
- traffic_increase_percent (REAL)

---

## public_transport_trips

Public transport trip records.

**Columns:**
- trip_id (INTEGER, PK)
- route_no (TEXT)
- vehicle_id (TEXT)
- stop_object_id (INTEGER, FK → city_objects where object_type='stop')
- scheduled_ts, actual_ts (TEXT)
- delay_minutes (INTEGER) - 0 means on time
- passenger_estimate (INTEGER)
- weather_condition (TEXT, nullable) - clear, rain, snow, fog
