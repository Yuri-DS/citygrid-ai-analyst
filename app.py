"""
CityGrid AI Analyst - Basic SQL Executor
Phase 0.3: Streamlit + Database connection
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# === Configuration ===
DB_PATH = Path(__file__).parent / "data" / "citygrid.db"

# === Page Config ===
st.set_page_config(
    page_title="CityGrid AI Analyst",
    page_icon="🏙️",
    layout="wide"
)


# === Database Connection ===
@st.cache_resource
def get_engine():
    """Create database connection engine."""
    if not DB_PATH.exists():
        st.error(f"Database not found: {DB_PATH}")
        return None
    return create_engine(f"sqlite:///{DB_PATH}")


def execute_query(query: str) -> tuple[pd.DataFrame | None, str | None]:
    """Execute SQL query and return results or error."""
    engine = get_engine()
    if engine is None:
        return None, "Database connection failed"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            return df, None
    except SQLAlchemyError as e:
        return None, str(e)


def get_table_info() -> pd.DataFrame | None:
    """Get list of tables in database."""
    query = """
    SELECT name, type 
    FROM sqlite_master 
    WHERE type='table' 
    ORDER BY name
    """
    df, _ = execute_query(query)
    return df


# === UI ===
st.title("🏙️ CityGrid AI Analyst")
st.caption("Phase 0.3: Basic SQL Executor")

# Sidebar - Database Info
with st.sidebar:
    st.header("📊 Database Info")

    if DB_PATH.exists():
        st.success(f"✅ Connected: {DB_PATH.name}")

        # Show tables
        tables_df = get_table_info()
        if tables_df is not None:
            st.subheader("Tables")
            for _, row in tables_df.iterrows():
                st.code(row['name'])
    else:
        st.error("❌ Database not found")

    st.divider()
    st.caption("CityGrid AI Analyst v0.1")

# Main Area - SQL Executor
st.header("SQL Executor")

# Example queries
example_queries = {
    "Select example...": "",
    "All districts": "SELECT * FROM districts LIMIT 10",
    "District count": "SELECT COUNT(*) as count FROM districts",
    "Sensors by type": """
SELECT sensor_type, COUNT(*) as count 
FROM sensors 
GROUP BY sensor_type 
ORDER BY count DESC
""",
    "Recent requests": """
SELECT category, status, COUNT(*) as count
FROM citizen_requests
GROUP BY category, status
ORDER BY count DESC
LIMIT 10
""",
    "City objects summary": """
SELECT object_type, COUNT(*) as count
FROM city_objects
GROUP BY object_type
ORDER BY count DESC
"""
}

# Query input
selected_example = st.selectbox("📝 Example queries:", list(example_queries.keys()))

default_query = example_queries[selected_example]
query = st.text_area(
    "Enter SQL query:",
    value=default_query,
    height=150,
    placeholder="SELECT * FROM districts LIMIT 10"
)

# Execute button
col1, col2 = st.columns([1, 5])
with col1:
    execute_btn = st.button("▶️ Execute", type="primary", use_container_width=True)

# Results
if execute_btn and query.strip():
    with st.spinner("Executing query..."):
        df, error = execute_query(query)

    if error:
        st.error(f"❌ Error: {error}")
    elif df is not None:
        st.success(f"✅ Returned {len(df)} rows")

        # Show results
        st.dataframe(df, use_container_width=True)

        # Quick stats
        if len(df) > 0:
            with st.expander("📈 Quick Stats"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Rows", len(df))
                col2.metric("Columns", len(df.columns))
                col3.metric("Memory", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")
elif execute_btn:
    st.warning("Please enter a SQL query", icon="⚠️")

# Footer
st.divider()
st.caption("💡 Tip: Use the example queries dropdown to get started")
