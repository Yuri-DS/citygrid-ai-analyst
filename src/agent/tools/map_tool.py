"""
Universal Map Tool for CityGrid AI Agent.

Single flexible function for any map visualization.
The agent decides what data to query and how to display it.
"""

from typing import Any, Union
from langchain_core.tools import tool
import json
import pandas as pd

try:
    import folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False


@tool
def create_map(
    data: Union[str, list[dict]],
    lat_column: str = "lat",
    lon_column: str = "lon",
    color_column: str = None,
    size_column: str = None,
    label_column: str = None,
    map_type: str = "points",
    start_lat_column: str = "start_lat",
    start_lon_column: str = "start_lon",
    end_lat_column: str = "end_lat",
    end_lon_column: str = "end_lon",
    title: str = "Map"
) -> dict[str, Any]:
    """
    Create an interactive map from data.

    This is a universal map tool. You decide:
    - What data to query (via execute_sql)
    - Which columns contain coordinates
    - How to color/size/label the markers
    - What type of visualization (points or lines)

    Args:
        data: List of dictionaries with data to visualize.
              Must contain latitude and longitude columns.
        lat_column: Column name for latitude. Default "lat".
                   For line maps, this is start latitude - also need end_lat.
        lon_column: Column name for longitude. Default "lon".
                   For line maps, this is start longitude - also need end_lon.
        color_column: Optional column to color markers by (categorical).
        size_column: Optional column to size markers by (numeric).
        label_column: Optional column for marker labels/popups.
        map_type: "points" for markers, "lines" for connected lines.
                 For lines, configure start/end coordinate columns below.
        start_lat_column: Start latitude column name for line maps.
        start_lon_column: Start longitude column name for line maps.
        end_lat_column: End latitude column name for line maps.
        end_lon_column: End longitude column name for line maps.
        title: Map title.

    Returns:
        Dictionary with 'success', 'map_html', 'items_count', 'title'.

    Examples:
        # Points map (sensors, buildings, events, etc.)
        create_map(data, lat_column="lat", lon_column="lon",
                   color_column="sensor_type", label_column="name")

        # District centers
        create_map(data, lat_column="center_lat", lon_column="center_lon",
                   size_column="population", label_column="name")

        # Road network (lines)
        create_map(data, start_lat_column="start_lat", start_lon_column="start_lon",
                   end_lat_column="end_lat", end_lon_column="end_lon",
                   map_type="lines", color_column="condition")
    """
    if not FOLIUM_AVAILABLE:
        return {"success": False, "error": "folium library not installed"}

    try:
        # Parse data
        if isinstance(data, str):
            if not data.strip():
                return {"success": False, "error": "Empty data string. Query data with execute_sql first."}
            data_list = json.loads(data)
        else:
            data_list = data

        if not data_list:
            return {"success": False, "error": "No data provided. Query data with execute_sql first."}

        df = pd.DataFrame(data_list)

        # Validate columns exist
        available_columns = list(df.columns)

        if map_type == "lines":
            required = [start_lat_column, start_lon_column, end_lat_column, end_lon_column]
            missing = [c for c in required if c not in df.columns]
            if missing:
                return {
                    "success": False,
                    "error": f"For lines map, need columns: {required}. Available: {available_columns}"
                }
        else:
            if lat_column not in df.columns:
                return {
                    "success": False,
                    "error": f"Latitude column '{lat_column}' not found. Available: {available_columns}"
                }
            if lon_column not in df.columns:
                return {
                    "success": False,
                    "error": f"Longitude column '{lon_column}' not found. Available: {available_columns}"
                }

        # Calculate map center
        if map_type == "lines":
            center_lat = df[[start_lat_column, end_lat_column]].mean().mean()
            center_lon = df[[start_lon_column, end_lon_column]].mean().mean()
        else:
            center_lat = df[lat_column].mean()
            center_lon = df[lon_column].mean()

        # Create map with dark style
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles='CartoDB dark_matter'
        )

        # Color mapping
        colors = ['blue', 'red', 'green', 'orange', 'purple', 'darkred',
                  'darkblue', 'darkgreen', 'cadetblue', 'pink']
        color_map = {}

        if color_column and color_column in df.columns:
            unique_values = df[color_column].dropna().unique()
            for i, val in enumerate(unique_values):
                color_map[val] = colors[i % len(colors)]

        if map_type == "lines":
            # Draw lines
            for _, row in df.iterrows():
                start = [row[start_lat_column], row[start_lon_column]]
                end = [row[end_lat_column], row[end_lon_column]]

                # Determine color
                if color_column and color_column in df.columns and pd.notna(row.get(color_column)):
                    color = color_map.get(row[color_column], 'blue')
                else:
                    color = 'blue'

                # Build popup
                popup_parts = []
                if label_column and label_column in df.columns and pd.notna(row.get(label_column)):
                    popup_parts.append(f"<b>{row[label_column]}</b>")
                if color_column and color_column in df.columns and pd.notna(row.get(color_column)):
                    popup_parts.append(f"{color_column}: {row[color_column]}")
                popup_text = "<br>".join(popup_parts) if popup_parts else None

                folium.PolyLine(
                    [start, end],
                    color=color,
                    weight=3,
                    opacity=0.8,
                    popup=popup_text
                ).add_to(m)
        else:
            # Draw points
            for _, row in df.iterrows():
                lat = row[lat_column]
                lon = row[lon_column]

                if pd.isna(lat) or pd.isna(lon):
                    continue

                # Determine color
                if color_column and color_column in df.columns and pd.notna(row.get(color_column)):
                    color = color_map.get(row[color_column], 'blue')
                else:
                    color = 'blue'

                # Determine size
                radius = 8
                if size_column and size_column in df.columns and pd.notna(row.get(size_column)):
                    val = row[size_column]
                    if isinstance(val, (int, float)) and val > 0:
                        # Scale: min 5, max 25
                        min_val = df[size_column].min()
                        max_val = df[size_column].max()
                        if max_val > min_val:
                            radius = 5 + 20 * (val - min_val) / (max_val - min_val)
                        else:
                            radius = 12

                # Build popup
                popup_parts = []
                if label_column and label_column in df.columns and pd.notna(row.get(label_column)):
                    popup_parts.append(f"<b>{row[label_column]}</b>")
                if color_column and color_column in df.columns and pd.notna(row.get(color_column)):
                    popup_parts.append(f"{color_column}: {row[color_column]}")
                if size_column and size_column in df.columns and pd.notna(row.get(size_column)):
                    popup_parts.append(f"{size_column}: {row[size_column]}")
                popup_text = "<br>".join(popup_parts) if popup_parts else None

                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=color,
                    fill=True,
                    fillColor=color,
                    fillOpacity=0.7,
                    popup=popup_text
                ).add_to(m)

        # Add legend if color column used (dark style)
        if color_column and color_map:
            legend_html = f'''
            <div style="position: fixed; bottom: 30px; right: 30px; z-index: 1000;
                        background: rgba(0,0,0,0.8); padding: 10px; border-radius: 5px;
                        border: 1px solid #444;">
                <p style="color: white; margin: 0 0 5px 0; font-weight: bold;">{color_column}</p>
            '''
            for val, color in color_map.items():
                legend_html += f'<p style="color: white; margin: 2px 0;"><span style="color: {color};">●</span> {val}</p>'
            legend_html += '</div>'
            m.get_root().html.add_child(folium.Element(legend_html))

        return {
            "success": True,
            "map_html": m._repr_html_(),
            "items_count": len(df),
            "title": title,
            "map_type": map_type
        }

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON data: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Export for tools registry
MAP_TOOLS = [create_map]