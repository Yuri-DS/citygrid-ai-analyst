"""
SQL Tool for CityGrid AI Agent.

Allows the agent to execute SQL queries against the CityGrid database.
"""

from typing import Any
from langchain_core.tools import tool

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database import get_connection, validate_sql


# === Schema Description for LLM ===
SCHEMA_DESCRIPTION = """
CityGrid Database Schema:

1. districts - Administrative districts (5-20 records)
   Columns: district_id, name, type, population, area_km2, density, income_level, industrial_coeff, center_lat, center_lon, geometry

2. road_network_nodes - Road network nodes/intersections (100-600 records)
   Columns: node_id, lat, lon, type, is_connected_to_district_center

3. city_objects - City infrastructure objects (500-6000 records)
   Columns: object_id, district_id, object_type, name, lat, lon, install_date, status,
            capacity (for stop/parking), length_m, from_node_id, to_node_id, road_type, 
            max_speed_kmh, lanes_count, direction, condition, start_lat, start_lon, end_lat, end_lon (for road_segment)
   Object types: building, road_segment, streetlight, stop, parking, substation, park
   Road types: highway, arterial, local, alley

4. sensors - IoT sensors (750-9000 records)
   Columns: sensor_id, object_id, sensor_type, unit, is_active, last_calibration, accuracy
   Sensor types: noise_db, pm25, traffic_intensity, temp_c

5. smart_meters - Smart meters for utilities (300-3600 records)
   Columns: meter_id, object_id, utility_type, unit, is_active
   Utility types: electricity_kwh, water_m3, heating_gcal

6. sensor_readings - Sensor readings time series (LARGE TABLE - requires time filter!)
   Columns: reading_id, sensor_id, ts, value, quality_flag, anomaly_score
   Quality flags: ok, missing, suspect

7. meter_readings - Meter readings time series (LARGE TABLE - requires time filter!)
   Columns: reading_id, meter_id, ts, value, is_peak

8. municipal_events - City events (75-1200 records)
   Columns: event_id, district_id, name, event_type, start_ts, end_ts, expected_attendance, lat, lon, impact_radius_km, noise_increase_db, traffic_increase_percent
   Event types: concert, construction, accident, protest, festival, sports_event

9. citizen_requests - Citizen complaints/requests (10k-160k records)
   Columns: request_id, district_id, object_id, category, created_ts, status, resolved_ts, resolution_hours, priority, description
   Categories: noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality
   Statuses: new, in_progress, resolved, rejected
   Priorities: low, medium, high

10. public_transport_trips - Public transport trips (50k-800k records)
    Columns: trip_id, route_no, vehicle_id, stop_object_id, scheduled_ts, actual_ts, delay_minutes, passenger_estimate, weather_condition
"""


@tool
def execute_sql(query: str) -> dict[str, Any]:
    """
    Execute a SQL query against the CityGrid database.

    Args:
        query: SQL SELECT query to execute

    Returns:
        Dictionary with:
        - success: bool
        - data: list of records (use this for visualization tools!)
        - row_count: number of rows
        - columns: list of column names
        - error: error message if failed
    """
    safe_query, validation = validate_sql(query, add_limit=True)

    if not validation.is_valid:
        return {
            "success": False,
            "error": validation.error,
            "data": [],
            "row_count": 0
        }

    conn = get_connection()
    df, error = conn.execute(safe_query, validate=False)

    if error:
        return {
            "success": False,
            "error": error,
            "data": [],
            "row_count": 0
        }

    records = df.to_dict("records")

    return {
        "success": True,
        "data": records,
        "row_count": len(records),
        "columns": list(df.columns),
        "query_executed": safe_query
    }


@tool
def get_schema() -> str:
    """
    Get the database schema description.

    Use this tool to understand what tables and columns are available
    before writing SQL queries.

    Returns:
        String description of all tables and their columns.
    """
    return SCHEMA_DESCRIPTION


@tool
def get_table_sample(table_name: str) -> dict[str, Any]:
    """
    Get sample rows from a specific table.

    Use this tool to see example data and understand the format of values
    in a table before writing complex queries.

    Args:
        table_name: Name of the table to sample

    Returns:
        Dictionary with sample data from the table
    """
    allowed_tables = {
        "districts", "road_network_nodes", "city_objects", "sensors",
        "smart_meters", "sensor_readings", "meter_readings",
        "municipal_events", "citizen_requests", "public_transport_trips"
    }

    if table_name.lower() not in allowed_tables:
        return {
            "success": False,
            "error": f"Unknown table: {table_name}. Allowed: {', '.join(sorted(allowed_tables))}",
            "data": []
        }

    conn = get_connection()
    df = conn.get_table_sample(table_name.lower(), limit=5)

    if df is None:
        return {
            "success": False,
            "error": f"Failed to get sample from {table_name}",
            "data": []
        }

    return {
        "success": True,
        "data": df.to_dict("records"),
        "columns": list(df.columns),
        "table": table_name
    }


# List of all SQL tools
SQL_TOOLS = [execute_sql, get_schema, get_table_sample]