# CityGrid Table Relationships

## Key Concept: city_objects is Central

Most data connects through `city_objects` table. This table contains ALL physical infrastructure - buildings, roads, streetlights, stops, etc.

**Important:** There are no separate tables for roads, buildings, etc. Everything is in `city_objects`, distinguished by `object_type` column.

```
districts
    │
    └── city_objects (via district_id)
            │
            ├── sensors (via object_id)
            │       └── sensor_readings (via sensor_id)
            │
            ├── smart_meters (via object_id)
            │       └── meter_readings (via meter_id)
            │
            └── public_transport_trips (via stop_object_id)
```

---

## Direct Relationships

### districts → city_objects
Every city object belongs to a district.
```
city_objects.district_id → districts.district_id
```

### districts → citizen_requests
Complaints are filed in districts.
```
citizen_requests.district_id → districts.district_id
```

### districts → municipal_events
Events happen in districts.
```
municipal_events.district_id → districts.district_id
```

### city_objects → sensors
Sensors are installed on city objects.
```
sensors.object_id → city_objects.object_id
```

### city_objects → smart_meters
Meters are installed in buildings.
```
smart_meters.object_id → city_objects.object_id
```

### sensors → sensor_readings
Time series data from sensors.
```
sensor_readings.sensor_id → sensors.sensor_id
```

### smart_meters → meter_readings
Time series data from meters.
```
meter_readings.meter_id → smart_meters.meter_id
```

### city_objects (stops) → public_transport_trips
Trips arrive at stops.
```
public_transport_trips.stop_object_id → city_objects.object_id (where object_type='stop')
```

### road_network_nodes → city_objects (road_segment)
Road segments connect nodes.
```
city_objects.from_node_id → road_network_nodes.node_id
city_objects.to_node_id → road_network_nodes.node_id
```

---

## Common JOIN Patterns

### To get district information for any object:
```
... JOIN districts d ON <table>.district_id = d.district_id
```

### To get location for sensors (sensors don't have direct lat/lon):
```
FROM sensors s
JOIN city_objects co ON s.object_id = co.object_id
-- Now co.lat and co.lon are available
```

### To get district for sensors (two-step):
```
FROM sensors s
JOIN city_objects co ON s.object_id = co.object_id
JOIN districts d ON co.district_id = d.district_id
```

### To filter city_objects by type:
```
FROM city_objects WHERE object_type = '<type>'
-- Types: building, road_segment, streetlight, stop, parking, substation, park
```

---

## Important Notes

1. **No separate road table**: Roads are `city_objects WHERE object_type = 'road_segment'`

2. **Coordinates vary by table:**
   - districts: center_lat, center_lon
   - city_objects: lat, lon (and start_lat/lon, end_lat/lon for road_segment)
   - sensors: no direct coords, join with city_objects
   - municipal_events: lat, lon
   - road_network_nodes: lat, lon

3. **Large tables need time filters:**
   - sensor_readings
   - meter_readings
   
4. **Nullable foreign keys:**
   - citizen_requests.object_id - may be NULL if complaint isn't about specific object
