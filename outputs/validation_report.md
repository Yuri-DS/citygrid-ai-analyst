# CityGrid - Validation Report

- DB: `D:\CityGrid AI Analyst\data\citygrid.db`
- Generated with config: `D:\CityGrid AI Analyst\configs\citygrid_generation.yaml`
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
| road_segment  |   600 |
| building      |   586 |
| streetlight   |   268 |
| stop          |   219 |
| parking       |   166 |
| park          |    97 |
| substation    |    64 |

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
| arterial    |   365 |       1064.9   |     70.1068 |     2.01918 |
| highway     |   123 |       5970.34  |     99.4959 |     3       |
| local       |   102 |        337.165 |     39.2255 |     1.52941 |
| alley       |    10 |        893.078 |     25.7    |     1       |

### Road Condition Distribution
| condition   |   cnt |   pct |
|:------------|------:|------:|
| good        |   335 | 55.83 |
| fair        |   177 | 29.5  |
| poor        |    88 | 14.67 |

### Road Direction Distribution
| direction   |   cnt |
|:------------|------:|
| backward    |    28 |
| both        |   525 |
| forward     |    47 |

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
| ok_count | 5,959,503 |
| missing_count | 407,199 |
| suspect_count | 113,298 |
| ok_share | 0.9197 |
| missing_share | 0.0628 |
| suspect_share | 0.0175 |
| avg_suspect_anomaly_score | 0.7017 |
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
| noise_db          |        123569 |     1944000 |          6.36 |
| pm25              |         84000 |     1296000 |          6.48 |
| temp_c            |         54547 |      972000 |          5.61 |
| traffic_intensity |        145083 |     2268000 |          6.4  |

## 5. Causality Validation
### A: Events → Traffic & Noise Increase
| Metric | Value |
|---|---|
| sample_events_analyzed | 20 |
| avg_delta_traffic (during - before) | 40.893 veh/h |
| avg_delta_noise (during - before) | 1.718 dB |
| pct_events_with_traffic_increase | 65.0% |
| pct_events_with_noise_increase | 60.0% |

✅ Events clearly increase traffic and noise

### B: After Events → Increased Complaints
| Metric | Value |
|---|---|
| complaints_24h_after_events | 5841 |
| complaints_24h_before_events | 4445 |
| increase_pct | 31.4% |

✅ Complaints increase after events (20%+ increase)

### C: Cold Temperature → Heating Issues
| Metric | Value |
|---|---|
| heating_issues_on_cold_days (<0°C) | 4216 |
| heating_issues_on_warm_days (≥15°C) | 0 |
| cold_days_count | 64 |
| warm_days_count | 0 |
| heating_issues_per_cold_day | 65.88 |
| heating_issues_per_warm_day | 0.00 |

✅ Heating issues strongly correlated with cold weather

### D: High PM2.5 → Air Quality Complaints
| Metric | Value |
|---|---|
| hours_with_pm25_>35 | 5116 |
| hours_with_pm25_≤35 | 16484 |
| air_quality_complaints_when_high_pm25 | 3335 |
| air_quality_complaints_when_normal_pm25 | 4935 |
| complaints_per_high_pm25_hour | 0.6519 |
| complaints_per_normal_pm25_hour | 0.2994 |

✅ Air quality complaints strongly correlated with high PM2.5

### E: Road Condition → Pothole Complaints
| condition   |   road_cnt |   pothole_cnt |   complaints_per_road |
|:------------|-----------:|--------------:|----------------------:|
| poor        |         88 |          3076 |                 34.95 |
| fair        |        177 |          1501 |                  8.48 |
| good        |        335 |           520 |                  1.55 |

✅ Poor road condition strongly increases pothole complaints

## 6. Public Transport Analysis
### Route Punctuality (Top 10 by trips)
| route_no   |   avg_delay |   on_time_pct |   trips |
|:-----------|------------:|--------------:|--------:|
| R06        |     3.0243  |         15.62 |   10166 |
| R09        |     3.10028 |         14.92 |   10132 |
| R12        |     3.0663  |         16.03 |   10106 |
| R10        |     3.08653 |         15.04 |   10100 |
| R03        |     3.06619 |         15.5  |   10092 |
| R18        |     3.04623 |         15.6  |   10081 |
| R01        |     3.10985 |         14.89 |   10041 |
| R15        |     3.07292 |         15.42 |   10038 |
| R07        |     3.0806  |         15.33 |   10025 |
| R13        |     3.05823 |         15.44 |    9994 |

### Weather Impact on Delays
| weather_condition   |   avg_delay |   trips |
|:--------------------|------------:|--------:|
| snow                |     4.60587 |   60800 |
| rain                |     3.56815 |   10580 |
| fog                 |     3.28635 |    4463 |
| clear               |     2.26458 |  124157 |

## 8. Summary Statistics
### Sensor Value Ranges
| sensor_type       |   min_val |   avg_val |   max_val | unit   |
|:------------------|----------:|----------:|----------:|:-------|
| noise_db          |   30.0231 |  54.9179  |  110      | dB     |
| pm25              |    1      |  28.5438  |  104.858  | ug/m3  |
| temp_c            |  -17.7464 |  -2.75885 |   16.9183 | C      |
| traffic_intensity |    0      | 160.869   | 1623.06   | veh/h  |

### District Summary
| name        | type         | density   | income_level   |   population |   area_km2 |   industrial_coeff |   objects_cnt |   roads_cnt |
|:------------|:-------------|:----------|:---------------|-------------:|-----------:|-------------------:|--------------:|------------:|
| District 5  | mixed        | high      | low            |      1321988 |     229.5  |              0.624 |           396 |          66 |
| District 10 | mixed        | very_high | high           |      1127449 |     122.33 |              0.273 |           262 |          54 |
| District 9  | residential  | high      | medium         |       899775 |     111.87 |              0.16  |           227 |          55 |
| District 1  | mixed        | high      | medium         |       548517 |      95.92 |              0.498 |           194 |          71 |
| District 8  | residential  | medium    | high           |       449931 |     121.29 |              0.112 |           192 |          48 |
| District 6  | residential  | high      | medium         |       414886 |      56.55 |              0.202 |           140 |          54 |
| District 2  | commercial   | medium    | high           |       288521 |      67.93 |              0.34  |           151 |          69 |
| District 3  | educational  | medium    | medium         |       271098 |      84.98 |              0.058 |           169 |          72 |
| District 7  | commercial   | high      | low            |       259191 |      47.24 |              0.162 |           116 |          56 |
| District 4  | recreational | low       | medium         |       217557 |     102.52 |              0.07  |           153 |          55 |

### Citizen Requests by Category
| category           |   total_requests |   resolved |   resolution_pct |   avg_resolution_hours |
|:-------------------|-----------------:|-----------:|-----------------:|-----------------------:|
| air_quality        |             8270 |       4575 |            55.32 |                  10.53 |
| noise_complaint    |             6914 |       3826 |            55.34 |                  10.72 |
| parking_issue      |             6733 |       3679 |            54.64 |                  10.42 |
| heating_issue      |             5264 |       2866 |            54.45 |                  10.44 |
| pothole            |             5097 |       2808 |            55.09 |                  10.5  |
| broken_streetlight |             4261 |       2321 |            54.47 |                  10.58 |
| water_leak         |             3461 |       1869 |            54    |                  10.66 |

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

