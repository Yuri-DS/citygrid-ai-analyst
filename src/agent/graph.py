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
            print(f"Messages count: {data.get('message_count', 0)}")
            print(f"Last message type: {data.get('last_message_type', '')}")
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
        elif event_type == "auto_visualization":
            print(f"Auto-creating: {data.get('tool', '')} for {data.get('reason', '')}")

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
    - Auto-visualization when LLM forgets to call chart/map tools
    """

    def __init__(
        self,
        model_name: str = "llama3.1:8b",
        ollama_base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_iterations: int = 15,
        verbose: bool = True,
    ):
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.logger = AgentLogger(verbose=verbose)
        self.original_question = ""  # Store for auto-visualization logic

        # Initialize LLM
        self.llm = ChatOllama(
            model=model_name,
            base_url=ollama_base_url,
            temperature=temperature,
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

        # Add system prompt for first message
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            system_message = ("system", SYSTEM_PROMPT)
            response = self.llm_with_tools.invoke([system_message] + list(messages))
        else:
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

        return {"messages": [response]}

    def _tools_node(self, state: AgentState) -> dict:
        """Execute tool calls."""
        messages = state["messages"]
        last_message = messages[-1]
        results = []

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                self.logger.log("tool_call", {
                    "tool_name": tool_name,
                    "arguments": tool_args,
                })

                tool_fn = self.tools_by_name.get(tool_name)

                if tool_fn:
                    result = tool_fn.invoke(tool_args)
                    result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

                    self.logger.log("tool_result", {
                        "tool_name": tool_name,
                        "result": result_str[:500],
                    })

                    results.append(ToolMessage(
                        content=result_str,
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

        # Check if we should auto-create visualization
        auto_viz = self._check_auto_visualization(state)
        if auto_viz:
            self.logger.log("auto_visualization", {
                "tool": auto_viz["name"],
                "reason": "User asked for visualization but LLM didn't create it"
            })
            # Inject tool call
            last_message.tool_calls = [auto_viz]
            return "tools"

        self.logger.log("decision", {
            "next_step": "end",
            "reason": "LLM provided final answer",
        })
        return "end"

    def _check_auto_visualization(self, state: AgentState) -> dict | None:
        """
        Check if we should automatically create a visualization.

        Returns tool call dict if yes, None if no.
        """
        messages = state["messages"]

        # Check if user wanted visualization
        viz_type = self._detect_visualization_intent(self.original_question)
        if not viz_type:
            return None

        # Check if visualization was already created
        viz_tools = {"create_chart", "create_district_map", "create_points_map", "create_road_map"}
        for msg in messages:
            if hasattr(msg, "name") and msg.name in viz_tools:
                return None  # Already done

        # Find SQL result data
        sql_data = None
        for msg in reversed(messages):
            if hasattr(msg, "name") and msg.name == "execute_sql":
                try:
                    result = json.loads(msg.content)
                    if result.get("success") and result.get("data"):
                        sql_data = result["data"]
                        break
                except:
                    pass

        if not sql_data:
            return None

        # Build auto visualization call
        return self._build_auto_viz_call(sql_data, viz_type, self.original_question)

    def _detect_visualization_intent(self, question: str) -> str | None:
        """Detect if user wants chart or map."""
        q = question.lower()

        # Explicit chart types
        if any(kw in q for kw in ["bar chart", "pie chart", "line chart", "histogram", "scatter"]):
            return "chart"

        # Map keywords
        if any(kw in q for kw in ["on a map", "on map", "show map", "display map"]):
            return "map"

        # Generic visualization words
        if any(kw in q for kw in ["chart", "graph", "plot", "visualize"]):
            return "chart"

        # "show" with data context (not just "show me the data")
        if "show" in q and not any(kw in q for kw in ["show me the data", "show data", "show the data"]):
            if any(kw in q for kw in ["distribution", "by", "per", "across"]):
                return "chart"

        return None

    def _build_auto_viz_call(self, data: list[dict], viz_type: str, question: str) -> dict:
        """Build automatic visualization tool call."""
        if not data:
            return None

        columns = list(data[0].keys())
        q = question.lower()

        if viz_type == "map":
            # Check for coordinates
            if "center_lat" in columns and "center_lon" in columns:
                value_col = next((c for c in columns if c not in ["name", "center_lat", "center_lon", "type", "district_id"]), "population")
                return {
                    "name": "create_district_map",
                    "args": {"data": data, "value_column": value_col, "title": "Districts Map"},
                    "id": "auto_map"
                }
            lat_cols = [c for c in columns if "lat" in c.lower()]
            lon_cols = [c for c in columns if "lon" in c.lower()]
            if lat_cols and lon_cols:
                return {
                    "name": "create_points_map",
                    "args": {"data": data, "lat_column": lat_cols[0], "lon_column": lon_cols[0], "title": "Points Map"},
                    "id": "auto_points_map"
                }

        # Chart - find x (categorical) and y (numeric) columns
        x_col, y_col = None, None
        for col in columns:
            sample = data[0].get(col)
            if isinstance(sample, str) and not x_col:
                x_col = col
            elif isinstance(sample, (int, float)) and not y_col:
                y_col = col

        if not (x_col and y_col):
            return None

        # Determine chart type
        if "pie" in q or "distribution" in q:
            chart_type = "pie"
        elif "line" in q or "trend" in q or "over time" in q:
            chart_type = "line"
        elif "scatter" in q:
            chart_type = "scatter"
        else:
            chart_type = "bar"

        title = f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}"

        return {
            "name": "create_chart",
            "args": {
                "data": data,
                "chart_type": chart_type,
                "x_column": x_col,
                "y_column": y_col,
                "title": title
            },
            "id": "auto_chart"
        }

    def invoke(self, question: str) -> dict:
        """Run the agent on a question."""
        self.logger.clear()
        self.original_question = question  # Store for auto-viz

        self.logger.log("user_input", {"question": question})

        initial_state = {"messages": [HumanMessage(content=question)]}
        result = self.graph.invoke(initial_state)

        messages = result["messages"]
        final_answer = self._extract_final_answer(messages)

        self.logger.log("final_answer", {"answer": final_answer[:300] if final_answer else ""})

        return {
            "answer": final_answer,
            "messages": messages,
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