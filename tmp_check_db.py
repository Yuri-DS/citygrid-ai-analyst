import sqlite3

conn = sqlite3.connect("data/citygrid.db")
cur = conn.cursor()

tables = [
    "districts",
    "city_objects",
    "sensors",
    "smart_meters",
    "municipal_events",
    "citizen_requests",
    "public_transport_trips",
    "sensor_readings",
    "meter_readings",
]

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"{t}: {cur.fetchone()[0]}")

conn.close()
