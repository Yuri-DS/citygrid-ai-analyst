# CityGrid - Data Dictionary

This workspace describes the synthetic dataset CityGrid (smart city) stored in SQLite.

## Tables

### districts
- district_id (PK)
- name
- population
- area_km2
- center_lat, center_lon

### city_objects
- object_id (PK)
- district_id (FK -> districts)
- object_type: substation, streetlight, road_segment, stop, parking, building
- name
- lat, lon
- install_date (YYYY-MM-DD)
- status: active | inactive

### sensors
- sensor_id (PK)
- object_id (FK -> city_objects)
- sensor_type: noise_db | pm25 | traffic_intensity | temp_c
- unit
- is_active: 0/1

### smart_meters
- meter_id (PK)
- object_id (FK -> city_objects)
- utility_type: electricity_kwh | water_m3 | heating_gcal
- unit
- is_active: 0/1

### sensor_readings
- reading_id (PK)
- sensor_id (FK -> sensors)
- ts: YYYY-MM-DD HH:MM:SS
- value
- quality_flag: ok | missing | suspect

### meter_readings
- reading_id (PK)
- meter_id (FK -> smart_meters)
- ts
- value
- is_peak: 0/1

### municipal_events
- event_id (PK)
- district_id (FK)
- name
- event_type: concert | fair | football | parade | repair
- start_ts, end_ts
- attendance_est

### citizen_requests
- request_id (PK)
- district_id (FK)
- object_id (nullable FK -> city_objects)
- category: noise_complaint | pothole | broken_streetlight | water_leak | heating_issue | parking_issue
- created_ts
- status: open | in_progress | resolved
- resolved_ts (nullable)
- resolution_hours (nullable)
- priority: low | medium | high

### public_transport_trips
- trip_id (PK)
- route_no
- vehicle_id
- stop_object_id (FK -> city_objects, object_type='stop')
- scheduled_ts
- actual_ts
- passenger_est
