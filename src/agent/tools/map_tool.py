"""
Map Tool for CityGrid AI Agent.

Creates interactive Folium maps for geographic visualization.
"""

import json
from typing import Any
import folium
from folium.plugins import MarkerCluster
import pandas as pd
from langchain_core.tools import tool


# Color schemes for different data types
CONDITION_COLORS = {
    "good": "green",
    "fair": "orange",
    "poor": "red"
}

ROAD_TYPE_COLORS = {
    "highway": "#e41a1c",
    "arterial": "#ff7f00",
    "local": "#377eb8",
    "alley": "#999999"
}

DISTRICT_TYPE_COLORS = {
    "residential": "#2ecc71",
    "commercial": "#3498db",
    "industrial": "#e74c3c",
    "mixed": "#9b59b6",
    "recreational": "#1abc9c",
    "educational": "#f39c12"
}

SENSOR_TYPE_COLORS = {
    "noise_db": "#e74c3c",
    "pm25": "#9b59b6",
    "traffic_intensity": "#3498db",
    "temp_c": "#f39c12"
}


def create_base_map(center_lat: float, center_lon: float, zoom: int = 12) -> folium.Map:
    """Create a base folium map with dark theme."""
    return folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        tiles="CartoDB dark_matter"
    )


@tool
def create_district_map(
    data: str,
    value_column: str = None,
    title: str = "Districts Map"
) -> dict[str, Any]:
    """
    Create an interactive map showing city districts.
    
    Use this tool to visualize district-level data on a map.
    
    Args:
        data: JSON string with district data. Must include 'center_lat', 'center_lon', 'name'.
              Can also include 'type', 'population', or any numeric column for coloring.
        value_column: Column name to use for circle size/color intensity (e.g., 'population')
        title: Map title
    
    Returns:
        Dictionary with 'success', 'map_html' (HTML string to render map)
    
    Example:
        1. Get data: execute_sql("SELECT name, center_lat, center_lon, population, type FROM districts")
        2. Create map: create_district_map(data, "population", "Population by District")
    """
    try:
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data
        
        if not data_list:
            return {"success": False, "error": "No data provided"}
        
        df = pd.DataFrame(data_list)
        
        # Validate required columns
        required = ["center_lat", "center_lon", "name"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return {
                "success": False,
                "error": f"Missing required columns: {missing}. Available: {list(df.columns)}"
            }
        
        # Calculate map center
        center_lat = df["center_lat"].mean()
        center_lon = df["center_lon"].mean()
        
        # Create map
        m = create_base_map(center_lat, center_lon, zoom=11)
        
        # Add title
        title_html = f'''
            <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                        z-index: 1000; background: rgba(0,0,0,0.7); padding: 10px 20px;
                        border-radius: 5px; color: white; font-size: 16px; font-weight: bold;">
                {title}
            </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Calculate sizes if value_column provided
        if value_column and value_column in df.columns:
            min_val = df[value_column].min()
            max_val = df[value_column].max()
            # Normalize to radius 10-30
            df["_radius"] = 10 + 20 * (df[value_column] - min_val) / (max_val - min_val + 1)
        else:
            df["_radius"] = 15
        
        # Add district markers
        for _, row in df.iterrows():
            # Determine color
            if "type" in df.columns:
                color = DISTRICT_TYPE_COLORS.get(row.get("type"), "#3498db")
            else:
                color = "#3498db"
            
            # Build popup content
            popup_lines = [f"<b>{row['name']}</b>"]
            if "type" in df.columns:
                popup_lines.append(f"Type: {row['type']}")
            if "population" in df.columns:
                popup_lines.append(f"Population: {row['population']:,}")
            if "area_km2" in df.columns:
                popup_lines.append(f"Area: {row['area_km2']:.1f} km²")
            if value_column and value_column in df.columns and value_column not in ["type", "population", "area_km2"]:
                popup_lines.append(f"{value_column}: {row[value_column]}")
            
            popup_html = "<br>".join(popup_lines)
            
            # Add circle marker
            folium.CircleMarker(
                location=[row["center_lat"], row["center_lon"]],
                radius=row["_radius"],
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.6,
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=row["name"]
            ).add_to(m)
        
        # Add legend if types present
        if "type" in df.columns:
            legend_html = '''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">District Types</p>
            '''
            for dtype, color in DISTRICT_TYPE_COLORS.items():
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">●</span> {dtype}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))
        
        return {
            "success": True,
            "map_html": m._repr_html_(),
            "districts_count": len(df),
            "title": title
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def create_points_map(
    data: str,
    lat_column: str = "lat",
    lon_column: str = "lon",
    label_column: str = None,
    color_column: str = None,
    title: str = "Points Map"
) -> dict[str, Any]:
    """
    Create a map with point markers (for sensors, events, requests, etc.).
    
    Use this for visualizing individual locations on a map.
    
    Args:
        data: JSON string with location data
        lat_column: Name of latitude column (default: "lat")
        lon_column: Name of longitude column (default: "lon")
        label_column: Column for marker labels/popups (optional)
        color_column: Column for color grouping (optional, e.g., "sensor_type", "category")
        title: Map title
    
    Returns:
        Dictionary with 'success', 'map_html'
    
    Example:
        1. Get sensors: execute_sql("SELECT s.sensor_id, s.sensor_type, co.lat, co.lon FROM sensors s JOIN city_objects co ON s.object_id = co.object_id LIMIT 100")
        2. Map them: create_points_map(data, "lat", "lon", "sensor_id", "sensor_type", "Sensor Locations")
    """
    try:
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data
        
        if not data_list:
            return {"success": False, "error": "No data provided"}
        
        df = pd.DataFrame(data_list)
        
        # Validate coordinate columns
        if lat_column not in df.columns or lon_column not in df.columns:
            return {
                "success": False,
                "error": f"Coordinate columns not found. Need '{lat_column}' and '{lon_column}'. Available: {list(df.columns)}"
            }
        
        # Remove rows with missing coordinates
        df = df.dropna(subset=[lat_column, lon_column])
        
        if df.empty:
            return {"success": False, "error": "No valid coordinates in data"}
        
        # Calculate center
        center_lat = df[lat_column].mean()
        center_lon = df[lon_column].mean()
        
        # Create map
        m = create_base_map(center_lat, center_lon, zoom=12)
        
        # Add title
        title_html = f'''
            <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                        z-index: 1000; background: rgba(0,0,0,0.7); padding: 10px 20px;
                        border-radius: 5px; color: white; font-size: 16px; font-weight: bold;">
                {title}
            </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Use marker cluster for many points
        use_cluster = len(df) > 50
        if use_cluster:
            marker_group = MarkerCluster()
        else:
            marker_group = folium.FeatureGroup()
        
        # Determine color mapping
        if color_column and color_column in df.columns:
            unique_vals = df[color_column].unique()
            # Try to use predefined colors, otherwise generate
            if color_column == "sensor_type":
                color_map = SENSOR_TYPE_COLORS
            elif color_column == "condition":
                color_map = CONDITION_COLORS
            else:
                colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#34495e"]
                color_map = {v: colors[i % len(colors)] for i, v in enumerate(unique_vals)}
        else:
            color_map = {}
        
        # Add markers
        for _, row in df.iterrows():
            # Determine color
            if color_column and color_column in df.columns:
                color = color_map.get(row[color_column], "#3498db")
            else:
                color = "#3498db"
            
            # Build popup
            if label_column and label_column in df.columns:
                popup_text = str(row[label_column])
            else:
                popup_text = f"({row[lat_column]:.4f}, {row[lon_column]:.4f})"
            
            if color_column and color_column in df.columns:
                popup_text += f"<br>{color_column}: {row[color_column]}"
            
            folium.CircleMarker(
                location=[row[lat_column], row[lon_column]],
                radius=6,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                popup=popup_text
            ).add_to(marker_group)
        
        marker_group.add_to(m)
        
        # Add legend if color column used
        if color_column and color_column in df.columns:
            legend_html = f'''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">{color_column}</p>
            '''
            for val, color in color_map.items():
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">●</span> {val}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))
        
        return {
            "success": True,
            "map_html": m._repr_html_(),
            "points_count": len(df),
            "title": title
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool  
def create_road_map(
    data: str,
    color_by: str = "condition",
    title: str = "Road Network"
) -> dict[str, Any]:
    """
    Create a map showing road segments.
    
    Use this to visualize the road network with color coding by condition or type.
    
    Args:
        data: JSON string with road data. Must include 'start_lat', 'start_lon', 'end_lat', 'end_lon'.
              Should also include 'road_type' or 'condition' for coloring.
        color_by: Column to use for coloring - "condition" or "road_type"
        title: Map title
    
    Returns:
        Dictionary with 'success', 'map_html'
    
    Example:
        1. Get roads: execute_sql("SELECT name, road_type, condition, start_lat, start_lon, end_lat, end_lon FROM city_objects WHERE object_type='road_segment' LIMIT 200")
        2. Map them: create_road_map(data, "condition", "Road Conditions")
    """
    try:
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data
        
        if not data_list:
            return {"success": False, "error": "No data provided"}
        
        df = pd.DataFrame(data_list)
        
        # Validate required columns
        required = ["start_lat", "start_lon", "end_lat", "end_lon"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return {
                "success": False,
                "error": f"Missing required columns: {missing}. Available: {list(df.columns)}"
            }
        
        # Calculate center
        center_lat = (df["start_lat"].mean() + df["end_lat"].mean()) / 2
        center_lon = (df["start_lon"].mean() + df["end_lon"].mean()) / 2
        
        # Create map
        m = create_base_map(center_lat, center_lon, zoom=12)
        
        # Add title
        title_html = f'''
            <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                        z-index: 1000; background: rgba(0,0,0,0.7); padding: 10px 20px;
                        border-radius: 5px; color: white; font-size: 16px; font-weight: bold;">
                {title}
            </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Select color map
        if color_by == "condition":
            color_map = CONDITION_COLORS
        elif color_by == "road_type":
            color_map = ROAD_TYPE_COLORS
        else:
            color_map = {}
        
        # Add road segments
        for _, row in df.iterrows():
            # Determine color
            if color_by in df.columns:
                color = color_map.get(row[color_by], "#3498db")
            else:
                color = "#3498db"
            
            # Determine weight by road type
            weight = 2
            if "road_type" in df.columns:
                if row.get("road_type") == "highway":
                    weight = 4
                elif row.get("road_type") == "arterial":
                    weight = 3
            
            # Build popup
            popup_lines = []
            if "name" in df.columns and pd.notna(row.get("name")):
                popup_lines.append(f"<b>{row['name']}</b>")
            if "road_type" in df.columns:
                popup_lines.append(f"Type: {row['road_type']}")
            if "condition" in df.columns:
                popup_lines.append(f"Condition: {row['condition']}")
            if "length_m" in df.columns:
                popup_lines.append(f"Length: {row['length_m']:.0f}m")
            
            popup_html = "<br>".join(popup_lines) if popup_lines else "Road segment"
            
            folium.PolyLine(
                locations=[
                    [row["start_lat"], row["start_lon"]],
                    [row["end_lat"], row["end_lon"]]
                ],
                weight=weight,
                color=color,
                opacity=0.8,
                popup=popup_html
            ).add_to(m)
        
        # Add legend
        if color_by in df.columns:
            legend_html = f'''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">{color_by}</p>
            '''
            for val, color in color_map.items():
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">━</span> {val}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))
        
        return {
            "success": True,
            "map_html": m._repr_html_(),
            "roads_count": len(df),
            "title": title
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# List of map tools
MAP_TOOLS = [create_district_map, create_points_map, create_road_map]
