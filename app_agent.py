"""
CityGrid AI Analyst - Main Application
Phase 1: Basic Agent with SQL capabilities
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import json

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database import get_connection, validate_sql
from agent import create_agent

# === Configuration ===
DB_PATH = Path(__file__).parent / "data" / "citygrid.db"

# === Page Config ===
st.set_page_config(
    page_title="CityGrid AI Analyst",
    page_icon="🏙️",
    layout="wide"
)

# === Initialize ===

@st.cache_resource
def init_database():
    """Initialize database connection."""
    return get_connection(DB_PATH)

@st.cache_resource
def init_agent():
    """Initialize the AI agent."""
    return create_agent(model_name="llama3.1:8b")


# === Session State ===
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_initialized" not in st.session_state:
    st.session_state.agent_initialized = False


# === UI ===

st.title("🏙️ CityGrid AI Analyst")
st.caption("AI-powered urban data analysis")

# Sidebar
with st.sidebar:
    st.header("📊 Database")
    
    # Check DB connection
    try:
        db = init_database()
        st.success("✅ Database connected")
        
        # Show tables
        with st.expander("📋 Tables"):
            schema = db.get_schema_info()
            for table_name in sorted(schema.keys()):
                st.code(table_name)
    except Exception as e:
        st.error(f"❌ DB Error: {e}")
    
    st.divider()
    
    # Agent status
    st.header("🤖 Agent")
    try:
        agent = init_agent()
        st.success("✅ Agent ready")
        st.caption(f"Model: llama3.1:8b")
        st.session_state.agent_initialized = True
    except Exception as e:
        st.error(f"❌ Agent Error: {e}")
        st.caption("Make sure Ollama is running")
    
    st.divider()
    
    # Clear chat button
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.caption("CityGrid AI Analyst v0.2")

# Main chat area
st.header("💬 Chat")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # Show reasoning steps if available
        if "steps" in message and message["steps"]:
            with st.expander("🔍 Reasoning Steps"):
                for i, step in enumerate(message["steps"]):
                    if step["type"] == "tool_result":
                        st.markdown(f"**Tool: {step['tool']}**")
                        st.code(step["content"][:1000])
                    elif step["type"] == "assistant" and "tool_calls" in step:
                        for tc in step["tool_calls"]:
                            st.markdown(f"🔧 Calling `{tc['name']}`")
                            st.json(tc["args"])

# Chat input
if prompt := st.chat_input("Ask about city data...", disabled=not st.session_state.agent_initialized):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Get agent response
    with st.chat_message("assistant"):
        if st.session_state.agent_initialized:
            with st.spinner("Thinking..."):
                try:
                    agent = init_agent()
                    result = agent.invoke(prompt)
                    
                    answer = result["answer"]
                    steps = result["steps"]
                    
                    st.markdown(answer)
                    
                    # Show reasoning
                    if steps:
                        with st.expander("🔍 Reasoning Steps"):
                            for step in steps:
                                if step["type"] == "tool_result":
                                    st.markdown(f"**Tool: {step['tool']}**")
                                    # Try to parse as JSON for better display
                                    try:
                                        data = json.loads(step["content"])
                                        if "data" in data and data["data"]:
                                            st.dataframe(pd.DataFrame(data["data"]))
                                        else:
                                            st.code(step["content"][:1000])
                                    except:
                                        st.code(step["content"][:1000])
                                elif step["type"] == "assistant" and "tool_calls" in step:
                                    for tc in step["tool_calls"]:
                                        st.markdown(f"🔧 Calling `{tc['name']}`")
                                        if tc["name"] == "execute_sql" and "query" in tc["args"]:
                                            st.code(tc["args"]["query"], language="sql")
                                        else:
                                            st.json(tc["args"])
                    
                    # Save to history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "steps": steps
                    })
                    
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
        else:
            st.warning("Agent not initialized. Check Ollama connection.")

# Example questions
if not st.session_state.messages:
    st.divider()
    st.subheader("💡 Example Questions")
    
    examples = [
        "How many districts are in the city?",
        "Show me the top 5 districts by population",
        "What types of sensors are available?",
        "How many citizen requests are there by category?",
        "What is the average population density across districts?",
    ]
    
    cols = st.columns(2)
    for i, example in enumerate(examples):
        with cols[i % 2]:
            if st.button(example, key=f"example_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": example})
                st.rerun()
