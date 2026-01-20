"""
SQL Tool for CityGrid AI Agent.

Allows the agent to execute SQL queries against the CityGrid database.
"""

from typing import Any
from langchain_core.tools import tool
import pandas as pd

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database import get_connection, validate_sql, safe_sql


# === Schema Description for LLM ===
SCHEMA_DESCRIPTION = """
CityGrid Database Schema:

1. districts - Administrative districts (10 records)
   Columns: id, name, district_type, population, area_km2, density, avg_income_level, center_lat, center_lon, geometry

2. road_network_nodes - Road network nodes/intersections (250 records)
   Columns: id, node_type, lat, lon, district_id

3. city_objects - City infrastructure objects (2000 records)
   Columns: id, object_type, name, district_id, lat, lon, status, 
            road_type, max_speed, lanes_count, condition (for road_segment type)
   Object types: building, road_segment, streetlight, stop, parking, substation, park

4. sensors - IoT sensors (3000 records)
   Columns: id, sensor_type, object_id, install_date, is_active
   Sensor types: noise_db, pm25, traffic_intensity, temp_c

5. smart_meters - Smart meters for utilities (1200 records)
   Columns: id, meter_type, object_id, install_date, is_active
   Meter types: electricity_kwh, water_m3, heating_gcal

6. sensor_readings - Sensor readings time series (LARGE TABLE - requires time filter!)
   Columns: id, sensor_id, ts, value, quality_flag, anomaly_score
   Quality flags: ok, missing, suspect

7. meter_readings - Meter readings time series (LARGE TABLE - requires time filter!)
   Columns: id, meter_id, ts, value, is_peak

8. municipal_events - City events (300 records)
   Columns: id, event_type, name, district_id, start_ts, end_ts, 
            expected_attendance, impact_radius_km, noise_increase_db, traffic_increase_percent
   Event types: concert, construction, accident, protest, festival, sports_event

9. citizen_requests - Citizen complaints/requests (40000 records)
   Columns: id, category, district_id, created_ts, status, resolution_hours, description, lat, lon
   Categories: noise_complaint, pothole, broken_streetlight, water_leak, heating_issue, parking_issue, air_quality
   Statuses: new, in_progress, resolved, rejected

10. public_transport_trips - Public transport trips (200000 records)
    Columns: id, route_no, vehicle_id, stop_object_id, scheduled_ts, actual_ts, 
             delay_minutes, passenger_estimate, weather_condition
"""


@tool
def execute_sql(query: str) -> dict[str, Any]:
    """
    Execute a SQL query against the CityGrid database.
    
    Use this tool to retrieve data from the database. Only SELECT queries are allowed.
    For large tables (sensor_readings, meter_readings), you MUST include a time filter.
    
    Args:
        query: SQL SELECT query to execute
        
    Returns:
        Dictionary with 'success', 'data' (list of records), 'row_count', and optionally 'error'
    
    Example queries:
        - "SELECT * FROM districts LIMIT 10"
        - "SELECT sensor_type, COUNT(*) FROM sensors GROUP BY sensor_type"
        - "SELECT * FROM sensor_readings WHERE ts >= '2024-01-01' AND ts < '2024-01-02' LIMIT 100"
    """
    # Validate and add limit
    safe_query, validation = safe_sql(query, add_limit=True)
    
    if not validation.is_valid:
        return {
            "success": False,
            "error": validation.error,
            "data": [],
            "row_count": 0
        }
    
    # Execute query
    conn = get_connection()
    df, error = conn.execute(safe_query, validate=False)  # Already validated
    
    if error:
        return {
            "success": False,
            "error": error,
            "data": [],
            "row_count": 0
        }
    
    # Convert to records
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
    # Validate table name
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
