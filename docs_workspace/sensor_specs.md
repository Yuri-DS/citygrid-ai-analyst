# CityGrid - Sensor specs

## Sensor types and units
- temp_c: C, typical -12 .. +27
- traffic_intensity: veh/h
- noise_db: dB, typical 32 .. 95
- pm25: ug/m3, typical 4 .. 160

## quality_flag
- ok: normal
- missing: downtime window (value filled with 0 but flagged)
- suspect: rare anomaly spike
