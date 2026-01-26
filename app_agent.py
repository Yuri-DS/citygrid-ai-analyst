"""
CityGrid AI Analyst - Main Application
Phase 3: Visualization (Charts + Maps)
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


def safe_invoke(agent, prompt, timeout=180, retries=1):
    """
    Safely invoke agent with timeout and retry.

    Prevents UI from hanging if LLM gets stuck.
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
            raise TimeoutError(f"LLM did not respond within {timeout} seconds after {retries + 1} attempts")

        except Exception as e:
            if attempt < retries:
                print(f"[WARN] Error: {e}, retrying...")
                time.sleep(2)
                continue
            raise

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
        elif tool_name in ["create_chart", "suggest_chart_type"]:
            container.caption(f"Chart type: {args.get('chart_type', 'auto')}")
        elif tool_name in ["create_district_map", "create_points_map", "create_road_map"]:
            container.caption(f"Creating map: {args.get('title', 'Map')}")
        else:
            container.json(args)

    elif step_type == "tool_result":
        tool_name = step.get("tool_name", "unknown")
        result = step.get("result", "")
        container.success(f"✅ **Result from:** `{tool_name}`")
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict):
                # Handle chart result
                if "chart_json" in data and data.get("success"):
                    container.caption(f"Chart created: {data.get('chart_type', 'unknown')}")
                # Handle map result
                elif "map_html" in data and data.get("success"):
                    container.caption(f"Map created with {data.get('points_count', data.get('districts_count', data.get('roads_count', '?')))} items")
                # Handle SQL result
                elif "data" in data and data["data"]:
                    container.dataframe(pd.DataFrame(data["data"]), use_container_width=True)
                else:
                    container.code(str(result)[:500])
            else:
                container.code(str(result)[:500])
        except:
            container.code(str(result)[:500])

    elif step_type == "llm_response":
        content = step.get("content", "")
        if content:
            container.markdown(content)


def extract_visualizations_from_messages(messages) -> list[dict]:
    """
    Extract visualizations from full message objects.

    This uses the complete ToolMessage content, not truncated logs.
    """
    visualizations = []

    # Debug: print message info
    print(f"DEBUG extract_viz: Processing {len(messages) if messages else 0} messages")

    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        has_name = hasattr(msg, 'name')
        has_content = hasattr(msg, 'content')

        print(f"DEBUG msg[{i}]: type={msg_type}, has_name={has_name}, has_content={has_content}")

        # Check if it's a ToolMessage (has 'name' attribute and content)
        if has_name and has_content:
            tool_name = getattr(msg, 'name', 'unknown')
            content_preview = str(msg.content)[:100] if msg.content else 'empty'
            print(f"DEBUG msg[{i}]: tool_name={tool_name}, content_preview={content_preview}")

            try:
                # Parse the full content
                result_data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content

                if isinstance(result_data, dict) and result_data.get("success"):
                    if "chart_json" in result_data:
                        print(f"DEBUG msg[{i}]: Found chart_json!")
                        visualizations.append({
                            "type": "chart",
                            "data": result_data["chart_json"],
                            "title": result_data.get("title", "Chart")
                        })
                    elif "map_html" in result_data:
                        print(f"DEBUG msg[{i}]: Found map_html!")
                        visualizations.append({
                            "type": "map",
                            "data": result_data["map_html"],
                            "title": result_data.get("title", "Map")
                        })
                    else:
                        print(f"DEBUG msg[{i}]: success=True but no chart_json or map_html. Keys: {list(result_data.keys())}")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"DEBUG msg[{i}]: JSON parse error: {e}")

    print(f"DEBUG extract_viz: Found {len(visualizations)} visualizations")
    return visualizations


def extract_steps_from_logs(logs) -> list[dict]:
    """Extract reasoning steps from logs for display."""
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

        # Check if model changed - clear old agent cache
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
                st.success("✅ Agent ready")
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
    st.caption("CityGrid AI Analyst v0.10")

# Main chat area
st.header("💬 Chat")

# DEBUG: Show session state info
print(f"DEBUG SESSION: messages count = {len(st.session_state.messages)}")
for i, m in enumerate(st.session_state.messages):
    print(f"DEBUG SESSION msg[{i}]: role={m.get('role')}, content_len={len(m.get('content', ''))}, viz_count={len(m.get('visualizations', []))}")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Show visualizations if available
        if "visualizations" in message and message["visualizations"]:
            for viz in message["visualizations"]:
                if viz["type"] == "chart":
                    try:
                        fig = go.Figure(json.loads(viz["data"]))
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Failed to render chart: {e}")
                elif viz["type"] == "map":
                    try:
                        components.html(viz["data"], height=500, scrolling=True)
                    except Exception as e:
                        st.error(f"Failed to render map: {e}")

        # Show reasoning steps if available (collapsed)
        if "steps" in message and message["steps"]:
            with st.expander("🔍 Reasoning Steps"):
                for step in message["steps"]:
                    display_step(step, st)

# Chat input
if prompt := st.chat_input("Ask about city data...", disabled=not st.session_state.agent_initialized):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get agent response
    if st.session_state.agent_initialized:
        try:
            agent = get_agent(st.session_state.selected_model)

            # Show spinner while processing with timeout protection
            with st.spinner("🤔 Thinking... (max 3 min)"):
                start_time = time.time()
                result = safe_invoke(agent, prompt, timeout=180, retries=1)
                elapsed = time.time() - start_time
                print(f"DEBUG: Agent completed in {elapsed:.1f}s")

            # Extract answer
            if isinstance(result, dict):
                final_answer = (
                    result.get("answer")
                    or result.get("output")
                    or result.get("final_answer")
                    or result.get("content")
                    or "No answer generated"
                )
                logs = result.get("logs") or []
                messages = result.get("messages") or []
            else:
                final_answer = str(result)
                logs = []
                messages = []

            # Extract steps from logs (for display in expander)
            collected_steps = extract_steps_from_logs(logs)

            # Extract visualizations from FULL messages (not truncated logs!)
            visualizations = extract_visualizations_from_messages(messages)

            # Debug output (remove in production)
            if visualizations:
                print(f"DEBUG: Found {len(visualizations)} visualization(s)")

            # Save to session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": final_answer,
                "steps": collected_steps,
                "visualizations": visualizations
            })

        except TimeoutError as e:
            print(f"TIMEOUT ERROR: {e}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"⏰ **Timeout:** The model took too long to respond. Please try again or use a simpler question.",
                "steps": [],
                "visualizations": []
            })

        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)  # For debugging
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Error: {str(e)}",
                "steps": [],
                "visualizations": []
            })
    else:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Agent not initialized. Check Ollama connection.",
            "steps": [],
            "visualizations": []
        })

    # Rerun to display the new messages
    print(f"DEBUG BEFORE RERUN: messages count = {len(st.session_state.messages)}")
    st.rerun()

# # Example questions
# if not st.session_state.messages:
#     st.divider()
#     st.subheader("💡 Example Questions")
#
#     examples = [
#         "How many districts are in the city?",
#         "Show me districts by population as a bar chart",
#         "Show the distribution of sensor types as a pie chart",
#         "Show all districts on a map",
#         "What is the average population density across districts?",
#         "Show road conditions on a map",
#     ]
#
#     cols = st.columns(2)
#     for i, example in enumerate(examples):
#         with cols[i % 2]:
#             if st.button(example, key=f"example_{i}", use_container_width=True):
#                 st.session_state.messages.append({"role": "user", "content": example})
#                 st.rerun()