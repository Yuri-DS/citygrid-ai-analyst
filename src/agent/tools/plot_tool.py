"""
Plot Tool for CityGrid AI Agent.

Creates interactive Plotly visualizations based on data.
"""

import json
from typing import Any, Union
import plotly.express as px
import pandas as pd
from langchain_core.tools import tool


@tool
def create_chart(
    data: Union[str, list[dict]],
    chart_type: str,
    x_column: str = None,
    y_column: str = None,
    title: str = None,
    color_column: str = None
) -> dict[str, Any]:
    """
    Create an interactive chart from data.

    Args:
        data: Data as JSON string OR list of dicts from SQL query result.
              Pass the "data" field from execute_sql result.
        chart_type: Type of chart - "bar", "line", "pie", "scatter", "histogram"
        x_column: Column name for X axis (or labels for pie chart).
                  Optional - auto-detected from data if not provided.
        y_column: Column name for Y axis (or values for pie chart). Optional for histogram.
                  Optional - auto-detected from data if not provided.
        title: Chart title (optional)
        color_column: Column for color grouping (optional)

    Returns:
        Dictionary with 'success', 'chart_json' (Plotly JSON), and 'chart_type'

    Example:
        After execute_sql returns {"success": true, "data": [...]},
        call: create_chart(data=[...], chart_type="bar", x_column="name", y_column="population")
        For pie charts, columns are auto-detected: create_chart(data=[...], chart_type="pie")
    """
    try:
        # Parse data - accept both string and list
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data

        if not data_list:
            return {
                "success": False,
                "error": "No data provided. Make sure to pass data from execute_sql result."
            }

        df = pd.DataFrame(data_list)

        # Auto-detect columns if not specified
        if not x_column or not y_column:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
            if not x_column:
                x_column = non_numeric_cols[0] if non_numeric_cols else df.columns[0]
            if not y_column and numeric_cols:
                y_column = numeric_cols[0]

        # Validate columns
        if x_column not in df.columns:
            return {
                "success": False,
                "error": f"Column '{x_column}' not found. Available: {list(df.columns)}"
            }

        if y_column and y_column not in df.columns:
            return {
                "success": False,
                "error": f"Column '{y_column}' not found. Available: {list(df.columns)}"
            }

        # Auto-generate title
        if not title:
            if chart_type == "pie":
                title = f"Distribution of {x_column}"
            elif y_column:
                title = f"{y_column.replace('_', ' ').title()} by {x_column.replace('_', ' ').title()}"
            else:
                title = f"{chart_type.title()} Chart"

        # Create chart
        fig = None

        if chart_type == "bar":
            fig = px.bar(
                df, x=x_column, y=y_column, title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
        elif chart_type == "line":
            fig = px.line(
                df, x=x_column, y=y_column, title=title,
                color=color_column if color_column and color_column in df.columns else None,
                markers=True
            )
        elif chart_type == "pie":
            fig = px.pie(df, names=x_column, values=y_column, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(
                df, x=x_column, y=y_column, title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
        elif chart_type == "histogram":
            fig = px.histogram(
                df, x=x_column, title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
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

        return {
            "success": True,
            "chart_json": fig.to_json(),
            "chart_type": chart_type,
            "title": title,
            "rows_visualized": len(df)
        }

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON data: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Chart creation failed: {str(e)}"
        }


@tool
def suggest_chart_type(data: Union[str, list[dict]], question: str = "") -> dict[str, Any]:
    """
    Suggest the best chart type for given data.

    Args:
        data: Data as JSON string or list of dicts from SQL query
        question: Original user question (helps determine intent)

    Returns:
        Dictionary with suggested chart type and reasoning
    """
    try:
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data

        if not data_list:
            return {"success": False, "error": "No data to analyze"}

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


# Export tools
PLOT_TOOLS = [create_chart, suggest_chart_type]