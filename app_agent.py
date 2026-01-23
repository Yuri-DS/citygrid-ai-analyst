"""
CityGrid AI Analyst - Main Application
Phase 1: Basic Agent with SQL capabilities + Streaming UI
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
    return create_agent(model_name="qwen2.5:7b", verbose=True)


# === Session State ===
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_initialized" not in st.session_state:
    st.session_state.agent_initialized = False


# === Helper Functions ===

def display_step(step: dict, container):
    """Display a single reasoning step."""
    step_type = step.get("type")

    if step_type == "thinking":
        container.info(f"🧠 **Thinking:** {step.get('content', '')}")

    elif step_type == "tool_call":
        tool_name = step.get("tool_name", "unknown")
        args = step.get("arguments", {})
        container.warning(f"🔧 **Calling tool:** `{tool_name}`")
        if tool_name == "execute_sql" and "query" in args:
            container.code(args["query"], language="sql")
        else:
            container.json(args)

    elif step_type == "tool_result":
        tool_name = step.get("tool_name", "unknown")
        result = step.get("result", "")
        container.success(f"✅ **Result from:** `{tool_name}`")
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict) and "data" in data and data["data"]:
                container.dataframe(pd.DataFrame(data["data"]), use_container_width=True)
            else:
                container.code(str(result)[:500])
        except:
            container.code(str(result)[:500])

    elif step_type == "llm_response":
        content = step.get("content", "")
        if content:
            container.markdown(content)


def run_agent_with_streaming(agent, prompt: str):
    """Run agent and display steps in real-time."""

    # Container for streaming steps
    steps_container = st.container()
    steps_expander = steps_container.expander("🔍 **Live Reasoning Steps**", expanded=True)

    # Placeholder for final answer
    answer_placeholder = st.empty()

    collected_steps = []
    final_answer = ""

    # Get logs from agent (we'll use invoke but display logs progressively)
    # For true streaming we need to modify the agent, but this shows the concept

    with st.spinner(""):
        result = agent.invoke(prompt)

        # Display steps from logs
        logs = result.get("logs", [])

        for log in logs:
            log_type = log.get("type")
            data = log.get("data", {})

            if log_type == "llm_output":
                # LLM thinking/response
                content = data.get("content", "")
                tool_calls = data.get("tool_calls")

                if tool_calls:
                    for tc in tool_calls:
                        step = {
                            "type": "tool_call",
                            "tool_name": tc["name"],
                            "arguments": tc["args"]
                        }
                        collected_steps.append(step)
                        display_step(step, steps_expander)

                if content and not tool_calls:
                    # This is the final answer
                    final_answer = content

            elif log_type == "tool_result":
                step = {
                    "type": "tool_result",
                    "tool_name": data.get("tool_name"),
                    "result": data.get("result")
                }
                collected_steps.append(step)
                display_step(step, steps_expander)

        # Display final answer
        final_answer = result.get("answer", "No answer generated")
        answer_placeholder.markdown(final_answer)

    return {
        "answer": final_answer,
        "steps": collected_steps
    }


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
    st.caption("CityGrid AI Analyst v0.3")

# Main chat area
st.header("💬 Chat")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Show reasoning steps if available (collapsed for history)
        if "steps" in message and message["steps"]:
            with st.expander("🔍 Reasoning Steps"):
                for step in message["steps"]:
                    display_step(step, st)

# Chat input
if prompt := st.chat_input("Ask about city data...", disabled=not st.session_state.agent_initialized):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Get agent response with streaming
    with st.chat_message("assistant"):
        if st.session_state.agent_initialized:
            try:
                agent = init_agent()
                result = run_agent_with_streaming(agent, prompt)

                # Save to history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": result["answer"],
                    "steps": result["steps"]
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
