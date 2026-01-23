# CityGrid SQL Examples

## Basic Queries

### Districts

```sql
-- All districts with population
SELECT name, type, population, area_km2 FROM districts ORDER BY population DESC;

-- Districts by type
SELECT type, COUNT(*) as count, SUM(population) as total_population 
FROM districts GROUP BY type;

-- Calculate population density
SELECT name, population, area_km2, 
       ROUND(population * 1.0 / area_km2, 2) as density_per_km2
FROM districts ORDER BY density_per_km2 DESC;
```

### Sensors

```sql
-- Sensors by type
SELECT sensor_type, COUNT(*) as count FROM sensors GROUP BY sensor_type;

-- Active sensors only
SELECT sensor_type, COUNT(*) as count 
FROM sensors WHERE is_active = 1 GROUP BY sensor_type;

-- Sensors per district
SELECT d.name, s.sensor_type, COUNT(*) as sensor_count
FROM sensors s
JOIN city_objects co ON s.object_id = co.object_id
JOIN districts d ON co.district_id = d.district_id
GROUP BY d.name, s.sensor_type
ORDER BY d.name, sensor_count DESC;
```

### City Objects

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
SELECT road_type, COUNT(*) as count, AVG(length_m) as avg_length
FROM city_objects 
WHERE object_type = 'road_segment' 
GROUP BY road_type;
```

### Citizen Requests

```sql
-- Requests by category
SELECT category, COUNT(*) as count 
FROM citizen_requests GROUP BY category ORDER BY count DESC;

-- Requests by status
SELECT status, COUNT(*) as count 
FROM citizen_requests GROUP BY status;

-- Requests by category and status
SELECT category, status, COUNT(*) as count 
FROM citizen_requests 
GROUP BY category, status 
ORDER BY category, count DESC;

-- Average resolution time by category
SELECT category, 
       ROUND(AVG(resolution_hours), 2) as avg_hours,
       COUNT(*) as resolved_count
FROM citizen_requests 
WHERE status = 'resolved' AND resolution_hours IS NOT NULL
GROUP BY category 
ORDER BY avg_hours DESC;

-- Requests per district
SELECT d.name, COUNT(*) as request_count
FROM citizen_requests cr
JOIN districts d ON cr.district_id = d.district_id
GROUP BY d.name
ORDER BY request_count DESC;
```

### Municipal Events

```sql
-- Events by type
SELECT event_type, COUNT(*) as count 
FROM municipal_events GROUP BY event_type ORDER BY count DESC;

-- Events with highest expected impact
SELECT name, event_type, expected_attendance, 
       noise_increase_db, traffic_increase_percent
FROM municipal_events 
ORDER BY expected_attendance DESC LIMIT 10;

-- Events per district
SELECT d.name, COUNT(*) as event_count
FROM municipal_events me
JOIN districts d ON me.district_id = d.district_id
GROUP BY d.name
ORDER BY event_count DESC;
```

### Public Transport

```sql
-- Average delay by route
SELECT route_no, 
       ROUND(AVG(delay_minutes), 2) as avg_delay,
       COUNT(*) as trip_count
FROM public_transport_trips 
GROUP BY route_no 
ORDER BY avg_delay DESC LIMIT 10;

-- On-time performance (delay = 0)
SELECT route_no,
       COUNT(*) as total_trips,
       SUM(CASE WHEN delay_minutes = 0 THEN 1 ELSE 0 END) as on_time,
       ROUND(100.0 * SUM(CASE WHEN delay_minutes = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as on_time_percent
FROM public_transport_trips
GROUP BY route_no
ORDER BY on_time_percent DESC;

-- Delays by weather
SELECT weather_condition, 
       ROUND(AVG(delay_minutes), 2) as avg_delay,
       COUNT(*) as trip_count
FROM public_transport_trips 
GROUP BY weather_condition 
ORDER BY avg_delay DESC;
```

### Smart Meters

```sql
-- Meters by type
SELECT meter_type, COUNT(*) as count 
FROM smart_meters GROUP BY meter_type;

-- Active meters only
SELECT meter_type, COUNT(*) as count 
FROM smart_meters WHERE is_active = 1 GROUP BY meter_type;
```

## Time-Series Queries (⚠️ ALWAYS use time filter!)

### Sensor Readings

```sql
-- Daily average noise for a sensor (MUST have time filter)
SELECT DATE(ts) as date, ROUND(AVG(value), 2) as avg_noise
FROM sensor_readings
WHERE sensor_id = 1 
  AND ts >= '2024-01-01' AND ts < '2024-02-01'
GROUP BY DATE(ts)
ORDER BY date;

-- Hourly pattern (one day)
SELECT strftime('%H', ts) as hour, ROUND(AVG(value), 2) as avg_value
FROM sensor_readings sr
JOIN sensors s ON sr.sensor_id = s.sensor_id
WHERE s.sensor_type = 'traffic_intensity'
  AND ts >= '2024-01-15' AND ts < '2024-01-16'
GROUP BY hour
ORDER BY hour;

-- Quality flag distribution
SELECT quality_flag, COUNT(*) as count
FROM sensor_readings
WHERE ts >= '2024-01-01' AND ts < '2024-01-08'
GROUP BY quality_flag;
```

### Meter Readings

```sql
-- Daily consumption (MUST have time filter)
SELECT DATE(ts) as date, SUM(value) as total_consumption
FROM meter_readings mr
JOIN smart_meters sm ON mr.meter_id = sm.meter_id
WHERE sm.meter_type = 'electricity_kwh'
  AND ts >= '2024-01-01' AND ts < '2024-02-01'
GROUP BY DATE(ts)
ORDER BY date;

-- Peak vs non-peak consumption
SELECT is_peak, COUNT(*) as readings, ROUND(AVG(value), 2) as avg_value
FROM meter_readings
WHERE ts >= '2024-01-01' AND ts < '2024-01-08'
GROUP BY is_peak;
```

## Complex Joins

```sql
-- Citizen requests near events (spatial proximity concept)
SELECT me.name as event_name, me.event_type,
       cr.category, COUNT(*) as request_count
FROM municipal_events me
JOIN citizen_requests cr ON cr.district_id = me.district_id
  AND cr.created_ts >= me.start_ts 
  AND cr.created_ts <= me.end_ts
GROUP BY me.event_id, cr.category
HAVING request_count > 5
ORDER BY request_count DESC;

-- Districts with most issues (requests + poor roads)
SELECT d.name,
       COUNT(DISTINCT cr.request_id) as request_count,
       COUNT(DISTINCT CASE WHEN co.condition = 'poor' THEN co.object_id END) as poor_roads
FROM districts d
LEFT JOIN citizen_requests cr ON cr.district_id = d.district_id
LEFT JOIN city_objects co ON co.district_id = d.district_id 
  AND co.object_type = 'road_segment'
GROUP BY d.district_id
ORDER BY request_count DESC;
```
