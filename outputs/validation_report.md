# CityGrid - Validation Report

- DB: `D:\CityGrid AI Analyst\data\citygrid.db`
- Generated with config: `D:\CityGrid AI Analyst\configs\citygrid_generation.yaml`
- Scale: `small`
- Period: 45 days

## 1. Data Integrity
### Foreign Key Violations
| Metric | Value |
|---|---|
| foreign_key_violations | 0 |

✅ All foreign keys valid

### Geographic Boundaries
| Metric | Value |
|---|---|
| objects_out_of_bbox | 0 |
| events_out_of_bbox | 0 |
| nodes_out_of_bbox | 0 |
| road_segments_out_of_bbox | 0 |

✅ All coordinates within bbox

## 2. Row Counts
| Table | Rows |
|---|---|
| districts | 5 |
| road_network_nodes | 100 |
| city_objects | 500 |
| sensors | 750 |
| smart_meters | 300 |
| municipal_events | 75 |
| citizen_requests | 10,000 |
| public_transport_trips | 50,000 |
| sensor_readings | 810,000 |
| meter_readings | 324,000 |

### Road Segments Breakdown
| object_type   |   cnt |
|:--------------|------:|
| road_segment  |   150 |
| building      |   112 |
| streetlight   |    73 |
| stop          |    59 |
| parking       |    47 |
| park          |    34 |
| substation    |    25 |

Road segments: 150 (30.0% of all objects)

## 3. Road Network Validation
### Node Types Distribution
| type         |   cnt |
|:-------------|------:|
| intersection |    95 |
| junction     |     5 |

| Metric | Value |
|---|---|
| total_nodes | 100 |
| district_center_nodes | 5 |

### Road Type Distribution
| road_type   |   cnt |   avg_length_m |   avg_speed |   avg_lanes |
|:------------|------:|---------------:|------------:|------------:|
| arterial    |    99 |       1100.45  |     69.7576 |     1.9899  |
| highway     |    32 |       9153.27  |     99.5    |     2.9375  |
| local       |    19 |        304.451 |     43.1053 |     1.57895 |

### Road Condition Distribution
| condition   |   cnt |   pct |
|:------------|------:|------:|
| good        |    88 | 58.67 |
| fair        |    45 | 30    |
| poor        |    17 | 11.33 |

### Road Direction Distribution
| direction   |   cnt |
|:------------|------:|
| backward    |     8 |
| both        |   137 |
| forward     |     5 |

### Network Connectivity
| Metric | Value |
|---|---|
| orphan_nodes (not connected) | 2 |
| road_segments_with_null_from_node | 0 |
| road_segments_with_null_to_node | 0 |

⚠️ **WARNING**: Network has disconnected components!

## 4. Data Quality
### Quality Flags & Anomaly Scores
| Metric | Value |
|---|---|
| sensor_readings_total | 810,000 |
| ok_count | 754,584 |
| missing_count | 43,179 |
| suspect_count | 12,237 |
| ok_share | 0.9316 |
| missing_share | 0.0533 |
| suspect_share | 0.0151 |
| avg_suspect_anomaly_score | 0.7259 |
| max_suspect_anomaly_score | 1.0000 |

### Quality Rule Violations
| Metric | Value |
|---|---|
| anomaly_score_nonzero_for_ok_or_missing | 0 |
| anomaly_score_nonpositive_for_suspect | 0 |

✅ All quality rules respected

### Missing Data by Sensor Type
| sensor_type       |   missing_cnt |   total_cnt |   missing_pct |
|:------------------|--------------:|------------:|--------------:|
| noise_db          |         13360 |      243000 |          5.5  |
| pm25              |          8599 |      162000 |          5.31 |
| temp_c            |          5682 |      120960 |          4.7  |
| traffic_intensity |         15538 |      284040 |          5.47 |

## 5. Causality Validation
### A: Events → Traffic & Noise Increase
| Metric | Value |
|---|---|
| sample_events_analyzed | 20 |
| avg_delta_traffic (during - before) | 35.778 veh/h |
| avg_delta_noise (during - before) | 2.520 dB |
| pct_events_with_traffic_increase | 65.0% |
| pct_events_with_noise_increase | 60.0% |

✅ Events clearly increase traffic and noise

### B: After Events → Increased Complaints
| Metric | Value |
|---|---|
| complaints_24h_after_events | 1440 |
| complaints_24h_before_events | 1011 |
| increase_pct | 42.4% |

✅ Complaints increase after events (20%+ increase)

### C: Cold Temperature → Heating Issues
| Metric | Value |
|---|---|
| heating_issues_on_cold_days (<0°C) | 1456 |
| heating_issues_on_warm_days (≥15°C) | 0 |
| cold_days_count | 45 |
| warm_days_count | 0 |
| heating_issues_per_cold_day | 32.36 |
| heating_issues_per_warm_day | 0.00 |

✅ Heating issues strongly correlated with cold weather

### D: High PM2.5 → Air Quality Complaints
| Metric | Value |
|---|---|
| hours_with_pm25_>35 | 1090 |
| hours_with_pm25_≤35 | 4310 |
| air_quality_complaints_when_high_pm25 | 771 |
| air_quality_complaints_when_normal_pm25 | 1282 |
| complaints_per_high_pm25_hour | 0.7073 |
| complaints_per_normal_pm25_hour | 0.2974 |

✅ Air quality complaints strongly correlated with high PM2.5

### E: Road Condition → Pothole Complaints
| condition   |   road_cnt |   pothole_cnt |   complaints_per_road |
|:------------|-----------:|--------------:|----------------------:|
| poor        |         17 |           738 |                 43.41 |
| fair        |         45 |           352 |                  7.82 |
| good        |         88 |           118 |                  1.34 |

✅ Poor road condition strongly increases pothole complaints

## 6. Public Transport Analysis
### Route Punctuality (Top 10 by trips)
| route_no   |   avg_delay |   on_time_pct |   trips |
|:-----------|------------:|--------------:|--------:|
| R09        |     3.0307  |         14.93 |    2606 |
| R07        |     2.97256 |         15.6  |    2551 |
| R19        |     3.09034 |         14.69 |    2546 |
| R06        |     2.94368 |         15.16 |    2539 |
| R12        |     3.06541 |         14.89 |    2538 |
| R16        |     3.05259 |         15.07 |    2529 |
| R08        |     3.00633 |         15.15 |    2528 |
| R17        |     2.99921 |         15.66 |    2523 |
| R13        |     2.98057 |         15.78 |    2522 |
| R03        |     3.04923 |         16.36 |    2519 |

### Weather Impact on Delays
| weather_condition   |   avg_delay |   trips |
|:--------------------|------------:|--------:|
| snow                |     4.2674  |   24301 |
| rain                |     2.98682 |     683 |
| fog                 |     2.79931 |     289 |
| clear               |     1.76835 |   24727 |

## 8. Summary Statistics
### Sensor Value Ranges
| sensor_type       |   min_val |   avg_val |   max_val | unit   |
|:------------------|----------:|----------:|----------:|:-------|
| noise_db          |   30.3721 |  50.8551  | 103.806   | dB     |
| pm25              |    1      |  24.7661  | 121.837   | ug/m3  |
| temp_c            |  -17.7491 |  -6.55552 |   4.95613 | C      |
| traffic_intensity |    0      | 127.035   | 954.5     | veh/h  |

### District Summary
| name       | type         | density   | income_level   |   population |   area_km2 |   industrial_coeff |   objects_cnt |   roads_cnt |
|:-----------|:-------------|:----------|:---------------|-------------:|-----------:|-------------------:|--------------:|------------:|
| District 3 | mixed        | high      | high           |      1225672 |     161.35 |              0.577 |           114 |          26 |
| District 5 | commercial   | medium    | high           |      1049681 |     274.98 |              0.123 |           119 |          26 |
| District 4 | recreational | low       | medium         |       550356 |     291.57 |              0.1   |           104 |          29 |
| District 2 | educational  | low       | medium         |       521630 |     252.38 |              0.077 |           106 |          37 |
| District 1 | commercial   | medium    | high           |       296670 |      59.86 |              0.162 |            57 |          32 |

### Citizen Requests by Category
| category           |   total_requests |   resolved |   resolution_pct |   avg_resolution_hours |
|:-------------------|-----------------:|-----------:|-----------------:|-----------------------:|
| air_quality        |             2053 |       1152 |            56.11 |                  10.73 |
| noise_complaint    |             1738 |        931 |            53.57 |                  10.24 |
| parking_issue      |             1680 |        933 |            55.54 |                  10.31 |
| heating_issue      |             1456 |        784 |            53.85 |                  10.87 |
| pothole            |             1208 |        670 |            55.46 |                  10.64 |
| broken_streetlight |             1021 |        561 |            54.95 |                  10.95 |
| water_leak         |              844 |        459 |            54.38 |                  10.33 |

## 9. Control SQL Queries

These queries should return non-empty results if data is correctly generated:

```sql
-- Top districts by requests (last 30 days from start date)
SELECT d.name, COUNT(*) AS req_cnt
FROM citizen_requests cr
JOIN districts d ON d.district_id = cr.district_id
WHERE cr.created_ts >= (SELECT datetime(MIN(created_ts), '+0 days') FROM citizen_requests)
  AND cr.created_ts <  (SELECT datetime(MIN(created_ts), '+30 days') FROM citizen_requests)
GROUP BY d.name
ORDER BY req_cnt DESC
LIMIT 10;

-- Traffic and noise before vs during event (sample event_id=1)
SELECT
  AVG(CASE WHEN s.sensor_type='traffic_intensity' THEN sr.value END) AS traffic_avg,
  AVG(CASE WHEN s.sensor_type='noise_db' THEN sr.value END) AS noise_avg
FROM sensor_readings sr
JOIN sensors s ON s.sensor_id=sr.sensor_id
JOIN city_objects o ON o.object_id=s.object_id
JOIN municipal_events e ON e.district_id=o.district_id
WHERE e.event_id=1
  AND sr.ts BETWEEN e.start_ts AND e.end_ts 
  AND sr.quality_flag='ok';

-- Route punctuality
SELECT route_no,
       AVG(delay_minutes) AS avg_delay,
       ROUND(100.0 * AVG(CASE WHEN delay_minutes=0 THEN 1.0 ELSE 0.0 END), 2) AS on_time_pct
FROM public_transport_trips
GROUP BY route_no
ORDER BY on_time_pct DESC
LIMIT 10;

-- PM2.5 high hours vs air_quality requests
WITH pm AS (
  SELECT o.district_id AS district_id,
         substr(sr.ts, 1, 13) || ':00:00' AS hour_ts,
         AVG(sr.value) AS pm25_avg
  FROM sensor_readings sr
  JOIN sensors s ON s.sensor_id=sr.sensor_id
  JOIN city_objects o ON o.object_id=s.object_id
  WHERE s.sensor_type='pm25' AND sr.quality_flag='ok'
  GROUP BY o.district_id, hour_ts
)
SELECT pm.district_id,
       SUM(CASE WHEN pm.pm25_avg > 35 THEN 1 ELSE 0 END) AS hours_pm25_gt_35,
       COUNT(DISTINCT cr.request_id) AS airq_requests
FROM pm
LEFT JOIN citizen_requests cr
  ON cr.district_id=pm.district_id
 AND substr(cr.created_ts, 1, 13) || ':00:00' = pm.hour_ts
 AND cr.category='air_quality'
GROUP BY pm.district_id
ORDER BY hours_pm25_gt_35 DESC
LIMIT 10;

-- Road network connectivity: Check if all districts are connected
WITH RECURSIVE connected_nodes AS (
    -- Start from node 1
    SELECT DISTINCT from_node_id AS node_id
    FROM city_objects
    WHERE object_type = 'road_segment' AND from_node_id = 1

    UNION

    -- Recursively add connected nodes
    SELECT DISTINCT co.to_node_id
    FROM city_objects co
    JOIN connected_nodes cn ON cn.node_id = co.from_node_id
    WHERE co.object_type = 'road_segment'

    UNION

    SELECT DISTINCT co.from_node_id
    FROM city_objects co
    JOIN connected_nodes cn ON cn.node_id = co.to_node_id
    WHERE co.object_type = 'road_segment'
)
SELECT 
    (SELECT COUNT(*) FROM road_network_nodes) AS total_nodes,
    COUNT(*) AS connected_nodes
FROM connected_nodes;

-- Road condition impact on pothole complaints
SELECT co.condition,
       COUNT(DISTINCT co.object_id) AS total_roads,
       COUNT(cr.request_id) AS pothole_complaints,
       ROUND(1.0 * COUNT(cr.request_id) / COUNT(DISTINCT co.object_id), 2) AS complaints_per_road
FROM city_objects co
LEFT JOIN citizen_requests cr ON cr.object_id = co.object_id AND cr.category = 'pothole'
WHERE co.object_type = 'road_segment'
GROUP BY co.condition
ORDER BY 
    CASE co.condition 
        WHEN 'poor' THEN 1 
        WHEN 'fair' THEN 2 
        WHEN 'good' THEN 3 
    END;

-- Road type vs average traffic intensity
SELECT co.road_type,
       COUNT(*) AS road_count,
       ROUND(AVG(sr.value), 2) AS avg_traffic_intensity,
       ROUND(AVG(co.max_speed_kmh), 2) AS avg_speed_limit
FROM city_objects co
JOIN sensors s ON s.object_id = co.object_id
JOIN sensor_readings sr ON sr.sensor_id = s.sensor_id
WHERE co.object_type = 'road_segment'
  AND s.sensor_type = 'traffic_intensity'
  AND sr.quality_flag = 'ok'
GROUP BY co.road_type
ORDER BY avg_traffic_intensity DESC;

-- Event types impact comparison
SELECT e.event_type,
       COUNT(*) AS event_count,
       ROUND(AVG(e.noise_increase_db), 2) AS avg_noise_increase,
       ROUND(AVG(e.traffic_increase_percent), 2) AS avg_traffic_increase,
       ROUND(AVG(e.expected_attendance), 0) AS avg_attendance
FROM municipal_events e
GROUP BY e.event_type
ORDER BY avg_traffic_increase DESC;

-- Meter peak times by utility type
SELECT sm.utility_type,
       SUM(CASE WHEN mr.is_peak = 1 THEN 1 ELSE 0 END) AS peak_readings,
       COUNT(*) AS total_readings,
       ROUND(100.0 * SUM(CASE WHEN mr.is_peak = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS peak_pct
FROM meter_readings mr
JOIN smart_meters sm ON sm.meter_id = mr.meter_id
GROUP BY sm.utility_type;
```

## 10. Validation Verdict
### ❌ **FAILED**: Critical issues detected

- ❌ 2 orphan nodes in road network

