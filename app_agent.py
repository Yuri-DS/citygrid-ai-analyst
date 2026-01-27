"""
CityGrid AI Analyst - Main Application
Phase 3: Visualization with optimized architecture
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from pathlib import Path
import sys
import json
import requests
import plotly.graph_objects as go
import concurrent.futures
import time

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database import get_connection
from agent import create_agent

# === Configuration ===
DB_PATH = Path(__file__).parent / "data" / "citygrid.db"
OLLAMA_BASE_URL = "http://localhost:11434"

# Available models (add your custom models here)
AVAILABLE_MODELS = {
    "qwen2.5:3b": "Qwen 2.5 3B - Fast ⚡",
    "qwen2.5:7b": "Qwen 2.5 7B - Quality ⭐",
    "qwen2.5-7b-ctx16k:latest": "Qwen 2.5 7B 16K context",
    "qwen2.5-7b-ctx32k:latest": "Qwen 2.5 7B 32K context",
    "llama3.1:8b": "Llama 3.1 8B",
}

# === Page Config ===
st.set_page_config(
    page_title="CityGrid AI Analyst",
    page_icon="🏙️",
    layout="wide"
)


# === Helper Functions ===

def check_ollama_running() -> bool:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def get_available_ollama_models() -> list[str]:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
    except:
        pass
    return []


def is_model_available(model_name: str) -> bool:
    available = get_available_ollama_models()
    base_name = model_name.split(":")[0]
    for m in available:
        if m == model_name or m.split(":")[0] == base_name:
            return True
    return False


@st.cache_resource
def init_database():
    return get_connection(DB_PATH)


def get_agent(model_name: str):
    cache_key = f"agent_{model_name}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = create_agent(model_name=model_name, verbose=True)
    return st.session_state[cache_key]


def safe_invoke(agent, prompt, timeout=300, retries=1):
    """
    Safely invoke agent with timeout and retry.
    """
    for attempt in range(retries + 1):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(agent.invoke, prompt)
                return future.result(timeout=timeout)

        except concurrent.futures.TimeoutError:
            if attempt < retries:
                print(f"[WARN] LLM timeout (attempt {attempt + 1}/{retries + 1}), retrying...")
                time.sleep(2)
                continue
            raise TimeoutError(f"LLM did not respond within {timeout} seconds")

        except Exception as e:
            if attempt < retries:
                print(f"[WARN] Error: {e}, retrying...")
                time.sleep(2)
                continue
            raise


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

    if step_type == "tool_call":
        tool_name = step.get("tool_name", "unknown")
        args = step.get("arguments", {})
        container.warning(f"🔧 **{tool_name}**")
        if tool_name == "execute_sql" and "query" in args:
            container.code(args["query"], language="sql")

    elif step_type == "tool_result":
        tool_name = step.get("tool_name", "unknown")
        result = step.get("result", "")
        container.success(f"✅ **{tool_name}** completed")
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict) and "data" in data and data["data"]:
                df = pd.DataFrame(data["data"][:5])
                container.dataframe(df, use_container_width=True)
                if data.get("row_count", 0) > 5:
                    container.caption(f"... and {data['row_count'] - 5} more rows")
        except:
            pass


def extract_steps_from_logs(logs) -> list[dict]:
    """Extract reasoning steps from logs."""
    collected_steps = []

    for log in logs:
        if not isinstance(log, dict):
            continue

        log_type = log.get("type")
        data = log.get("data", {})

        if log_type == "llm_output":
            tool_calls = data.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    collected_steps.append({
                        "type": "tool_call",
                        "tool_name": tc.get("name"),
                        "arguments": tc.get("args", {}),
                    })

        elif log_type == "tool_result":
            collected_steps.append({
                "type": "tool_result",
                "tool_name": data.get("tool_name"),
                "result": data.get("result", ""),
            })

    return collected_steps


def render_visualization(viz: dict, key_prefix: str = "viz"):
    """Render a single visualization."""
    viz_type = viz.get("type")

    if viz_type == "chart":
        try:
            fig = go.Figure(json.loads(viz["data"]))
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_chart")
        except Exception as e:
            st.error(f"Failed to render chart: {e}")

    elif viz_type == "map":
        try:
            components.html(viz["data"], height=500, scrolling=True)
        except Exception as e:
            st.error(f"Failed to render map: {e}")


# === UI ===

st.title("🏙️ CityGrid AI Analyst")
st.caption("AI-powered urban data analysis")

# Sidebar
with st.sidebar:
    st.header("📊 Database")

    try:
        db = init_database()
        st.success("✅ Connected")
        with st.expander("📋 Tables"):
            schema = db.get_schema_info()
            for table_name in sorted(schema.keys()):
                st.code(table_name)
    except Exception as e:
        st.error(f"❌ DB Error: {e}")

    st.divider()
    st.header("🤖 Agent")

    ollama_running = check_ollama_running()

    if not ollama_running:
        st.error("❌ Ollama not running")
        st.code("ollama serve", language="bash")
        st.session_state.agent_initialized = False
    else:
        available_ollama_models = get_available_ollama_models()
        model_names = list(AVAILABLE_MODELS.keys())

        current_model = st.session_state.selected_model
        current_index = model_names.index(current_model) if current_model in model_names else 0

        selected_model = st.selectbox(
            "Model",
            options=model_names,
            index=current_index,
            format_func=lambda x: AVAILABLE_MODELS.get(x, x),
        )

        if selected_model != st.session_state.selected_model:
            old_cache_key = f"agent_{st.session_state.selected_model}"
            st.session_state.pop(old_cache_key, None)
            st.session_state.selected_model = selected_model
            st.rerun()

        model_available = is_model_available(selected_model)

        if not model_available:
            st.warning(f"⚠️ Model not found")
            st.code(f"ollama pull {selected_model}", language="bash")
            if available_ollama_models:
                with st.expander("Available models"):
                    for m in available_ollama_models:
                        st.code(m)
            st.session_state.agent_initialized = False
        else:
            try:
                agent = get_agent(selected_model)
                st.success(f"✅ Ready")
                st.session_state.agent_initialized = True
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.session_state.agent_initialized = False

    st.divider()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("CityGrid AI Analyst v0.12")

# Main chat area
st.header("💬 Chat")

# Display chat history
for msg_idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Show visualizations
        if "visualizations" in message and message["visualizations"]:
            for viz_idx, viz in enumerate(message["visualizations"]):
                render_visualization(viz, key_prefix=f"hist_{msg_idx}_{viz_idx}")

        # Show reasoning steps (collapsed)
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

    # Get agent response
    with st.chat_message("assistant"):
        if st.session_state.agent_initialized:
            try:
                agent = get_agent(st.session_state.selected_model)

                with st.spinner("🤔 Thinking... (this may take a minute on CPU)"):
                    start_time = time.time()
                    result = safe_invoke(agent, prompt, timeout=300, retries=1)
                    elapsed = time.time() - start_time
                    print(f"DEBUG: Agent completed in {elapsed:.1f}s")

                # Extract from result
                final_answer = result.get("answer", "No answer generated")
                visualizations = result.get("visualizations", [])
                logs = result.get("logs", [])

                print(f"DEBUG: Got {len(visualizations)} visualization(s)")

                # Extract steps
                collected_steps = extract_steps_from_logs(logs)

                # Display answer
                st.markdown(final_answer)

                # Display visualizations
                for viz_idx, viz in enumerate(visualizations):
                    render_visualization(viz, key_prefix=f"new_{viz_idx}")

                # Save to session state
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": final_answer,
                    "steps": collected_steps,
                    "visualizations": visualizations
                })

            except TimeoutError as e:
                error_msg = "⏰ **Timeout:** The model took too long. Try a simpler question or smaller model."
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "steps": [],
                    "visualizations": []
                })

            except Exception as e:
                import traceback
                error_msg = f"Error: {str(e)}"
                print(f"ERROR: {traceback.format_exc()}")
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "steps": [],
                    "visualizations": []
                })
        else:
            st.warning("Agent not initialized. Check Ollama.")

    st.rerun()

# Example questions
if not st.session_state.messages:
    st.divider()
    st.subheader("💡 Try these questions")

    examples = [
        "How many districts are in the city?",
        "Show districts by population as a bar chart",
        "Show sensor type distribution as a pie chart",
        "Show all districts on a map",
    ]

    cols = st.columns(2)
    for i, example in enumerate(examples):
        with cols[i % 2]:
            if st.button(example, key=f"ex_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": example})
                st.rerun()
