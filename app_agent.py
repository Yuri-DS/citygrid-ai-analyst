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

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from database import get_connection
from agent import create_agent

# === Configuration ===
DB_PATH = Path(__file__).parent / "data" / "citygrid.db"
OLLAMA_BASE_URL = "http://localhost:11434"
MAX_PROMPT_CHARS = 15_000  # Max user input length (characters)

# Available models - Ollama (add your custom models here)
AVAILABLE_MODELS = {
    "qwen2.5:3b": "Qwen 2.5 3B - Fast ⚡",
    "qwen2.5:7b": "Qwen 2.5 7B - Quality ⭐",
    "qwen2.5-7b-ctx16k:latest": "Qwen 2.5 7B 16K context",
    "granite3-dense:8b-instruct-q3_K_M": "granite3",
    "llama3.1:8b-instruct-q4_K_M": "llama3 instruct",
    "llama3.1:8b": "Llama 3.1 8B",
}

# ChatGPT (OpenAI API) models
OPENAI_MODELS = {
    "gpt-4o-mini": "GPT-4o mini - Fast & cheap"
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


def get_agent(model_name: str, provider: str = "ollama", api_key: str | None = None):
    cache_key = f"agent_{provider}_{model_name}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = create_agent(
            model_name=model_name,
            verbose=True,
            provider=provider,
            api_key=api_key,
        )
    return st.session_state[cache_key]


# === Session State ===
if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_initialized" not in st.session_state:
    st.session_state.agent_initialized = False

if "selected_model" not in st.session_state:
    st.session_state.selected_model = list(AVAILABLE_MODELS.keys())[0]

if "provider" not in st.session_state:
    st.session_state.provider = "ollama"

if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = ""

if "selected_openai_model" not in st.session_state:
    st.session_state.selected_openai_model = "gpt-4o-mini"


# === Display Functions ===

def display_step(step: dict, container, parent_message: dict | None = None):
    """Display a single reasoning step. When parent has map/chart, do not show dataframe for execute_sql."""
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
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict) and data.get("success") is False:
                err_msg = data.get("error", "Unknown error")
                container.error(f"❌ **{tool_name}** failed: {err_msg}")
            else:
                container.success(f"✅ **{tool_name}** completed")
                if isinstance(data, dict) and "data" in data and data["data"]:
                    has_viz = parent_message and (parent_message.get("visualizations") or [])
                    if tool_name == "execute_sql" and has_viz:
                        container.caption(f"({data.get('row_count', len(data['data']))} rows used for visualization)")
                    else:
                        df = pd.DataFrame(data["data"][:5])
                        container.dataframe(df, use_container_width=True)
                        if data.get("row_count", 0) > 5:
                            container.caption(f"... and {data['row_count'] - 5} more rows")
        except Exception:
            container.success(f"✅ **{tool_name}** completed")


def format_checklist_progress(checklist: list, checklist_done: dict) -> str:
    """Format checklist progress as e.g. '✓ execute_sql, ○ create_map'."""
    if not checklist:
        return ""
    parts = []
    for name in checklist:
        done = checklist_done.get(name, False)
        parts.append(f"{'✓' if done else '○'} {name}")
    return ", ".join(parts)


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

    provider = st.radio(
        "Provider",
        options=["ollama", "openai"],
        format_func=lambda x: "Ollama (local)" if x == "ollama" else "ChatGPT (OpenAI API)",
        index=0 if st.session_state.provider == "ollama" else 1,
        key="provider_radio",
    )
    if provider != st.session_state.provider:
        st.session_state.provider = provider
        st.rerun()

    if provider == "ollama":
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
                old_cache_key = f"agent_ollama_{st.session_state.selected_model}"
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
                    agent = get_agent(selected_model, provider="ollama")
                    st.success(f"✅ Ready")
                    st.session_state.agent_initialized = True
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    st.session_state.agent_initialized = False
    else:
        # ChatGPT (OpenAI API)
        openai_models = list(OPENAI_MODELS.keys())
        current_openai = st.session_state.selected_openai_model
        openai_index = openai_models.index(current_openai) if current_openai in openai_models else 0
        selected_openai_model = st.selectbox(
            "ChatGPT model",
            options=openai_models,
            index=openai_index,
            format_func=lambda x: OPENAI_MODELS.get(x, x),
            key="openai_model_select",
        )
        if selected_openai_model != st.session_state.selected_openai_model:
            old_cache_key = f"agent_openai_{st.session_state.selected_openai_model}"
            st.session_state.pop(old_cache_key, None)
            st.session_state.selected_openai_model = selected_openai_model
            st.rerun()

        # manual entry
        api_key = st.session_state.get("openai_api_key", "")

        if not api_key:
            key_input = st.text_input(
                "OpenAI API key",
                type="password",
                placeholder="sk-...",
                help="Enter key manually to connect",
            )
            if key_input:
                st.session_state.openai_api_key = key_input
                st.rerun()

            st.info("Enter OpenAI API key to use ChatGPT.")
            st.session_state.agent_initialized = False
        else:
            # Проверка подключения только после ручного ввода (ключ уже сохранен в session_state)
            try:
                agent = get_agent(
                    st.session_state.selected_openai_model,
                    provider="openai",
                    api_key=api_key,
                )
                st.success("✅ Ready (ChatGPT)")
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

        # Show checklist progress (collapsed) for assistant messages
        if message.get("role") == "assistant" and message.get("checklist"):
            progress = format_checklist_progress(
                message.get("checklist", []),
                message.get("checklist_done", {}),
            )
            if progress:
                with st.expander("Progress", expanded=False):
                    st.caption(progress)

        # Show reasoning steps (collapsed)
        if "steps" in message and message["steps"]:
            with st.expander("🔍 Reasoning Steps"):
                for step in message["steps"]:
                    display_step(step, st, parent_message=message)

# Chat input
if prompt := st.chat_input("Ask about city data...", disabled=not st.session_state.agent_initialized):
    if len(prompt) > MAX_PROMPT_CHARS:
        st.warning(
            f"⚠️ Your question is too long ({len(prompt):,} characters). "
            f"Maximum allowed: {MAX_PROMPT_CHARS:,}. Please make it shorter."
        )
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    if not st.session_state.agent_initialized:
        st.warning("Agent not initialized. Check Ollama or API key.")
        st.rerun()
    else:
        current_model = (
            st.session_state.selected_openai_model
            if st.session_state.provider == "openai"
            else st.session_state.selected_model
        )
        api_key = None
        if st.session_state.provider == "openai":
            api_key = st.session_state.get("openai_api_key") or ""
            try:
                api_key = api_key or st.secrets.get("openai_api_key", "")
            except Exception:
                pass
        agent = get_agent(
            current_model,
            provider=st.session_state.provider,
            api_key=api_key if st.session_state.provider == "openai" else None,
        )
        result_holder = []
        try:
            with st.chat_message("assistant"):
                st.write_stream(agent.stream_run(prompt, result_holder))
        except Exception as e:
            st.error(str(e))
        if result_holder:
            result = result_holder[0]
            collected_steps = extract_steps_from_logs(result.get("logs", []))
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("answer", "No answer generated"),
                "steps": collected_steps,
                "visualizations": result.get("visualizations", []),
                "checklist": result.get("checklist", []),
                "checklist_done": result.get("checklist_done", {}),
            })
            if result.get("error"):
                st.error(result["error"])
        st.rerun()

# # Example questions
# if not st.session_state.messages:
#     st.divider()
#     st.subheader("💡 Try these questions")
#
#     examples = [
#         "How many districts are in the city?",
#         "Show districts by population as a bar chart",
#         "Show sensor type distribution as a pie chart",
#         "Show all districts on a map",
#     ]
#
#     cols = st.columns(2)
#     for i, example in enumerate(examples):
#         with cols[i % 2]:
#             if st.button(example, key=f"ex_{i}", use_container_width=True):
#                 st.session_state.messages.append({"role": "user", "content": example})
#                 st.rerun()