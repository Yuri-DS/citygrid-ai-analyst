"""
LangGraph Agent for CityGrid AI Analyst.

ReAct-style agent that can query the database and analyze results.
"""

from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from datetime import datetime
import json
import re

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import ALL_TOOLS
from agent.prompts import SYSTEM_PROMPT


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

        print()

    def get_logs(self) -> list[dict]:
        return self.logs.copy()

    def clear(self):
        self.logs = []


# === Agent State ===

class AgentState(TypedDict):
    """State of the agent during execution."""
    messages: Annotated[Sequence[BaseMessage], add_messages]


# === Agent Graph ===

class CityGridAgent:
    """
    CityGrid AI Agent using LangGraph.

    Features:
    - ReAct pattern for reasoning + acting
    - Universal tools: agent decides how to use them
    - Separate visualization storage (not sent to LLM to save context)
    """

    # Tools that produce visualizations
    VIZ_TOOLS = {"create_chart", "create_map"}

    def __init__(
        self,
        model_name: str = "llama3.1:8b",
        ollama_base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_iterations: int = 10,
        verbose: bool = True,
    ):
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.logger = AgentLogger(verbose=verbose)
        self.visualizations = []  # Store visualizations separately from messages

        # Initialize LLM with timeout to prevent hanging
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

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph agent graph."""
        graph = StateGraph(AgentState)

        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)

        graph.set_entry_point("agent")
        graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "end": END,
            }
        )
        graph.add_edge("tools", "agent")

        return graph.compile()

    def _agent_node(self, state: AgentState) -> dict:
        """Agent reasoning node."""
        messages = state["messages"]
        last_msg = messages[-1] if messages else None

        self.logger.log("llm_input", {
            "message_count": len(messages),
            "last_message_type": type(last_msg).__name__ if last_msg else None,
        })

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

        # Add system prompt for first message
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            system_message = ("system", SYSTEM_PROMPT)
            chars, tokens = estimate_tokens(messages, SYSTEM_PROMPT)
            self.logger.log("llm_input", {
                "messages_count": len(messages),
                "system_prompt_chars": len(SYSTEM_PROMPT),
                "total_chars": chars,
                "estimated_tokens": tokens,
                "last_message_type": type(messages[-1]).__name__,
            })
            response = self.llm_with_tools.invoke([system_message] + list(messages))
        else:
            chars, tokens = estimate_tokens(messages)
            self.logger.log("llm_input", {
                "messages_count": len(messages),
                "total_chars": chars,
                "estimated_tokens": tokens,
                "last_message_type": type(messages[-1]).__name__,
            })
            response = self.llm_with_tools.invoke(messages)

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

    def _tools_node(self, state: AgentState) -> dict:
        """Execute tool calls and store visualizations separately."""
        messages = state["messages"]
        last_message = messages[-1]
        results = []

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Check if visualization tool called with empty data
                if tool_name in self.VIZ_TOOLS:
                    data_arg = tool_args.get("data", "")
                    is_empty = (data_arg == "" or data_arg == [] or data_arg is None)

                    if is_empty:
                        # Try to get data from previous SQL result
                        sql_data = self._get_last_sql_data(messages)
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
                            # Send short summary to LLM
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
                            # Send short summary to LLM
                            llm_result = {
                                "success": True,
                                "message": f"Map created: {result.get('title', 'Map')}",
                                "items_count": result.get("items_count"),
                                "map_type": result.get("map_type"),
                            }
                            llm_result = {k: v for k, v in llm_result.items() if v is not None}
                        else:
                            llm_result = result

                        llm_result_str = json.dumps(llm_result, ensure_ascii=False)
                        self.logger.log("visualization_stored", {
                            "type": self.visualizations[-1]["type"],
                            "title": self.visualizations[-1]["title"],
                        })
                    else:
                        # Non-visualization tool or error - send full result to LLM
                        llm_result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

                    self.logger.log("tool_result", {
                        "tool_name": tool_name,
                        "result": llm_result_str[:500],
                    })

                    results.append(ToolMessage(
                        content=llm_result_str,
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

        return {"messages": results}

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
        """Decide whether to continue with tools or end."""
        messages = state["messages"]
        last_message = messages[-1]

        # If LLM wants to use tools, continue
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            self.logger.log("decision", {
                "next_step": "tools",
                "reason": f"LLM requested {len(last_message.tool_calls)} tool(s)",
            })
            return "tools"

        self.logger.log("decision", {
            "next_step": "end",
            "reason": "LLM provided final answer",
        })
        return "end"

    def invoke(self, question: str) -> dict:
        """Run the agent on a question."""
        self.logger.clear()
        self.visualizations = []  # Clear visualizations from previous run

        self.logger.log("user_input", {"question": question})

        initial_state = {"messages": [HumanMessage(content=question)]}
        result = self.graph.invoke(initial_state)

        messages = result["messages"]
        final_answer = self._extract_final_answer(messages)

        self.logger.log("final_answer", {"answer": final_answer[:300] if final_answer else ""})

        return {
            "answer": final_answer,
            "messages": messages,
            "visualizations": self.visualizations.copy(),  # Return stored visualizations
            "steps": self._extract_steps(messages),
            "logs": self.logger.get_logs(),
        }

    def _extract_final_answer(self, messages: list[BaseMessage]) -> str:
        """Extract final answer from messages."""
        # Last AI message content
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
    **kwargs
) -> CityGridAgent:
    """Create a CityGrid agent instance."""
    return CityGridAgent(model_name=model_name, verbose=verbose, **kwargs)
