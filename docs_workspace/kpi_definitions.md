# CityGrid - KPI Definitions

## Transport Performance
- **On-time share:** fraction of trips with delay_minutes = 0
  ```sql
  SELECT ROUND(SUM(CASE WHEN delay_minutes = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as on_time_pct
  FROM public_transport_trips;
  ```
- **Avg delay:** average delay per route
  ```sql
  SELECT route_no, ROUND(AVG(delay_minutes), 2) as avg_delay
  FROM public_transport_trips GROUP BY route_no ORDER BY avg_delay DESC;
  ```

## Citizen Engagement
- **Complaint rate:** number of requests per 10,000 population
  ```sql
  SELECT d.name, ROUND(COUNT(cr.request_id) * 10000.0 / d.population, 2) as rate_per_10k
  FROM districts d
  LEFT JOIN citizen_requests cr ON d.district_id = cr.district_id
  GROUP BY d.district_id ORDER BY rate_per_10k DESC;
  ```
- **Resolution rate:** fraction of resolved among all requests
  ```sql
  SELECT ROUND(SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as resolution_pct
  FROM citizen_requests;
  ```

## Event Impact
- **Traffic change:** compare traffic_intensity before/during event (requires sensor_readings + municipal_events join with time overlap)
- **Noise change:** compare noise_db before/during event (requires sensor_readings + municipal_events join with time overlap)

## Road Network
- **Avg road condition:** distribution of good/fair/poor
  ```sql
  SELECT condition, COUNT(*) as count,
         ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as pct
  FROM city_objects WHERE object_type = 'road_segment'
  GROUP BY condition;
  ```
