"""
LangGraph Agent for CityGrid AI Analyst.

ReAct-style agent that can query the database and analyze results.
"""

from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from datetime import datetime
import json
import re

import sys
from pathlib import Path

# Import ValidationError for catching malformed tool calls
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import ALL_TOOLS
from agent.prompts import SYSTEM_PROMPT, CHECKLIST_PROMPT


# === Logging ===

class AgentLogger:
    """Logger for agent actions."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.logs = []

    def log(self, event_type: str, data: dict):
        """Log an event."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "type": event_type,
            "data": data
        }
        self.logs.append(entry)

        if self.verbose:
            self._print_log(entry)

    def _print_log(self, entry: dict):
        """Print log entry to console."""
        t = entry["timestamp"]
        event_type = entry["type"]
        data = entry["data"]

        print(f"\n{'='*60}")
        print(f"[{t}] {event_type.upper()}")
        print('='*60)

        if event_type == "user_input":
            print(f"Question: {data.get('question', '')}")
        elif event_type == "llm_input":
            print(f"Messages count: {data.get('messages_count', data.get('message_count', 0))}")
            print(f"Last message type: {data.get('last_message_type', '')}")
            if data.get('total_chars'):
                print(f"Total chars: {data.get('total_chars'):,}")
                print(f"Estimated tokens: ~{data.get('estimated_tokens'):,}")
            if data.get('system_prompt_chars'):
                print(f"  (system prompt: {data.get('system_prompt_chars'):,} chars)")
        elif event_type == "llm_output":
            print(f"Response type: {data.get('response_type', '')}")
            if data.get('tool_calls'):
                print(f"Tool calls: {json.dumps(data['tool_calls'], indent=2)}")
            elif data.get('content'):
                content = data['content'][:300] + "..." if len(data.get('content', '')) > 300 else data.get('content', '')
                print(f"Content: {content}")
        elif event_type == "tool_call":
            print(f"Tool: {data.get('tool_name', '')}")
        elif event_type == "tool_result":
            print(f"Tool: {data.get('tool_name', '')}")
            result = str(data.get('result', ''))[:200]
            print(f"Result: {result}...")
        elif event_type == "decision":
            print(f"Next: {data.get('next_step', '')} - {data.get('reason', '')}")
        elif event_type == "visualization_stored":
            print(f"Stored: {data.get('type', '')} - {data.get('title', '')}")
        elif event_type == "data_from_previous_sql":
            print(f"Using data from previous SQL for {data.get('tool', '')} ({data.get('rows', 0)} rows)")
        elif event_type == "final_answer":
            answer = data.get('answer', '')[:200]
            print(f"Answer: {answer}...")
        elif event_type == "checklist_generated":
            print(f"Checklist: {data.get('checklist', [])}")
            if data.get('error'):
                print(f"Error: {data['error']}")
        elif event_type == "reminder_sent":
            print(f"Reminder: remaining {data.get('remaining', [])}")
        elif event_type == "checklist_done_updated":
            checklist = data.get("checklist", [])
            checklist_done = data.get("checklist_done", {})
            completed = [t for t in checklist if checklist_done.get(t, False)]
            remaining = [t for t in checklist if not checklist_done.get(t, False)]
            print(f"Completed: {completed}")
            print(f"Remaining: {remaining}")
        elif event_type == "tool_validation_error":
            print(f"Tool: {data.get('tool_name', '')}")
            print(f"Invalid args: {data.get('invalid_args', {})}")
            print(f"Error: {data.get('error', '')}")
        elif event_type == "tool_retry_requested":
            print(f"Retry requested for: {data.get('tool_name', '')}")

        print()

    def get_logs(self) -> list[dict]:
        return self.logs.copy()

    def clear(self):
        self.logs = []


# === Agent State ===


class AgentState(TypedDict):
    """State of the agent during execution."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    checklist: list[str]
    checklist_done: dict[str, bool]


# === Agent Graph ===

class CityGridAgent:
    """
    CityGrid AI Agent using LangGraph.

    Features:
    - ReAct pattern for reasoning + acting
    - Universal tools: agent decides how to use them
    - Separate visualization storage (not sent to LLM to save context)
    - ValidationError retry: asks LLM to fix malformed tool calls
    """

    # Tools that produce visualizations
    VIZ_TOOLS = {"create_chart", "create_map"}

    # Max retries for validation errors per tool call
    MAX_VALIDATION_RETRIES = 2

    # Max total characters in context sent to LLM (~7K tokens)
    MAX_CONTEXT_CHARS = 30_000

    def __init__(
        self,
        model_name: str = "llama3.1:8b",
        ollama_base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_iterations: int = 10,
        verbose: bool = True,
        provider: str = "ollama",
        api_key: str | None = None,
    ):
        self.model_name = model_name
        self.provider = provider
        self.max_iterations = max_iterations
        self.logger = AgentLogger(verbose=verbose)
        self.visualizations = []  # Store visualizations separately from messages

        if provider == "openai":
            import os
            key = api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("OpenAI API key required: set OPENAI_API_KEY or pass api_key=...")
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=key,
            )
        else:
            # Ollama (default)
            self.llm = ChatOllama(
                model=model_name,
                base_url=ollama_base_url,
                temperature=temperature,
                timeout=180,  # 3 minutes timeout - prevents infinite hang
            )

        # Bind tools to LLM
        self.tools = ALL_TOOLS
        self.tools_by_name = {tool.name: tool for tool in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build graph
        self.graph = self._build_graph()

    # Checklist uses only workflow tools; exclude helpers (get_table_sample, get_schema)
    # so the planner never suggests "sample 5 rows" for map/chart requests.
    CHECKLIST_TOOLS = {"search_documentation", "execute_sql", "create_chart", "create_map"}

    def _generate_checklist(self, question: str) -> list[str]:
        """Generate required tool names for this request via one LLM call (no tools)."""
        allowed_set = self.CHECKLIST_TOOLS
        allowed_tools_str = ", ".join(sorted(allowed_set))
        try:
            prompt = CHECKLIST_PROMPT.format(allowed_tools=allowed_tools_str, question=question)
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = (response.content or "").strip()
            # Extract JSON array (allow markdown code block)
            if "```" in content:
                match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1)
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                return []
            # Filter to allowed tools, preserve order
            checklist = [str(x).strip() for x in parsed if str(x).strip() in allowed_set]
            # Ensure execute_sql before first viz tool
            viz = self.VIZ_TOOLS
            for i, name in enumerate(checklist):
                if name in viz:
                    if "execute_sql" not in checklist[:i]:
                        checklist.insert(i, "execute_sql")
                    break
            self.logger.log("checklist_generated", {"checklist": checklist})
            return checklist
        except (json.JSONDecodeError, re.error) as e:
            self.logger.log("checklist_generated", {"error": str(e), "checklist": []})
            return []

    def _reminder_node(self, state: AgentState) -> dict:
        """Append a reminder message when checklist is not done and LLM replied with text only."""
        checklist = state.get("checklist") or []
        checklist_done = state.get("checklist_done") or {}
        remaining = [t for t in checklist if not checklist_done.get(t, True)]
        next_step = remaining[0] if remaining else ""

        # Check if the previous tool call had a validation error — give context
        had_error = False
        messages = state.get("messages") or []
        for m in reversed(messages[-5:]):
            if hasattr(m, "content") and isinstance(m.content, str) and "ValidationError" in m.content:
                had_error = True
                break

        if had_error:
            msg = (
                f"Your previous {next_step} call failed due to a validation error. "
                f"Do NOT describe the problem in text — instead, fix the arguments and call {next_step} again immediately. "
                f"Read the error message carefully: it tells you exactly which parameters are required."
            )
        else:
            msg = (
                f"Task not complete. Remaining steps: {remaining}. "
                f"Call {next_step} now with the correct arguments. "
                f"Do not respond with only text — you MUST make a tool call."
            )

        self.logger.log("reminder_sent", {"remaining": remaining})
        return {"messages": [HumanMessage(content=msg)]}

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph agent graph."""
        graph = StateGraph(AgentState)

        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("reminder", self._reminder_node)

        graph.set_entry_point("agent")
        graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "end": END,
                "reminder": "reminder",
            }
        )
        graph.add_edge("tools", "agent")
        graph.add_edge("reminder", "agent")

        return graph.compile()

    def _trim_context(self, messages, max_chars: int):
        """Trim oldest ToolMessage bodies to fit context within max_chars.

        Replaces content of the oldest ToolMessages first, preserving
        HumanMessage/AIMessage and the most recent tool results.
        """
        messages = list(messages)
        for i in range(len(messages)):
            total = sum(len(m.content or "") for m in messages)
            if total <= max_chars:
                break
            if isinstance(messages[i], ToolMessage):
                messages[i] = ToolMessage(
                    content='{"note": "Content trimmed to save context"}',
                    name=messages[i].name,
                    tool_call_id=messages[i].tool_call_id,
                )
        return messages

    def _agent_node(self, state: AgentState) -> dict:
        """Agent reasoning node."""
        messages = state["messages"]
        last_msg = messages[-1] if messages else None

        self.logger.log("llm_input", {
            "message_count": len(messages),
            "last_message_type": type(last_msg).__name__ if last_msg else None,
        })

        # Build system prompt: base + optional "Remaining steps" when checklist not done
        system_prompt = SYSTEM_PROMPT
        checklist = state.get("checklist") or []
        checklist_done = state.get("checklist_done") or {}
        if checklist:
            remaining = [t for t in checklist if not checklist_done.get(t, True)]
            done = [t for t in checklist if checklist_done.get(t, False)]
            if remaining:
                next_step = remaining[0]
                system_prompt += (
                    f"\n\n## Current Progress"
                    f"\nCompleted: {done if done else 'none'}"
                    f"\nRemaining: {remaining}"
                    f"\nNEXT STEP: {next_step}"
                    f"\n\nYou MUST call {next_step} now. Do not respond with text only — that will be treated as task abandonment."
                    f" If a previous tool call failed, read the error and fix the arguments."
                )

        # Calculate prompt size
        def estimate_tokens(messages_list, system_prompt=None):
            """Estimate token count. Rough approximation: 1 token ≈ 4 chars for English."""
            total_chars = 0
            if system_prompt:
                total_chars += len(system_prompt)
            for msg in messages_list:
                if hasattr(msg, 'content'):
                    total_chars += len(msg.content or "")
                elif isinstance(msg, tuple):
                    total_chars += len(msg[1] or "")
            return total_chars, total_chars // 4  # chars, estimated tokens

        # Workaround: torch.classes can raise when something touches __path__._path
        # (e.g. during message handling). Patch to avoid crash so LLM invoke completes.
        def _apply_torch_patch():
            try:
                import torch
                if not hasattr(torch, "classes"):
                    return None
                _orig_classes = torch.classes
                _dummy_class = type("_DummyTorchClass", (), {})
                _dummy_ns = type("_DummyNs", (), {"__getattr__": lambda self, _: _dummy_class})()
                def _safe_getattr(self, name):
                    if name == "__path__":
                        return _dummy_ns
                    try:
                        return getattr(_orig_classes, name)
                    except Exception:
                        return _dummy_ns
                _safe_classes = type("_SafeClasses", (), {"__getattr__": _safe_getattr})()
                torch.classes = _safe_classes
                return _orig_classes
            except Exception:
                return None

        def _restore_torch_patch(orig):
            if orig is not None:
                try:
                    import torch
                    torch.classes = orig
                except Exception:
                    pass

        orig_torch_classes = _apply_torch_patch()
        try:
            # Add system prompt for first message
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_message = ("system", system_prompt)
                chars, tokens = estimate_tokens(messages, system_prompt)
                self.logger.log("llm_input", {
                    "messages_count": len(messages),
                    "system_prompt_chars": len(system_prompt),
                    "total_chars": chars,
                    "estimated_tokens": tokens,
                    "last_message_type": type(messages[-1]).__name__,
                })
                response = self.llm_with_tools.invoke([system_message] + list(messages))
            else:
                chars, tokens = estimate_tokens(messages)
                # Trim context if too large
                if chars > self.MAX_CONTEXT_CHARS:
                    messages = self._trim_context(messages, self.MAX_CONTEXT_CHARS)
                    trimmed_chars, trimmed_tokens = estimate_tokens(messages)
                    self.logger.log("context_truncated", {
                        "original_chars": chars,
                        "trimmed_chars": trimmed_chars,
                        "original_tokens": tokens,
                        "trimmed_tokens": trimmed_tokens,
                    })
                    chars, tokens = trimmed_chars, trimmed_tokens
                self.logger.log("llm_input", {
                    "messages_count": len(messages),
                    "total_chars": chars,
                    "estimated_tokens": tokens,
                    "last_message_type": type(messages[-1]).__name__,
                })
                response = self.llm_with_tools.invoke(messages)
        finally:
            _restore_torch_patch(orig_torch_classes)

        # Strip hallucinated base64 images from response content (e.g. ChatGPT embedding charts as markdown)
        if response.content:
            # Markdown image links: ![alt](data:image/...base64...)
            cleaned = re.sub(
                r'!\[\s*[^\]]*\]\s*\(\s*data:image/[^)]+\)',
                '[Chart created via create_chart tool]',
                response.content,
                flags=re.IGNORECASE,
            )
            # Orphan data: URIs (no ![ ] wrapper)
            cleaned = re.sub(
                r'data:image/[^)]+\)',
                '[Image removed]',
                cleaned,
                flags=re.IGNORECASE,
            )
            if cleaned != response.content:
                response.content = cleaned

        # Log output
        tool_calls = None
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [{"name": tc["name"], "args": tc["args"]} for tc in response.tool_calls]

        self.logger.log("llm_output", {
            "response_type": type(response).__name__,
            "content": response.content,
            "tool_calls": tool_calls,
        })

        # Log thinking (LLM's reasoning content)
        if response.content and not tool_calls:
            self.logger.log("thinking", {
                "content": response.content
            })

        return {"messages": [response]}

    def _get_tool_schema(self, tool_name: str) -> str:
        """Get tool schema as a string for error messages."""
        tool = self.tools_by_name.get(tool_name)
        if not tool:
            return "Tool not found"
        
        # Extract schema from tool
        try:
            schema = tool.args_schema.model_json_schema() if hasattr(tool, 'args_schema') else {}
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            
            params = []
            for name, info in properties.items():
                param_type = info.get("type", "any")
                req = "(required)" if name in required else "(optional)"
                params.append(f"  - {name}: {param_type} {req}")
            
            return "\n".join(params) if params else "No parameters"
        except Exception:
            return "Schema unavailable"

    def _tools_node(self, state: AgentState) -> dict:
        """Execute tool calls and store visualizations separately.
        
        Handles ValidationError by returning error message to LLM for retry.
        """
        messages = state["messages"]
        last_message = messages[-1]
        results = []

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            # --- Checklist order guard ---
            # If LLM skips earlier checklist steps, block the call and redirect.
            checklist = state.get("checklist") or []
            checklist_done = state.get("checklist_done") or {}

            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                if checklist and tool_name in checklist:
                    skipped = []
                    for step in checklist:
                        if step == tool_name:
                            break
                        if not checklist_done.get(step, False):
                            skipped.append(step)
                    if skipped:
                        next_required = skipped[0]
                        warning_msg = {
                            "success": False,
                            "error": f"Skipped required step: {next_required}",
                            "details": (
                                f"You called {tool_name}, but {next_required} has not been completed yet. "
                                f"Without {next_required}, your {tool_name} call is likely to produce incorrect results "
                                f"(wrong column names, missing JOINs, bad aggregation). "
                                f"Call {next_required} first, then use its results to make a correct {tool_name} call."
                            ),
                            "skipped_steps": skipped,
                            "action_required": f"Call {next_required} now.",
                        }
                        self.logger.log("checklist_order_violation", {
                            "called": tool_name,
                            "skipped": skipped,
                            "redirected_to": next_required,
                        })
                        results.append(ToolMessage(
                            content=json.dumps(warning_msg, ensure_ascii=False),
                            name=tool_name,
                            tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                        ))
                        continue

                # Check if visualization tool called with empty data
                if tool_name in self.VIZ_TOOLS:
                    data_arg = tool_args.get("data", "")
                    is_empty = (data_arg == "" or data_arg == [] or data_arg is None)

                    if is_empty:
                        # Try to get data from previous SQL result (full data from state, not truncated message)
                        sql_data = self._last_sql_data or self._get_last_sql_data(messages)
                        if sql_data:
                            tool_args["data"] = sql_data
                            self.logger.log("data_from_previous_sql", {
                                "tool": tool_name,
                                "rows": len(sql_data),
                            })
                        else:
                            # No auto-fetch - return error, let agent call execute_sql
                            results.append(ToolMessage(
                                content=json.dumps({
                                    "success": False,
                                    "error": "No data provided. Call execute_sql first to get data, then call this tool with the result."
                                }),
                                name=tool_name,
                                tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                            ))
                            continue

                self.logger.log("tool_call", {
                    "tool_name": tool_name,
                    "arguments": {k: v if k != "data" else f"[{len(v) if isinstance(v, list) else 'str'}]" for k, v in tool_args.items()},
                })

                tool_fn = self.tools_by_name.get(tool_name)
                if tool_fn:
                    try:
                        # Attempt to invoke the tool
                        result = tool_fn.invoke(tool_args)
                        
                        # Handle visualization tools specially
                        if tool_name in self.VIZ_TOOLS and isinstance(result, dict) and result.get("success"):
                            # Store visualization for UI (full data)
                            if "chart_json" in result:
                                self.visualizations.append({
                                    "type": "chart",
                                    "data": result["chart_json"],
                                    "title": result.get("title", "Chart"),
                                    "chart_type": result.get("chart_type"),
                                })
                                # Short summary for LLM; instruction first so model does not waste tokens on base64
                                llm_result = {
                                    "success": True,
                                    "message": f"Chart created: {result.get('title', 'Chart')}",
                                    "chart_type": result.get("chart_type"),
                                    "rows_visualized": result.get("rows_visualized"),
                                }
                            elif "map_html" in result:
                                self.visualizations.append({
                                    "type": "map",
                                    "data": result["map_html"],
                                    "title": result.get("title", "Map"),
                                })
                                llm_result = {
                                    "success": True,
                                    "message": f"Map created: {result.get('title', 'Map')}",
                                    "items_count": result.get("items_count"),
                                    "map_type": result.get("map_type"),
                                }
                                llm_result = {k: v for k, v in llm_result.items() if v is not None}
                            else:
                                llm_result = result

                            # Prepend strong instruction so OpenAI does not generate base64 (saves tokens)
                            viz_instruction = (
                                "Reply in 1-2 short sentences, plain text only. Do NOT output any image, "
                                "base64, or data: URI — that wastes thousands of tokens and is invalid. "
                                "The chart/map is already shown by the system.\n\n"
                            )
                            llm_result_str = viz_instruction + json.dumps(llm_result, ensure_ascii=False)
                            self.logger.log("visualization_stored", {
                                "type": self.visualizations[-1]["type"],
                                "title": self.visualizations[-1]["title"],
                            })
                        else:
                            # Non-visualization tool or error - send full result to LLM
                            if tool_name == "execute_sql" and isinstance(result, dict) and result.get("success") and result.get("data"):
                                # Store full data for create_map/create_chart; send truncated to LLM to avoid token explosion
                                self._last_sql_data = result["data"]
                                max_rows_for_llm = 30
                                trunc = result["data"][:max_rows_for_llm]
                                truncated_result = {
                                    "success": True,
                                    "row_count": result["row_count"],
                                    "columns": result["columns"],
                                    "query_executed": result.get("query_executed"),
                                    "data": trunc,
                                    "_truncated": len(result["data"]) > max_rows_for_llm,
                                    "message": f"Result has {result['row_count']} rows; first {len(trunc)} shown. Full data available for create_map/create_chart." if len(result["data"]) > max_rows_for_llm else None,
                                }
                                truncated_result = {k: v for k, v in truncated_result.items() if v is not None}
                                llm_result_str = json.dumps(truncated_result, ensure_ascii=False)
                            else:
                                llm_result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                                if tool_name == "execute_sql":
                                    self._last_sql_data = result.get("data") if isinstance(result, dict) else None

                        self.logger.log("tool_result", {
                            "tool_name": tool_name,
                            "result": llm_result_str[:500],
                        })

                        results.append(ToolMessage(
                            content=llm_result_str,
                            name=tool_name,
                            tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                        ))
                        
                    except ValidationError as e:
                        # LLM generated malformed arguments - ask it to fix
                        self.logger.log("tool_validation_error", {
                            "tool_name": tool_name,
                            "invalid_args": tool_args,
                            "error": str(e),
                        })
                        
                        # Build helpful error message for LLM
                        tool_schema = self._get_tool_schema(tool_name)
                        error_msg = {
                            "success": False,
                            "error": "ValidationError: Invalid tool arguments",
                            "details": f"Your tool call had malformed arguments. The error was: {e.errors()[0]['msg'] if e.errors() else str(e)}",
                            "invalid_args_received": tool_args,
                            "expected_schema": f"Tool '{tool_name}' expects:\n{tool_schema}",
                            "hint": "Please call the tool again with correct argument names and types. Check for typos in parameter names.",
                        }
                        
                        self.logger.log("tool_retry_requested", {"tool_name": tool_name})
                        
                        results.append(ToolMessage(
                            content=json.dumps(error_msg, ensure_ascii=False),
                            name=tool_name,
                            tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                        ))
                        
                    except Exception as e:
                        # Other errors - also send to LLM
                        error_result = {
                            "success": False,
                            "error": f"{type(e).__name__}: {str(e)}",
                        }
                        results.append(ToolMessage(
                            content=json.dumps(error_result, ensure_ascii=False),
                            name=tool_name,
                            tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                        ))
                else:
                    error_msg = f"Tool not found: {tool_name}"
                    results.append(ToolMessage(
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=tool_call.get("id", f"call_{tool_name}"),
                    ))

        # Update checklist_done for executed tools (only if no validation error)
        checklist_done = dict(state.get("checklist_done") or {})
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for i, tool_call in enumerate(last_message.tool_calls):
                # Check if this tool had an error
                if i < len(results):
                    try:
                        result_content = json.loads(results[i].content)
                        if result_content.get("success", True):  # Mark done only if successful
                            checklist_done[tool_call["name"]] = True
                    except (json.JSONDecodeError, TypeError):
                        # If we can't parse, assume success (old behavior)
                        checklist_done[tool_call["name"]] = True
            self.logger.log("checklist_done_updated", {
                "checklist_done": checklist_done,
                "checklist": state.get("checklist") or [],
            })

        return {"messages": results, "checklist_done": checklist_done}

    def _get_last_sql_data(self, messages) -> list | None:
        """Get data from the last successful SQL query in messages."""
        for msg in reversed(messages):
            if hasattr(msg, "name") and msg.name == "execute_sql":
                try:
                    result = json.loads(msg.content)
                    if result.get("success") and result.get("data"):
                        return result["data"]
                except:
                    pass
        return None

    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue with tools, go to reminder, or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # If LLM wants to use tools, continue
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            self.logger.log("decision", {
                "next_step": "tools",
                "reason": f"LLM requested {len(last_message.tool_calls)} tool(s)",
            })
            return "tools"

        checklist = state.get("checklist") or []
        checklist_done = state.get("checklist_done") or {}
        all_done = all(checklist_done.get(t, True) for t in checklist)

        if checklist and not all_done:
            self.logger.log("decision", {
                "next_step": "reminder",
                "reason": "Checklist not done, LLM replied with text only",
            })
            return "reminder"

        self.logger.log("decision", {
            "next_step": "end",
            "reason": "LLM provided final answer",
        })
        return "end"

    def invoke(self, question: str) -> dict:
        """Run the agent on a question."""
        self.logger.clear()
        self.visualizations = []  # Clear visualizations from previous run
        self._last_sql_data = None  # Full SQL result for create_map/create_chart; LLM gets truncated

        self.logger.log("user_input", {"question": question})

        checklist = self._generate_checklist(question)
        checklist_done = {name: False for name in checklist}
        initial_state = {
            "messages": [HumanMessage(content=question)],
            "checklist": checklist,
            "checklist_done": checklist_done,
        }
        # Cap steps to avoid infinite reminder loops and terminal freeze (each loop = agent + tools/reminder).
        # If the terminal freezes, Ctrl+C and refresh the app; recursion_limit will stop the graph eventually.
        recursion_limit = max(10, self.max_iterations * 3)
        result = self.graph.invoke(
            initial_state,
            config={"recursion_limit": recursion_limit},
        )

        messages = result["messages"]
        final_answer = self._extract_final_answer(messages)
        out_checklist = result.get("checklist", checklist)
        out_checklist_done = result.get("checklist_done", checklist_done)

        self.logger.log("final_answer", {"answer": final_answer[:300] if final_answer else ""})

        return {
            "answer": final_answer,
            "messages": messages,
            "visualizations": self.visualizations.copy(),  # Return stored visualizations
            "steps": self._extract_steps(messages),
            "logs": self.logger.get_logs(),
            "checklist": out_checklist,
            "checklist_done": out_checklist_done,
        }

    def stream_run(self, question: str, result_holder: list | None = None):
        """
        Run the agent on a question, yielding markdown strings for each step (tool call / tool result).
        Final result is appended to result_holder if provided.
        """
        self.logger.clear()
        self.visualizations = []
        self._last_sql_data = None

        self.logger.log("user_input", {"question": question})

        checklist = self._generate_checklist(question)
        checklist_done = {name: False for name in checklist}
        initial_state = {
            "messages": [HumanMessage(content=question)],
            "checklist": checklist,
            "checklist_done": checklist_done,
        }
        recursion_limit = max(10, self.max_iterations * 3)
        config = {"recursion_limit": recursion_limit}

        prev_len = 0
        last_state = None

        try:
            for state in self.graph.stream(
                initial_state,
                config=config,
                stream_mode="values",
            ):
                last_state = state
                messages = state.get("messages") or []
                new_messages = messages[prev_len:]
                for msg in new_messages:
                    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                        for tc in msg.tool_calls:
                            name = tc.get("name", "unknown")
                            args = tc.get("args") or {}
                            line = f"**{name}**"
                            if name == "execute_sql" and args.get("query"):
                                q = (args["query"] or "").strip()
                                if len(q) > 80:
                                    q = q[:80] + "..."
                                line += f"\n\n```sql\n{q}\n```"
                            yield f"🔧 {line}\n\n"
                    elif isinstance(msg, ToolMessage):
                        name = getattr(msg, "name", "unknown")
                        content = getattr(msg, "content", "") or ""
                        try:
                            data = json.loads(content) if isinstance(content, str) else content
                            if isinstance(data, dict) and data.get("success") is False:
                                err_msg = data.get("error", "Unknown error")
                                yield f"❌ **{name}** failed: {err_msg}\n\n"
                            else:
                                yield f"✅ **{name}** completed\n\n"
                        except Exception:
                            yield f"✅ **{name}** completed\n\n"
                prev_len = len(messages)

            if last_state is None:
                last_state = initial_state

            messages = last_state.get("messages") or []
            final_answer = self._extract_final_answer(messages)
            out_checklist = last_state.get("checklist", checklist)
            out_checklist_done = last_state.get("checklist_done", checklist_done)
            self.logger.log("final_answer", {"answer": (final_answer or "")[:300]})

            result = {
                "answer": final_answer or "No answer generated",
                "messages": messages,
                "visualizations": self.visualizations.copy(),
                "steps": self._extract_steps(messages),
                "logs": self.logger.get_logs(),
                "checklist": out_checklist,
                "checklist_done": out_checklist_done,
            }
            if result_holder is not None:
                result_holder.append(result)
        except Exception as e:
            err_result = {
                "answer": f"Error: {e}",
                "messages": [],
                "visualizations": [],
                "steps": [],
                "logs": self.logger.get_logs(),
                "checklist": checklist,
                "checklist_done": checklist_done,
                "error": str(e),
            }
            if result_holder is not None:
                result_holder.append(err_result)
            raise

    def _extract_final_answer(self, messages: list[BaseMessage]) -> str:
        """Extract final answer from messages. When there is a viz tool result, prefer the AI message after it (map/chart summary)."""
        # If there is a create_map/create_chart tool result, prefer the first AI message with content after the last such result
        last_viz_idx = -1
        for i, msg in enumerate(messages):
            if hasattr(msg, "name") and getattr(msg, "name", None) in self.VIZ_TOOLS:
                last_viz_idx = i
        if last_viz_idx >= 0:
            for msg in messages[last_viz_idx + 1 :]:
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
        # Last AI message content (original behavior)
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content

        # Fallback: summarize from tool results
        for msg in reversed(messages):
            if hasattr(msg, "name"):
                try:
                    result = json.loads(msg.content)
                    if result.get("success"):
                        if "chart_json" in result:
                            return f"I've created a {result.get('chart_type', '')} chart: {result.get('title', 'Chart')}"
                        if "map_html" in result:
                            return f"I've created a map: {result.get('title', 'Map')}"
                        if "data" in result:
                            return f"Query returned {result.get('row_count', len(result['data']))} records."
                except:
                    pass

        return "No answer generated"

    def _extract_steps(self, messages: list[BaseMessage]) -> list[dict]:
        """Extract reasoning steps from messages."""
        steps = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                steps.append({"type": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                step = {"type": "assistant", "content": msg.content}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    step["tool_calls"] = [{"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls]
                steps.append(step)
            elif isinstance(msg, ToolMessage):
                steps.append({
                    "type": "tool_result",
                    "tool": msg.name,
                    "content": msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                })
        return steps


# === Factory function ===

def create_agent(
    model_name: str = "llama3.1:8b",
    verbose: bool = True,
    provider: str = "ollama",
    api_key: str | None = None,
    **kwargs
) -> CityGridAgent:
    """Create a CityGrid agent instance. Use provider='openai' for ChatGPT API."""
    return CityGridAgent(
        model_name=model_name,
        verbose=verbose,
        provider=provider,
        api_key=api_key,
        **kwargs,
    )