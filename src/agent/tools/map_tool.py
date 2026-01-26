"""
Map Tool for CityGrid AI Agent.

Creates interactive Folium maps for geographic visualization.
"""

import json
from typing import Any, Union, Optional
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
    data: Union[str, list[dict]],
    value_column: str = "population",
    title: str = "Districts Map"
) -> dict[str, Any]:
    """
    Create an interactive map showing city districts.

    Args:
        data: District data with 'center_lat', 'center_lon', 'name' columns.
              Can be JSON string or list of dicts.
        value_column: Column for circle size (default: "population").
                      If column doesn't exist, uniform size is used.
        title: Map title

    Returns:
        Dictionary with 'success', 'map_html' (HTML string)

    Example:
        1. execute_sql("SELECT name, center_lat, center_lon, population, type FROM districts")
        2. create_district_map(data=<result>, value_column="population", title="City Districts")
    """
    try:
        # Parse data
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

        # Calculate sizes if value_column exists
        if value_column and value_column in df.columns:
            min_val = df[value_column].min()
            max_val = df[value_column].max()
            if max_val > min_val:
                df["_radius"] = 10 + 20 * (df[value_column] - min_val) / (max_val - min_val)
            else:
                df["_radius"] = 15
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
            unique_types = df["type"].unique()
            legend_html = '''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">District Types</p>
            '''
            for dtype in unique_types:
                color = DISTRICT_TYPE_COLORS.get(dtype, "#3498db")
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">●</span> {dtype}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))

        return {
            "success": True,
            "map_html": m._repr_html_(),
            "districts_count": len(df),
            "title": title
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON data: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def create_points_map(
    data: Union[str, list[dict]],
    lat_column: str = "lat",
    lon_column: str = "lon",
    label_column: str = "",
    color_column: str = "",
    title: str = "Points Map"
) -> dict[str, Any]:
    """
    Create a map with point markers (sensors, events, requests, etc.).

    Args:
        data: Location data as JSON string or list of dicts
        lat_column: Name of latitude column (default: "lat")
        lon_column: Name of longitude column (default: "lon")
        label_column: Column for marker labels (optional, use "" if not needed)
        color_column: Column for color grouping (optional, e.g., "sensor_type")
        title: Map title

    Returns:
        Dictionary with 'success', 'map_html'
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

        # Calculate map center
        center_lat = df[lat_column].mean()
        center_lon = df[lon_column].mean()

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
        marker_group = MarkerCluster() if len(df) > 50 else m

        # Build color map
        color_map = {}
        if color_column and color_column in df.columns:
            unique_vals = df[color_column].unique()
            colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#34495e"]
            for i, val in enumerate(unique_vals):
                color_map[val] = colors[i % len(colors)]

        # Add markers
        for _, row in df.iterrows():
            lat, lon = row[lat_column], row[lon_column]

            # Determine color
            if color_column and color_column in df.columns:
                color = color_map.get(row[color_column], "#3498db")
            else:
                color = "#3498db"

            # Build popup
            if label_column and label_column in df.columns:
                popup_text = str(row[label_column])
            else:
                popup_text = f"({lat:.4f}, {lon:.4f})"

            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                popup=popup_text
            ).add_to(marker_group if isinstance(marker_group, MarkerCluster) else m)

        if isinstance(marker_group, MarkerCluster):
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

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON data: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def create_road_map(
    data: Union[str, list[dict]],
    color_by: str = "condition",
    title: str = "Road Network"
) -> dict[str, Any]:
    """
    Create a map showing road segments.

    Args:
        data: Road data with 'start_lat', 'start_lon', 'end_lat', 'end_lon' columns.
        color_by: Column for coloring - "condition" or "road_type" (default: "condition")
        title: Map title

    Returns:
        Dictionary with 'success', 'map_html'
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

        # Calculate map center
        center_lat = (df["start_lat"].mean() + df["end_lat"].mean()) / 2
        center_lon = (df["start_lon"].mean() + df["end_lon"].mean()) / 2

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

        # Determine color scheme
        if color_by == "condition" and "condition" in df.columns:
            color_map = CONDITION_COLORS
        elif color_by == "road_type" and "road_type" in df.columns:
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

            # Line weight based on road type
            weight = 3
            if "road_type" in df.columns:
                road_type = row.get("road_type", "local")
                weight = {"highway": 5, "arterial": 4, "local": 3, "alley": 2}.get(road_type, 3)

            # Popup
            popup_lines = []
            if "name" in df.columns:
                popup_lines.append(f"<b>{row['name']}</b>")
            if "road_type" in df.columns:
                popup_lines.append(f"Type: {row['road_type']}")
            if "condition" in df.columns:
                popup_lines.append(f"Condition: {row['condition']}")
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
        if color_by in df.columns and color_map:
            legend_html = f'''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">{color_by}</p>
            '''
            for val in df[color_by].unique():
                color = color_map.get(val, "#3498db")
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">━</span> {val}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))

        return {
            "success": True,
            "map_html": m._repr_html_(),
            "roads_count": len(df),
            "title": title
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON data: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# List of map tools
MAP_TOOLS = [create_district_map, create_points_map, create_road_map]