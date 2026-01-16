import sqlite3
import pandas as pd
import folium

# --- Load data ---
conn = sqlite3.connect("data/citygrid.db")

# Берем объекты с координатами
df = pd.read_sql("""
SELECT
  o.object_id,
  o.object_type,
  o.name,
  o.lat,
  o.lon,
  d.name AS district
FROM city_objects o
JOIN districts d ON d.district_id = o.district_id
WHERE o.lat IS NOT NULL AND o.lon IS NOT NULL
""", conn)

conn.close()

# --- Create map ---
m = folium.Map(
    location=[df.lat.mean(), df.lon.mean()],
    zoom_start=11,
    tiles="OpenStreetMap"
)

# Цвета по типам объектов
color_map = {
    "building": "blue",
    "streetlight": "yellow",
    "road_segment": "gray",
    "stop": "green",
    "parking": "purple",
    "substation": "red",
}

# --- Add markers ---
for _, row in df.iterrows():
    folium.CircleMarker(
        location=[row.lat, row.lon],
        radius=2,
        color=color_map.get(row.object_type, "black"),
        fill=True,
        fill_opacity=0.7,
        popup=f"""
        <b>{row.name}</b><br>
        Type: {row.object_type}<br>
        District: {row.district}
        """
    ).add_to(m)

# --- Save ---
m.save("outputs/citygrid_map.html")
print("Map saved to outputs/citygrid_map.html")
