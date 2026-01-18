#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate interactive HTML map of CityGrid with road network
"""

import sqlite3
import pandas as pd
import folium
from folium import plugins
import yaml
import sys
from pathlib import Path


def create_citygrid_map():
    """Create interactive map with districts, roads, nodes, and objects"""

    # Load config
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    cfg_path = project_dir / "configs" / "citygrid_generation.yaml"
    if len(sys.argv) > 1:
        cfg_path = Path(sys.argv[1]).resolve()

    print(f"Loading config from {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    db_path = Path(cfg["output"]["sqlite_path"])
    if not db_path.is_absolute():
        db_path = (project_dir / db_path).resolve()

    print(f"Connecting to database {db_path}")
    conn = sqlite3.connect(str(db_path))

    # ===== 1. CENTER MAP ON DISTRICTS =====
    print("Loading districts...")
    districts = pd.read_sql_query("""
        SELECT district_id, name, type, center_lat, center_lon, 
               population, density, income_level
        FROM districts
    """, conn)

    center_lat = districts.center_lat.mean()
    center_lon = districts.center_lon.mean()

    # Create base map with layers control
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )

    # ===== 2. DISTRICTS LAYER =====
    print("Adding districts...")
    districts_layer = folium.FeatureGroup(name='Districts', show=True)

    district_colors = {
        'residential': '#3498db',  # blue
        'commercial': '#e74c3c',  # red
        'industrial': '#95a5a6',  # gray
        'mixed': '#9b59b6',  # purple
        'recreational': '#2ecc71',  # green
        'educational': '#f39c12'  # orange
    }

    for _, d in districts.iterrows():
        folium.CircleMarker(
            location=[d['center_lat'], d['center_lon']],
            radius=15,
            popup=folium.Popup(
                f"<b>{d['name']}</b><br>"
                f"Type: {d['type']}<br>"
                f"Population: {d['population']:,}<br>"
                f"Density: {d['density']}<br>"
                f"Income: {d['income_level']}",
                max_width=200
            ),
            tooltip=d['name'],
            color=district_colors.get(d['type'], '#000000'),
            fill=True,
            fillColor=district_colors.get(d['type'], '#000000'),
            fillOpacity=0.3,
            weight=2
        ).add_to(districts_layer)

    districts_layer.add_to(m)

    # ===== 3. ROAD NETWORK NODES LAYER =====
    print("Loading road network nodes...")
    nodes = pd.read_sql_query("""
        SELECT node_id, lat, lon, type, is_connected_to_district_center
        FROM road_network_nodes
    """, conn)

    nodes_layer = folium.FeatureGroup(name='Road Network Nodes', show=False)

    node_colors = {
        'junction': '#e74c3c',  # red for junctions (district centers)
        'intersection': '#3498db',  # blue for intersections
        'terminal': '#f39c12'  # orange for terminals
    }

    for _, n in nodes.iterrows():
        folium.CircleMarker(
            location=[n['lat'], n['lon']],
            radius=3 if n['type'] == 'junction' else 2,
            popup=f"Node {n['node_id']}<br>Type: {n['type']}",
            tooltip=f"Node {n['node_id']}",
            color=node_colors.get(n['type'], '#000000'),
            fill=True,
            fillOpacity=0.7,
            weight=1
        ).add_to(nodes_layer)

    nodes_layer.add_to(m)

    # ===== 4. ROAD SEGMENTS LAYER =====
    print("Loading road segments...")
    roads = pd.read_sql_query("""
        SELECT object_id, name, start_lat, start_lon, end_lat, end_lon,
               road_type, max_speed_kmh, lanes_count, direction, condition,
               length_m
        FROM city_objects
        WHERE object_type = 'road_segment'
    """, conn)

    roads_layer = folium.FeatureGroup(name='Roads', show=True)

    road_colors = {
        'highway': '#e74c3c',  # red
        'arterial': '#f39c12',  # orange
        'local': '#3498db',  # blue
        'alley': '#95a5a6'  # gray
    }

    road_weights = {
        'highway': 6,
        'arterial': 4,
        'local': 2,
        'alley': 1
    }

    print(f"Drawing {len(roads)} road segments...")
    for _, r in roads.iterrows():
        if pd.notna(r['start_lat']) and pd.notna(r['end_lat']):
            # Determine opacity based on condition
            opacity = {
                'good': 0.8,
                'fair': 0.6,
                'poor': 0.4
            }.get(r['condition'], 0.5)

            # Create popup with road info
            popup_html = f"""
                <b>{r['name']}</b><br>
                Type: {r['road_type']}<br>
                Condition: {r['condition']}<br>
                Speed limit: {r['max_speed_kmh']} km/h<br>
                Lanes: {r['lanes_count']}<br>
                Direction: {r['direction']}<br>
                Length: {r['length_m']:.0f} m
            """

            folium.PolyLine(
                locations=[
                    [r['start_lat'], r['start_lon']],
                    [r['end_lat'], r['end_lon']]
                ],
                color=road_colors.get(r['road_type'], 'gray'),
                weight=road_weights.get(r['road_type'], 2),
                opacity=opacity,
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=f"{r['road_type']}: {r['condition']}"
            ).add_to(roads_layer)

    roads_layer.add_to(m)

    # ===== 5. OTHER CITY OBJECTS LAYER =====
    print("Loading other city objects...")
    objects = pd.read_sql_query("""
        SELECT object_id, object_type, name, lat, lon, capacity, status
        FROM city_objects
        WHERE object_type != 'road_segment'
        LIMIT 500
    """, conn)

    objects_layer = folium.FeatureGroup(name='City Objects (sample 500)', show=False)

    object_icons = {
        'building': {'icon': 'home', 'color': 'blue'},
        'streetlight': {'icon': 'lightbulb', 'color': 'orange'},
        'stop': {'icon': 'bus', 'color': 'red'},
        'parking': {'icon': 'car', 'color': 'purple'},
        'substation': {'icon': 'plug', 'color': 'gray'},
        'park': {'icon': 'tree', 'color': 'green'}
    }

    for _, obj in objects.iterrows():
        icon_config = object_icons.get(obj['object_type'], {'icon': 'info-sign', 'color': 'gray'})

        popup_html = f"""
            <b>{obj['name']}</b><br>
            Type: {obj['object_type']}<br>
            Status: {obj['status']}
        """
        if pd.notna(obj['capacity']):
            popup_html += f"<br>Capacity: {obj['capacity']}"

        folium.Marker(
            location=[obj['lat'], obj['lon']],
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=obj['object_type'],
            icon=folium.Icon(
                color=icon_config['color'],
                icon=icon_config['icon'],
                prefix='fa'
            )
        ).add_to(objects_layer)

    objects_layer.add_to(m)

    # ===== 6. SENSORS WITH ISSUES LAYER =====
    print("Loading sensors with data quality issues...")
    sensors_issues = pd.read_sql_query("""
        SELECT DISTINCT s.sensor_id, s.sensor_type, o.lat, o.lon, o.name
        FROM sensors s
        JOIN city_objects o ON o.object_id = s.object_id
        JOIN sensor_readings sr ON sr.sensor_id = s.sensor_id
        WHERE sr.quality_flag IN ('missing', 'suspect')
        LIMIT 100
    """, conn)

    if not sensors_issues.empty:
        sensors_layer = folium.FeatureGroup(name='Sensors with Issues (sample 100)', show=False)

        for _, s in sensors_issues.iterrows():
            folium.CircleMarker(
                location=[s['lat'], s['lon']],
                radius=4,
                popup=f"Sensor {s['sensor_id']}<br>Type: {s['sensor_type']}<br>Location: {s['name']}",
                tooltip=s['sensor_type'],
                color='red',
                fill=True,
                fillColor='red',
                fillOpacity=0.5
            ).add_to(sensors_layer)

        sensors_layer.add_to(m)

    # ===== 7. EVENTS LAYER =====
    print("Loading municipal events...")
    events = pd.read_sql_query("""
        SELECT event_id, name, event_type, lat, lon, 
               impact_radius_km, expected_attendance,
               start_ts, end_ts
        FROM municipal_events
        LIMIT 50
    """, conn)

    if not events.empty:
        events_layer = folium.FeatureGroup(name='Events (sample 50)', show=False)

        event_colors = {
            'concert': '#9b59b6',
            'construction': '#e67e22',
            'accident': '#e74c3c',
            'protest': '#f39c12',
            'festival': '#1abc9c',
            'sports_event': '#3498db'
        }

        for _, e in events.iterrows():
            folium.Circle(
                location=[e['lat'], e['lon']],
                radius=e['impact_radius_km'] * 1000,  # km to meters
                popup=folium.Popup(
                    f"<b>{e['name']}</b><br>"
                    f"Type: {e['event_type']}<br>"
                    f"Attendance: {e['expected_attendance']:,}<br>"
                    f"Impact radius: {e['impact_radius_km']:.2f} km<br>"
                    f"Start: {e['start_ts']}<br>"
                    f"End: {e['end_ts']}",
                    max_width=250
                ),
                tooltip=e['event_type'],
                color=event_colors.get(e['event_type'], '#95a5a6'),
                fill=True,
                fillOpacity=0.1,
                weight=2
            ).add_to(events_layer)

        events_layer.add_to(m)

    # ===== 8. ADD LEGEND =====
    legend_html = """
    <div style="
        position: fixed;
        bottom: 50px; right: 50px;
        width: 200px;
        background-color: white;
        border: 2px solid grey;
        z-index: 9999;
        font-size: 12px;
        padding: 10px;
        border-radius: 5px;
    ">
    <h4 style="margin-top: 0;">Road Types</h4>
    <p><span style="color: #e74c3c;">━━━</span> Highway</p>
    <p><span style="color: #f39c12;">━━━</span> Arterial</p>
    <p><span style="color: #3498db;">━━━</span> Local</p>
    <p><span style="color: #95a5a6;">━━━</span> Alley</p>
    <hr>
    <h4>Road Condition</h4>
    <p>Opacity: Good > Fair > Poor</p>
    <hr>
    <h4>Districts</h4>
    <p><span style="color: #3498db;">●</span> Residential</p>
    <p><span style="color: #e74c3c;">●</span> Commercial</p>
    <p><span style="color: #95a5a6;">●</span> Industrial</p>
    <p><span style="color: #9b59b6;">●</span> Mixed</p>
    <p><span style="color: #2ecc71;">●</span> Recreational</p>
    <p><span style="color: #f39c12;">●</span> Educational</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ===== 9. ADD LAYER CONTROL =====
    folium.LayerControl(collapsed=False).add_to(m)

    # ===== 10. ADD MINIMAP =====
    minimap = plugins.MiniMap(toggle_display=True)
    m.add_child(minimap)

    # ===== 11. ADD FULLSCREEN BUTTON =====
    plugins.Fullscreen(
        position='topleft',
        title='Fullscreen',
        title_cancel='Exit fullscreen',
        force_separate_button=True
    ).add_to(m)

    # ===== 12. SAVE MAP =====
    out_dir = project_dir / "outputs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "citygrid_map.html"

    m.save(str(out_path))

    print(f"\n✅ Map saved to: {out_path}")
    print(f"   Districts: {len(districts)}")
    print(f"   Nodes: {len(nodes)}")
    print(f"   Roads: {len(roads)}")
    print(f"   Objects: {len(objects)} (sample)")
    if not sensors_issues.empty:
        print(f"   Sensors with issues: {len(sensors_issues)} (sample)")
    if not events.empty:
        print(f"   Events: {len(events)} (sample)")

    conn.close()


if __name__ == "__main__":
    try:
        create_citygrid_map()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
