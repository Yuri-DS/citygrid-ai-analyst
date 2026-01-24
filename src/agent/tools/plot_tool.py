"""
Plot Tool for CityGrid AI Agent.

Creates interactive Plotly visualizations based on data.
"""

import json
from typing import Any
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from langchain_core.tools import tool


@tool
def create_chart(
    data: str,
    chart_type: str,
    x_column: str,
    y_column: str = None,
    title: str = None,
    color_column: str = None
) -> dict[str, Any]:
    """
    Create an interactive chart from data.
    
    Use this tool AFTER getting data from execute_sql to visualize results.
    
    Args:
        data: JSON string of data (list of dicts) from SQL query result
        chart_type: Type of chart - "bar", "line", "pie", "scatter", "histogram"
        x_column: Column name for X axis (or labels for pie chart)
        y_column: Column name for Y axis (or values for pie chart). Optional for histogram.
        title: Chart title (optional)
        color_column: Column for color grouping (optional)
    
    Returns:
        Dictionary with 'success', 'chart_json' (Plotly JSON), and 'chart_type'
    
    Examples:
        - Bar chart of districts by population:
          create_chart(data, "bar", "name", "population", "Districts by Population")
        
        - Pie chart of sensor types:
          create_chart(data, "pie", "sensor_type", "count", "Sensor Distribution")
        
        - Line chart of values over time:
          create_chart(data, "line", "date", "value", "Trend Over Time")
    """
    try:
        # Parse data
        if isinstance(data, str):
            data_list = json.loads(data)
        else:
            data_list = data
        
        if not data_list:
            return {
                "success": False,
                "error": "No data provided for visualization"
            }
        
        df = pd.DataFrame(data_list)
        
        # Validate columns exist
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
        
        # Generate title if not provided
        if not title:
            if chart_type == "pie":
                title = f"Distribution of {x_column}"
            elif y_column:
                title = f"{y_column} by {x_column}"
            else:
                title = f"{chart_type.title()} Chart"
        
        # Create chart based on type
        fig = None
        
        if chart_type == "bar":
            fig = px.bar(
                df, 
                x=x_column, 
                y=y_column, 
                title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
        
        elif chart_type == "line":
            fig = px.line(
                df, 
                x=x_column, 
                y=y_column, 
                title=title,
                color=color_column if color_column and color_column in df.columns else None,
                markers=True
            )
        
        elif chart_type == "pie":
            fig = px.pie(
                df, 
                names=x_column, 
                values=y_column, 
                title=title
            )
        
        elif chart_type == "scatter":
            fig = px.scatter(
                df, 
                x=x_column, 
                y=y_column, 
                title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
        
        elif chart_type == "histogram":
            fig = px.histogram(
                df, 
                x=x_column, 
                title=title,
                color=color_column if color_column and color_column in df.columns else None
            )
        
        else:
            return {
                "success": False,
                "error": f"Unknown chart type: {chart_type}. Use: bar, line, pie, scatter, histogram"
            }
        
        # Update layout for better appearance
        fig.update_layout(
            template="plotly_white",
            font=dict(size=12),
            title_font=dict(size=16),
            showlegend=True if color_column else False
        )
        
        # Convert to JSON for frontend
        chart_json = fig.to_json()
        
        return {
            "success": True,
            "chart_json": chart_json,
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
def suggest_chart_type(data: str, question: str = "") -> dict[str, Any]:
    """
    Suggest the best chart type for given data.
    
    Use this tool if unsure which chart type to use.
    
    Args:
        data: JSON string of data from SQL query
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
        num_rows = len(df)
        
        # Analyze data types
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
        
        # Check for time-related columns
        time_cols = [c for c in columns if any(t in c.lower() for t in ['date', 'time', 'ts', 'year', 'month'])]
        
        suggestion = {
            "success": True,
            "columns": columns,
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "row_count": num_rows
        }
        
        # Logic for suggestion
        question_lower = question.lower()
        
        if "distribution" in question_lower or "breakdown" in question_lower:
            suggestion["suggested_type"] = "pie"
            suggestion["reason"] = "Pie chart shows distribution/breakdown well"
        
        elif "trend" in question_lower or "over time" in question_lower or time_cols:
            suggestion["suggested_type"] = "line"
            suggestion["reason"] = "Line chart is best for trends over time"
            if time_cols:
                suggestion["suggested_x"] = time_cols[0]
        
        elif "compare" in question_lower or "top" in question_lower or "ranking" in question_lower:
            suggestion["suggested_type"] = "bar"
            suggestion["reason"] = "Bar chart is best for comparisons"
        
        elif len(numeric_cols) >= 2:
            suggestion["suggested_type"] = "scatter"
            suggestion["reason"] = "Scatter plot shows relationship between two numeric variables"
            suggestion["suggested_x"] = numeric_cols[0]
            suggestion["suggested_y"] = numeric_cols[1]
        
        elif len(categorical_cols) >= 1 and len(numeric_cols) >= 1:
            if num_rows <= 10:
                suggestion["suggested_type"] = "pie"
                suggestion["reason"] = "Small categorical dataset - pie chart works well"
            else:
                suggestion["suggested_type"] = "bar"
                suggestion["reason"] = "Categorical data with numeric values - bar chart recommended"
            suggestion["suggested_x"] = categorical_cols[0]
            suggestion["suggested_y"] = numeric_cols[0]
        
        else:
            suggestion["suggested_type"] = "bar"
            suggestion["reason"] = "Default recommendation for general data"
        
        return suggestion
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Analysis failed: {str(e)}"
        }


# List of plot tools
PLOT_TOOLS = [create_chart, suggest_chart_type]
