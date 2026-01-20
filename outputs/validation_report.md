# CityGrid - Validation Report

- DB: `C:\Users\1\PycharmProjects\citygrid-ai-analyst\data\citygrid.db`
- Generated with config: `C:\Users\1\PycharmProjects\citygrid-ai-analyst\configs\citygrid_generation.yaml`
- Scale: `medium`
- Period: 90 days

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
| districts | 10 |
| road_network_nodes | 250 |
| city_objects | 2,000 |
| sensors | 3,000 |
| smart_meters | 1,200 |
| municipal_events | 300 |
| citizen_requests | 40,000 |
| public_transport_trips | 200,000 |
| sensor_readings | 6,480,000 |
| meter_readings | 2,592,000 |

### Road Segments Breakdown
| object_type   |   cnt |
|:--------------|------:|
| building      |   629 |
| road_segment  |   600 |
| streetlight   |   285 |
| stop          |   183 |
| parking       |   131 |
| substation    |    91 |
| park          |    81 |

Road segments: 600 (30.0% of all objects)

## 3. Road Network Validation
### Node Types Distribution
| type         |   cnt |
|:-------------|------:|
| intersection |   240 |
| junction     |    10 |

| Metric | Value |
|---|---|
| total_nodes | 250 |
| district_center_nodes | 10 |

### Road Type Distribution
| road_type   |   cnt |   avg_length_m |   avg_speed |   avg_lanes |
|:------------|------:|---------------:|------------:|------------:|
| arterial    |   360 |       1007.68  |     70.1583 |     1.98333 |
| local       |   129 |        332.238 |     39.2481 |     1.55039 |
| highway     |   101 |       7344.02  |     99.8119 |     2.9505  |
| alley       |    10 |        837.137 |     24.7    |     1       |

### Road Condition Distribution
| condition   |   cnt |   pct |
|:------------|------:|------:|
| good        |   314 | 52.33 |
| fair        |   211 | 35.17 |
| poor        |    75 | 12.5  |

### Road Direction Distribution
| direction   |   cnt |
|:------------|------:|
| backward    |    34 |
| both        |   535 |
| forward     |    31 |

### Network Connectivity
| Metric | Value |
|---|---|
| orphan_nodes (not connected) | 0 |
| road_segments_with_null_from_node | 0 |
| road_segments_with_null_to_node | 0 |

✅ Network fully connected

## 4. Data Quality
### Quality Flags & Anomaly Scores
| Metric | Value |
|---|---|
| sensor_readings_total | 6,480,000 |
| ok_count | 5,948,061 |
| missing_count | 440,279 |
| suspect_count | 91,660 |
| ok_share | 0.9179 |
| missing_share | 0.0679 |
| suspect_share | 0.0141 |
| avg_suspect_anomaly_score | 0.7005 |
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
| noise_db          |        131676 |     1944000 |          6.77 |
| pm25              |         87145 |     1296000 |          6.72 |
| temp_c            |         59847 |      972000 |          6.16 |
| traffic_intensity |        161611 |     2268000 |          7.13 |

## 5. Causality Validation
### A: Events → Traffic & Noise Increase
| Metric | Value |
|---|---|
| sample_events_analyzed | 20 |
| avg_delta_traffic (during - before) | 103.415 veh/h |
| avg_delta_noise (during - before) | 3.628 dB |
| pct_events_with_traffic_increase | 90.0% |
| pct_events_with_noise_increase | 80.0% |

✅ Events clearly increase traffic and noise

### B: After Events → Increased Complaints
| Metric | Value |
|---|---|
| complaints_24h_after_events | 6091 |
| complaints_24h_before_events | 4411 |
| increase_pct | 38.1% |

✅ Complaints increase after events (20%+ increase)

### C: Cold Temperature → Heating Issues
| Metric | Value |
|---|---|
| heating_issues_on_cold_days (<0°C) | 4422 |
| heating_issues_on_warm_days (≥15°C) | 0 |
| cold_days_count | 66 |
| warm_days_count | 0 |
| heating_issues_per_cold_day | 67.00 |
| heating_issues_per_warm_day | 0.00 |

✅ Heating issues strongly correlated with cold weather

### D: High PM2.5 → Air Quality Complaints
| Metric | Value |
|---|---|
| hours_with_pm25_>35 | 7802 |
| hours_with_pm25_≤35 | 13798 |
| air_quality_complaints_when_high_pm25 | 2622 |
| air_quality_complaints_when_normal_pm25 | 5446 |
| complaints_per_high_pm25_hour | 0.3361 |
| complaints_per_normal_pm25_hour | 0.3947 |

⚠️ Weak correlation between PM2.5 and air quality complaints

### E: Road Condition → Pothole Complaints
| condition   |   road_cnt |   pothole_cnt |   complaints_per_road |
|:------------|-----------:|--------------:|----------------------:|
| poor        |         75 |          3059 |                 40.79 |
| fair        |        211 |          1572 |                  7.45 |
| good        |        314 |           530 |                  1.69 |

✅ Poor road condition strongly increases pothole complaints

## 6. Public Transport Analysis
### Route Punctuality (Top 10 by trips)
| route_no   |   avg_delay |   on_time_pct |   trips |
|:-----------|------------:|--------------:|--------:|
| R06        |     2.95946 |         16.2  |   10162 |
| R09        |     3.01404 |         15.09 |   10117 |
| R12        |     2.97557 |         15.93 |   10111 |
| R10        |     2.97911 |         15.33 |   10101 |
| R18        |     2.9779  |         15.24 |   10091 |
| R03        |     2.97096 |         15.45 |   10088 |
| R07        |     3.00209 |         15.12 |   10030 |
| R01        |     3.02264 |         14.86 |   10027 |
| R15        |     3.01018 |         15.34 |   10023 |
| R02        |     2.94729 |         16.02 |    9999 |

### Weather Impact on Delays
| weather_condition   |   avg_delay |   trips |
|:--------------------|------------:|--------:|
| snow                |     4.49928 |   60862 |
| rain                |     3.49407 |   10618 |
| fog                 |     3.24216 |    4398 |
| clear               |     2.19051 |  124122 |

## 8. Summary Statistics
### Sensor Value Ranges
| sensor_type       |   min_val |   avg_val |   max_val | unit   |
|:------------------|----------:|----------:|----------:|:-------|
| noise_db          |  32.4936  |   54.4938 |  110      | dB     |
| pm25              |   3.38776 |   31.0102 |  101.547  | ug/m3  |
| temp_c            | -18.2443  |   -3.0914 |   14.4651 | C      |
| traffic_intensity |   0       |  161.867  | 1375.75   | veh/h  |

### District Summary
| name        | type        | density   | income_level   |   population |   area_km2 |   industrial_coeff |   objects_cnt |   roads_cnt |
|:------------|:------------|:----------|:---------------|-------------:|-----------:|-------------------:|--------------:|------------:|
| District 3  | residential | high      | low            |       189957 |      25.42 |              0.169 |           286 |          74 |
| District 7  | residential | high      | medium         |       182012 |      30.84 |              0.156 |           278 |          75 |
| District 2  | mixed       | high      | high           |       177819 |      27.98 |              0.355 |           273 |          65 |
| District 5  | residential | high      | medium         |       176056 |      25.2  |              0.177 |           223 |          52 |
| District 1  | mixed       | high      | high           |       156950 |      18.73 |              0.605 |           191 |          50 |
| District 8  | commercial  | high      | medium         |       135872 |      23.14 |              0.235 |           188 |          53 |
| District 9  | residential | medium    | low            |       107220 |      22.07 |              0.223 |           187 |          55 |
| District 6  | mixed       | high      | medium         |        86614 |      16.49 |              0.296 |           160 |          61 |
| District 10 | industrial  | medium    | medium         |        66341 |      13.42 |              0.682 |           107 |          50 |
| District 4  | industrial  | medium    | low            |        44777 |      10.05 |              0.74  |           107 |          65 |

### Citizen Requests by Category
| category           |   total_requests |   resolved |   resolution_pct |   avg_resolution_hours |
|:-------------------|-----------------:|-----------:|-----------------:|-----------------------:|
| air_quality        |             8068 |       4472 |            55.43 |                  10.47 |
| noise_complaint    |             7052 |       3940 |            55.87 |                  10.55 |
| parking_issue      |             6771 |       3779 |            55.81 |                  10.4  |
| heating_issue      |             5463 |       2909 |            53.25 |                  10.53 |
| pothole            |             5161 |       2812 |            54.49 |                  10.36 |
| broken_streetlight |             4031 |       2198 |            54.53 |                  10.68 |
| water_leak         |             3454 |       1914 |            55.41 |                  10.51 |

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
### ✅ **PASSED**: Dataset is valid!

**No issues or warnings detected. Dataset meets all validation criteria.** 🎉

