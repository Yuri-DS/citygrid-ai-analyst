"""
Plot Tool for CityGrid AI Agent.

Creates interactive Plotly visualizations based on data.
"""

import json
from typing import Any, Optional, Union
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from langchain_core.tools import tool

# Глобальное хранилище последнего SQL результата
_last_sql_data: Optional[list[dict]] = None

def set_last_sql_data(data: list[dict]) -> None:
    """Store last SQL result for visualization tools."""
    global _last_sql_data
    _last_sql_data = data

def get_last_sql_data() -> Optional[list[dict]]:
    """Get last SQL result."""
    return _last_sql_data


@tool
def create_chart(
        chart_type: str,
        x_column: str,
        y_column: str = None,
        title: str = None,
        color_column: str = None
) -> dict[str, Any]:
    """
    Create an interactive chart from the LAST SQL query result.

    IMPORTANT: You MUST call execute_sql FIRST to get data, then call this tool.
    This tool automatically uses data from the previous SQL query.

    Args:
        chart_type: Type of chart - "bar", "line", "pie", "scatter", "histogram"
        x_column: Column name for X axis (or labels for pie chart)
        y_column: Column name for Y axis (or values for pie chart). Optional for histogram.
        title: Chart title (optional)
        color_column: Column for color grouping (optional)

    Returns:
        Dictionary with 'success', 'chart_json' (Plotly JSON), and 'chart_type'
    """
    try:
        # Получаем данные из последнего SQL запроса
        data_list = get_last_sql_data()

        if not data_list:
            return {
                "success": False,
                "error": "No data available. Execute a SQL query first using execute_sql tool."
            }

        df = pd.DataFrame(data_list)

        # Validate columns
        if x_column not in df.columns:
            return {
                "success": False,
                "error": f"Column '{x_column}' not found. Available columns: {list(df.columns)}"
            }

        if y_column and y_column not in df.columns:
            return {
                "success": False,
                "error": f"Column '{y_column}' not found. Available columns: {list(df.columns)}"
            }

        # Auto-generate title
        if not title:
            if chart_type == "pie":
                title = f"Distribution of {x_column}"
            elif y_column:
                title = f"{y_column} by {x_column}"
            else:
                title = f"{chart_type.title()} Chart"

        # Create chart
        fig = None

        if chart_type == "bar":
            fig = px.bar(df, x=x_column, y=y_column, title=title, color=color_column)
        elif chart_type == "line":
            fig = px.line(df, x=x_column, y=y_column, title=title, color=color_column, markers=True)
        elif chart_type == "pie":
            fig = px.pie(df, names=x_column, values=y_column, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_column, y=y_column, title=title, color=color_column)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x_column, title=title, color=color_column)
        else:
            return {
                "success": False,
                "error": f"Unknown chart type: {chart_type}. Use: bar, line, pie, scatter, histogram"
            }

        # Styling
        fig.update_layout(
            template="plotly_white",
            font=dict(size=12),
            title_font=dict(size=16),
            showlegend=bool(color_column)
        )

        chart_json = fig.to_json()

        return {
            "success": True,
            "chart_json": chart_json,
            "chart_type": chart_type,
            "title": title,
            "rows_visualized": len(df)
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Chart creation failed: {str(e)}"
        }


@tool
def suggest_chart_type(question: str = "") -> dict[str, Any]:
    """
    Suggest the best chart type for the last SQL result.

    Args:
        question: Original user question (helps determine intent)

    Returns:
        Dictionary with suggested chart type and reasoning
    """
    try:
        data_list = get_last_sql_data()

        if not data_list:
            return {"success": False, "error": "No data available. Execute SQL first."}

        df = pd.DataFrame(data_list)
        columns = list(df.columns)

        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
        time_cols = [c for c in columns if any(t in c.lower() for t in ['date', 'time', 'ts', 'year', 'month'])]

        suggestion = {
            "success": True,
            "columns": columns,
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "row_count": len(df)
        }

        q = question.lower()

        if "distribution" in q or "breakdown" in q:
            suggestion["suggested_type"] = "pie"
            suggestion["reason"] = "Pie chart shows distribution well"
        elif "trend" in q or "over time" in q or time_cols:
            suggestion["suggested_type"] = "line"
            suggestion["reason"] = "Line chart best for trends"
            if time_cols:
                suggestion["suggested_x"] = time_cols[0]
        elif "compare" in q or "top" in q or "ranking" in q:
            suggestion["suggested_type"] = "bar"
            suggestion["reason"] = "Bar chart best for comparisons"
        elif len(numeric_cols) >= 2:
            suggestion["suggested_type"] = "scatter"
            suggestion["reason"] = "Scatter plot shows correlation"
        else:
            suggestion["suggested_type"] = "bar"
            suggestion["reason"] = "Default for general data"

        if categorical_cols and numeric_cols:
            suggestion["suggested_x"] = categorical_cols[0]
            suggestion["suggested_y"] = numeric_cols[0]

        return suggestion

    except Exception as e:
        return {"success": False, "error": str(e)}


PLOT_TOOLS = [create_chart, suggest_chart_type]


# List of plot tools
PLOT_TOOLS = [create_chart, suggest_chart_type]
