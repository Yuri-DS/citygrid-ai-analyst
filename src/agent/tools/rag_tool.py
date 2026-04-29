"""
RAG Tool for CityGrid AI Agent.

Allows the agent to search documentation for schema info and SQL examples.
Uses multi-query strategy: when table names are detected in the query,
an additional search for table relationships/JOINs is performed automatically.
"""

import re
from typing import Any
from langchain_core.tools import tool

from rag import get_rag_system
from database.connection import get_connection


# --- Table name detection (dynamic, cached) ---

_table_names_cache: set[str] | None = None


def _get_table_names() -> set[str]:
    """Get table names from the database. Cached after first call."""
    global _table_names_cache
    if _table_names_cache is None:
        try:
            conn = get_connection()
            df, err = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                validate=False,
            )
            if df is not None:
                _table_names_cache = {name.lower() for name in df["name"]}
            else:
                _table_names_cache = set()
        except Exception:
            _table_names_cache = set()
    return _table_names_cache


def _detect_tables(query: str) -> list[str]:
    """Detect database table names mentioned in a search query.

    Matches both full table names (e.g. "sensors") and their singular forms
    (e.g. "sensor", "district") so that natural-language queries like
    "sensors in each district" are handled correctly.
    """
    query_lower = query.lower()
    tables = _get_table_names()
    found: list[str] = []
    for table in tables:
        # Exact table name match (word boundary)
        if re.search(r'\b' + re.escape(table) + r'\b', query_lower):
            found.append(table)
            continue
        # Singular form: strip trailing 's' (works for most English plurals)
        if table.endswith('s'):
            singular = table[:-1]
            if singular and re.search(r'\b' + re.escape(singular) + r'\b', query_lower):
                found.append(table)
    return found


def _deduplicate_results(
    main: list[tuple], rel: list[tuple]
) -> list[tuple]:
    """Merge two result lists, removing duplicates by content."""
    seen_content: set[str] = set()
    merged: list[tuple] = []
    for item in main:
        doc = item[0]
        key = doc.page_content.strip()
        if key not in seen_content:
            seen_content.add(key)
            merged.append(item)
    for item in rel:
        doc = item[0]
        key = doc.page_content.strip()
        if key not in seen_content:
            seen_content.add(key)
            merged.append(item)
    return merged


# --- Tool ---

@tool
def search_documentation(query: str) -> dict[str, Any]:
    """
    Search CityGrid documentation for relevant information.
    
    Use this tool to find:
    - Database schema (table names, column names, data types)
    - Table relationships and JOIN patterns
    - SQL query examples
    - Business rules and KPI definitions
    - Sensor specifications and typical values
    
    IMPORTANT: Always use this tool BEFORE writing SQL queries to ensure
    you use correct table and column names.
    
    Args:
        query: Search query describing what information you need
        
    Returns:
        Dictionary with search results containing relevant documentation snippets
        
    Example queries:
        - "schema of districts table columns"
        - "how to calculate population density"
        - "sensor_readings table structure"
        - "example SQL for citizen requests by category"
        - "what columns are in public_transport_trips"
    """
    try:
        rag = get_rag_system()

        # 1) Main search — what the agent explicitly asked for
        main_results = rag.search_with_scores(query, k=3)

        # 2) Auto-detect table names in the query.
        #    If any are found, run an additional search focused on
        #    relationships / JOINs between those tables.  This ensures
        #    the agent always sees how tables connect — even if it only
        #    asked for "schema of sensors table".
        mentioned_tables = _detect_tables(query)
        rel_results: list[tuple] = []
        if mentioned_tables:
            rel_query = f"relationships joins between {' '.join(mentioned_tables)}"
            rel_results = rag.search_with_scores(rel_query, k=2)

        # 3) Merge & deduplicate
        all_results = _deduplicate_results(main_results, rel_results)

        if not all_results:
            return {
                "success": True,
                "results": [],
                "message": "No relevant documentation found",
            }

        # Format results
        formatted_results = []
        for doc, score in all_results:
            formatted_results.append({
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "relevance_score": round(1 - score, 3),
            })

        return {
            "success": True,
            "results": formatted_results,
            "result_count": len(formatted_results),
            "tables_detected": mentioned_tables if mentioned_tables else None,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
        }


# List of RAG tools
RAG_TOOLS = [search_documentation]
