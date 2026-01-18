# CityGrid - Data Dictionary

## districts
- district_id: PK
- type: residential/commercial/industrial/mixed/recreational/educational
- industrial_coeff: [0..1]
- center_lat, center_lon: центр района
- geometry: WKT полигона

## road_network_nodes
- node_id: PK
- type: intersection/junction/terminal
- is_connected_to_district_center: флаг связи с центром района

## city_objects
- object_id: PK
- object_type: building/road_segment/streetlight/stop/parking/substation/park
- capacity: только для stop/parking
- Поля для road_segment: length_m, from_node_id, to_node_id, road_type, max_speed_kmh, lanes_count, direction, condition, start_lat/lon, end_lat/lon

## sensors
- sensor_type: noise_db/pm25/traffic_intensity/temp_c

## sensor_readings
- quality_flag: ok/missing/suspect
- anomaly_score: 0 для ok/missing, >0 для suspect

## meter_readings
- is_peak: 1 если value >= 90-й перцентиль
