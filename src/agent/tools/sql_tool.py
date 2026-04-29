"""
SQL Tool for CityGrid AI Agent.

Allows the agent to execute SQL queries against the CityGrid database.
"""

from typing import Any
from langchain_core.tools import tool
import re

from database import get_connection, validate_sql
from database.validator import DEFAULT_LIMIT, ALLOWED_TABLES


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
    # Guardrail: very small LIMIT (1-5) is too small for visualization; use config default
    query = re.sub(r"\bLIMIT\s+(1|2|3|4|5)\b", f"LIMIT {DEFAULT_LIMIT}", query, flags=re.IGNORECASE)
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
    if table_name.lower() not in ALLOWED_TABLES:
        return {
            "success": False,
            "error": f"Unknown table: {table_name}. Allowed: {', '.join(sorted(ALLOWED_TABLES))}",
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
SQL_TOOLS = [execute_sql, get_table_sample]