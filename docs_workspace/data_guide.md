# CityGrid Data Guide

## Disambiguation: match concept to table

Similar wording can mean different concepts. Use the **concept** (what the user cares about) to pick the right table, not just keywords.

| Concept | Table(s) | Key filter / columns | Do not use |
|---------|----------|----------------------|------------|
| Road surface condition (pavement state: good, fair, poor) | city_objects | object_type = 'road_segment', condition | public_transport_trips |
| Trip delays, routes, passenger counts, weather during trips | public_transport_trips | delay_minutes, stop_object_id, scheduled_ts, weather_condition | city_objects.condition (that is pavement, not trips) |
| Complaints or requests by category (noise, pothole, etc.) | citizen_requests | category, district_id, status, priority | sensors, meter_readings |
| Sensor measurements over time (noise, PM2.5, traffic, temp) | sensor_readings + sensors | sensor_id, ts, value, sensor_type | citizen_requests (that is complaints) |
| Utility consumption (electricity, water, heating) | meter_readings + smart_meters | meter_id, ts, value, utility_type | sensor_readings |
| Physical objects on a map (buildings, roads, stops, parks) | city_objects | object_type, lat/lon or start_lat/lon, end_lat/lon | Use object_type to filter; roads = road_segment |

**Aggregation by district:** For any table that has district_id, join districts for name and center_lat, center_lon (for maps). For city_objects, always filter by object_type when the question is about one kind of object (e.g. roads → object_type = 'road_segment').

---

## Working with Different Data Types

### Categorical Data
Columns with predefined set of values.

**districts.type:** residential, commercial, industrial, mixed, recreational, educational

**city_objects.object_type:** building, road_segment, streetlight, stop, parking, substation, park

**city_objects.status:** active, inactive, under_repair

**city_objects.condition (road_segment only):** good, fair, poor

**city_objects.road_type (road_segment only):** highway, arterial, local, alley

**sensors.sensor_type:** noise_db, pm25, traffic_intensity, temp_c

**smart_meters.utility_type:** electricity_kwh, water_m3, heating_gcal

**citizen_requests.category:** noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality

**citizen_requests.status:** new, in_progress, resolved, rejected

**citizen_requests.priority:** low, medium, high

**municipal_events.event_type:** concert, construction, accident, protest, festival, sports_event

**sensor_readings.quality_flag:** ok, missing, suspect

**public_transport_trips.weather_condition:** clear, rain, snow, fog

---

## Numeric Data

**Population & Area:**
- districts.population - number of residents
- districts.area_km2 - area in square kilometers

**Measurements:**
- sensor_readings.value - depends on sensor_type
- meter_readings.value - depends on utility_type
- city_objects.length_m - road length
- city_objects.capacity - for stops and parking

**Time & Duration:**
- citizen_requests.resolution_hours
- public_transport_trips.delay_minutes

**Coefficients & Percentages:**
- districts.industrial_coeff (0 to 1)
- municipal_events.traffic_increase_percent

---

## Geographic Data

**Point coordinates:**
- Most tables have lat, lon columns

**District centers:**
- districts.center_lat, districts.center_lon

**Line coordinates (for roads):**
- city_objects.start_lat, start_lon, end_lat, end_lon (when object_type='road_segment')

**Boundaries:**
- districts.geometry - WKT polygon (may be null)

---

## Time Series Data

**Timestamps** are stored as TEXT in ISO format: 'YYYY-MM-DD HH:MM:SS'

**Large time series tables** (filter by time!):
- sensor_readings.ts
- meter_readings.ts

**Event timestamps:**
- municipal_events.start_ts, end_ts
- citizen_requests.created_ts, resolved_ts
- public_transport_trips.scheduled_ts, actual_ts

---

## Data Quality

**sensor_readings.quality_flag:**
- ok - normal reading
- missing - data gap
- suspect - potential anomaly

**sensor_readings.anomaly_score:**
- 0 for ok and missing
- >0 indicates anomaly severity

---

## Aggregation Patterns

**Counting by category:**
```
SELECT <category_column>, COUNT(*) as count
FROM <table>
GROUP BY <category_column>
```

**Aggregating by district:**
```
SELECT d.name, <aggregation>
FROM <table> t
JOIN districts d ON t.district_id = d.district_id
GROUP BY d.district_id
```

**For tables without direct district_id (like sensors):**
```
SELECT d.name, <aggregation>
FROM sensors s
JOIN city_objects co ON s.object_id = co.object_id
JOIN districts d ON co.district_id = d.district_id
GROUP BY d.district_id
```

---

## Performance Tips

1. **Time filter for large tables:**
   sensor_readings and meter_readings have millions of rows.
   Always include: `WHERE ts >= '...' AND ts < '...'`

2. **LIMIT for exploration:**
   When exploring data structure, use LIMIT to avoid large result sets.

3. **LIMIT for map or chart:**
   For visualization (map or chart), use execute_sql with a LIMIT that matches the table size (see schema for row counts). Do not use get_table_sample for visualization — it returns only a small sample. Use a sufficient LIMIT or omit LIMIT so the system default applies.

4. **Specific object_type:**
   city_objects is large. Filter by object_type when possible.
