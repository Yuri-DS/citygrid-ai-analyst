"""
RAG Tool for CityGrid AI Agent.

Allows the agent to search documentation for schema info and SQL examples.
"""

from typing import Any
from langchain_core.tools import tool

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rag import get_rag_system


@tool
def search_documentation(query: str) -> dict[str, Any]:
    """
    Search CityGrid documentation for relevant information.
    
    Use this tool to find:
    - Database schema (table names, column names, data types)
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
        results = rag.search_with_scores(query, k=3)
        
        if not results:
            return {
                "success": True,
                "results": [],
                "message": "No relevant documentation found"
            }
        
        # Format results
        formatted_results = []
        for doc, score in results:
            formatted_results.append({
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "relevance_score": round(1 - score, 3)  # Convert distance to similarity
            })
        
        return {
            "success": True,
            "results": formatted_results,
            "result_count": len(formatted_results)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


# List of RAG tools
RAG_TOOLS = [search_documentation]
