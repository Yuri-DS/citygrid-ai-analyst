"""
CityGrid AI Agent Tools.

Universal tools for data analysis - agent decides how to use them.
"""

from .sql_tool import execute_sql, get_table_sample, SQL_TOOLS
from .plot_tool import create_chart, PLOT_TOOLS
from .map_tool import create_map, MAP_TOOLS
from .rag_tool import search_documentation, RAG_TOOLS
from .anomaly_tool import detect_anomalies, ANOMALY_TOOLS

# All tools available to the agent
ALL_TOOLS = SQL_TOOLS + PLOT_TOOLS + MAP_TOOLS + RAG_TOOLS + ANOMALY_TOOLS

__all__ = [
    "execute_sql",
    "get_table_sample",
    "create_chart",
    "create_map",
    "search_documentation",
    "detect_anomalies",
    "ALL_TOOLS",
    "SQL_TOOLS",
    "PLOT_TOOLS",
    "MAP_TOOLS",
    "RAG_TOOLS",
    "ANOMALY_TOOLS",
]
