"""Agent tools for CityGrid AI Analyst."""

from .sql_tool import execute_sql, get_schema, get_table_sample, SQL_TOOLS
from .rag_tool import search_documentation, RAG_TOOLS
from .plot_tool import create_chart, suggest_chart_type, PLOT_TOOLS
from .map_tool import create_district_map, create_points_map, create_road_map, MAP_TOOLS

# All tools combined
ALL_TOOLS = SQL_TOOLS + RAG_TOOLS + PLOT_TOOLS + MAP_TOOLS

__all__ = [
    # SQL
    "execute_sql",
    "get_schema",
    "get_table_sample",
    "SQL_TOOLS",
    # RAG
    "search_documentation",
    "RAG_TOOLS",
    # Plot
    "create_chart",
    "suggest_chart_type",
    "PLOT_TOOLS",
    # Map
    "create_district_map",
    "create_points_map",
    "create_road_map",
    "MAP_TOOLS",
    # All
    "ALL_TOOLS",
]