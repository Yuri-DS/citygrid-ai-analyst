"""
CityGrid AI Analyst - Main Application
Phase 2: RAG + Model Selection + Fixes
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys
import json
import requests

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database import get_connection, validate_sql
from agent import create_agent

# === Configuration ===
DB_PATH = Path(__file__).parent / "data" / "citygrid.db"
OLLAMA_BASE_URL = "http://localhost:11434"

# Available models for selection (ordered by recommendation)
AVAILABLE_MODELS = {
    "qwen2.5:7b": "Qwen 2.5 7B - Best for tool calling ⭐",
    "qwen2.5:14b": "Qwen 2.5 14B - Most capable, needs 10GB+ RAM",
    "llama3.1:8b": "Llama 3.1 8B - Good general model",
    "mistral": "Mistral 7B - Fast and capable",
    "llama3.2:3b": "Llama 3.2 3B - Lightweight, less accurate",
}

# === Page Config ===
st.set_page_config(
    page_title="CityGrid AI Analyst",
    page_icon="🏙️",
    layout="wide"
)

# === Helper Functions ===

def check_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def get_available_ollama_models() -> list[str]:
    """Get list of models available in Ollama."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
    except:
        pass
    return []


def is_model_available(model_name: str) -> bool:
    """Check if specific model is available in Ollama."""
    available = get_available_ollama_models()
    # Check exact match or match without tag
    for m in available:
        if m == model_name or m.startswith(model_name + ":") or model_name.startswith(m.split(":")[0]):
            return True
    # Also check if model_name matches base name
    base_name = model_name.split(":")[0]
    for m in available:
        if m.split(":")[0] == base_name:
            return True
    return False


@st.cache_resource
def init_database():
    """Initialize database connection."""
    return get_connection(DB_PATH)


def get_agent(model_name: str):
    """Get or create agent for specific model."""
    cache_key = f"agent_{model_name}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = create_agent(model_name=model_name, verbose=True)
    return st.session_state[cache_key]


# === Session State ===
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_initialized" not in st.session_state:
    st.session_state.agent_initialized = False

if "selected_model" not in st.session_state:
    st.session_state.selected_model = list(AVAILABLE_MODELS.keys())[0]


# === Display Functions ===

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


def run_agent_with_streaming(agent, prompt: str, container):
    """Run agent and display steps in real-time (reliable chat rendering)."""

    collected_steps = []

    with container:
        with st.spinner("Thinking..."):
            result = agent.invoke(prompt)

        # --- Robust final answer extraction ---
        if isinstance(result, dict):
            final_answer = (
                result.get("answer")
                or result.get("output")
                or result.get("final_answer")
                or result.get("content")
                or "No answer generated"
            )
            logs = result.get("logs") or []
        else:
            final_answer = str(result)
            logs = []

        # --- Steps (optional) ---
        with st.expander("🔍 **Reasoning Steps**", expanded=False):
            for log in logs:
                # на случай если logs внезапно строками
                if not isinstance(log, dict):
                    st.code(str(log))
                    continue

                log_type = log.get("type")
                data = log.get("data", {})

                if log_type == "fallback_parse":
                    st.info(f"🔄 **Fallback:** {data.get('message', '')} - `{data.get('tool', '')}`")

                elif log_type == "llm_output":
                    tool_calls = data.get("tool_calls")
                    if tool_calls:
                        for tc in tool_calls:
                            step = {
                                "type": "tool_call",
                                "tool_name": tc.get("name"),
                                "arguments": tc.get("args", {}),
                            }
                            collected_steps.append(step)
                            display_step(step, st)

                elif log_type == "tool_result":
                    step = {
                        "type": "tool_result",
                        "tool_name": data.get("tool_name"),
                        "result": data.get("result"),
                    }
                    collected_steps.append(step)
                    display_step(step, st)

        # --- Final answer ---
        st.markdown(final_answer)

    return {"answer": final_answer, "steps": collected_steps}


    # Display final answer AFTER the expander
    st.markdown(final_answer)

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

    # Model selection
    st.header("🤖 Agent")

    # Check Ollama status
    ollama_running = check_ollama_running()

    if not ollama_running:
        st.error("❌ Ollama not running")
        st.caption("Start Ollama server first:")
        st.code("ollama serve", language="bash")
        st.session_state.agent_initialized = False
    else:
        # Get available models
        available_ollama_models = get_available_ollama_models()

        model_names = list(AVAILABLE_MODELS.keys())

        # Get current index
        current_model = st.session_state.selected_model
        current_index = model_names.index(current_model) if current_model in model_names else 0

        selected_model = st.selectbox(
            "Select Model",
            options=model_names,
            index=current_index,
            format_func=lambda x: AVAILABLE_MODELS[x],
            help="Choose LLM model. Qwen 2.5 recommended for best tool calling."
        )

        # Check if model changed
        if selected_model != st.session_state.selected_model:
            old_model = st.session_state.selected_model
            st.session_state.selected_model = selected_model
            old_cache_key = f"agent_{old_model}"
            st.session_state.pop(old_cache_key, None)
            st.rerun()

        # Check if selected model is available
        model_available = is_model_available(selected_model)

        if not model_available:
            st.warning(f"⚠️ Model not found: {selected_model}")
            st.caption("Download the model first:")
            st.code(f"ollama pull {selected_model}", language="bash")

            # Show available models
            if available_ollama_models:
                with st.expander("📦 Available models"):
                    for m in available_ollama_models:
                        st.code(m)

            st.session_state.agent_initialized = False
        else:
            # Model is available, initialize agent
            try:
                agent = get_agent(selected_model)
                st.success(f"✅ Agent ready")
                st.caption(f"Model: {selected_model}")
                st.session_state.agent_initialized = True
            except Exception as e:
                st.error(f"❌ Agent Error: {e}")
                st.session_state.agent_initialized = False

    st.divider()

    # Clear chat button
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("CityGrid AI Analyst v0.6")

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
                agent = get_agent(st.session_state.selected_model)

                chat_container = st.container()
                result = run_agent_with_streaming(agent, prompt, chat_container)

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
