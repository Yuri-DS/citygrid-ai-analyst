"""
LangGraph Agent for CityGrid AI Analyst.

ReAct-style agent that can query the database and analyze results.
"""

from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from datetime import datetime
import json

import sys
from pathlib import Path

# Add src to path
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
            if data.get('last_message_content'):
                content = data['last_message_content']
                if len(content) > 500:
                    content = content[:500] + "..."
                print(f"Last message: {content}")

        elif event_type == "llm_output":
            print(f"Response type: {data.get('response_type', '')}")
            if data.get('content'):
                content = data['content']
                if len(content) > 500:
                    content = content[:500] + "..."
                print(f"Content: {content}")
            if data.get('tool_calls'):
                print(f"Tool calls: {json.dumps(data['tool_calls'], indent=2, ensure_ascii=False)}")

        elif event_type == "tool_call":
            print(f"Tool: {data.get('tool_name', '')}")
            print(f"Arguments: {json.dumps(data.get('arguments', {}), indent=2, ensure_ascii=False)}")

        elif event_type == "tool_result":
            print(f"Tool: {data.get('tool_name', '')}")
            result = data.get('result', '')
            if isinstance(result, str) and len(result) > 500:
                result = result[:500] + "..."
            print(f"Result: {result}")

        elif event_type == "decision":
            print(f"Next step: {data.get('next_step', '')}")
            print(f"Reason: {data.get('reason', '')}")

        elif event_type == "final_answer":
            print(f"Answer: {data.get('answer', '')}")

        print()

    def get_logs(self) -> list[dict]:
        """Get all logs."""
        return self.logs.copy()

    def clear(self):
        """Clear logs."""
        self.logs = []


# === Agent State ===

class AgentState(TypedDict):
    """State of the agent during execution."""
    messages: Annotated[Sequence[BaseMessage], add_messages]


# === Agent Graph ===

class CityGridAgent:
    """
    CityGrid AI Agent using LangGraph.

    Implements ReAct pattern: Reasoning + Acting in a loop.
    """

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

        # Initialize LLM
        self.llm = ChatOllama(
            model=model_name,
            base_url=ollama_base_url,
            temperature=temperature,
        )

        # Bind tools to LLM
        self.tools = ALL_TOOLS
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph agent graph."""

        # Create graph
        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)

        # Add edges
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
        """Agent reasoning node - decides what to do next."""
        messages = state["messages"]

        # Log input to LLM
        last_msg = messages[-1] if messages else None
        self.logger.log("llm_input", {
            "message_count": len(messages),
            "last_message_type": type(last_msg).__name__ if last_msg else None,
            "last_message_content": last_msg.content if last_msg else None,
        })

        # Add system prompt if first message
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            system_message = ("system", SYSTEM_PROMPT)
            response = self.llm_with_tools.invoke([system_message] + list(messages))
        else:
            response = self.llm_with_tools.invoke(messages)

        # FALLBACK: If no tool_calls but JSON in content, try to parse it
        if not (hasattr(response, "tool_calls") and response.tool_calls):
            extracted_call = self._extract_tool_call_from_text(response.content)
            if extracted_call:
                self.logger.log("fallback_parse", {
                    "message": "Extracted tool call from text",
                    "tool": extracted_call["name"]
                })
                # Create new AIMessage with proper tool_calls
                response = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": extracted_call["name"],
                        "args": extracted_call["args"],
                        "id": f"fallback_{extracted_call['name']}"
                    }]
                )

        # Log LLM output
        tool_calls = None
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                {"name": tc["name"], "args": tc["args"]}
                for tc in response.tool_calls
            ]

        self.logger.log("llm_output", {
            "response_type": type(response).__name__,
            "content": response.content,
            "tool_calls": tool_calls,
        })

        return {"messages": [response]}

    def _extract_tool_call_from_text(self, content: str) -> dict | None:
        """
        Try to extract tool call from text if LLM wrote JSON instead of calling tool.

        Handles formats like:
        - {"name": "execute_sql", "parameters": {"query": "..."}}
        - {"name": "search_documentation", "parameters": {"query": "..."}}
        """
        if not content:
            return None

        import re

        # Look for JSON patterns in text
        # Pattern 1: {"name": "tool_name", "parameters": {...}}
        pattern = r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"parameters"\s*:\s*(\{[^}]+\})\s*\}'

        matches = re.findall(pattern, content, re.DOTALL)

        if matches:
            # Take the first match (or last for multi-step plans)
            tool_name, params_str = matches[-1]  # Last one is usually the action to take

            try:
                params = json.loads(params_str)

                # Only extract known tools
                known_tools = {
                    "execute_sql", "search_documentation", "get_schema", "get_table_sample",
                    "create_chart", "suggest_chart_type",
                    "create_district_map", "create_points_map", "create_road_map"
                }
                if tool_name in known_tools:
                    return {
                        "name": tool_name,
                        "args": params
                    }
            except json.JSONDecodeError:
                pass

        # Pattern 2: Try to find execute_sql with query directly
        sql_pattern = r'"query"\s*:\s*"([^"]+)"'
        sql_match = re.search(sql_pattern, content)
        if sql_match and "execute_sql" in content.lower():
            return {
                "name": "execute_sql",
                "args": {"query": sql_match.group(1)}
            }

        return None

    def _tools_node(self, state: AgentState) -> dict:
        """Execute tools and log results."""
        messages = state["messages"]
        last_message = messages[-1]

        results = []

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Log tool call
                self.logger.log("tool_call", {
                    "tool_name": tool_name,
                    "arguments": tool_args,
                })

                # Find and execute tool
                tool_fn = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        tool_fn = tool
                        break

                if tool_fn:
                    result = tool_fn.invoke(tool_args)

                    # Log result
                    result_str = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                    self.logger.log("tool_result", {
                        "tool_name": tool_name,
                        "result": result_str[:1000],  # Truncate for logging
                    })

                    results.append(ToolMessage(
                        content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                        name=tool_name,
                        tool_call_id=tool_call["id"],
                    ))
                else:
                    error_msg = f"Tool not found: {tool_name}"
                    self.logger.log("tool_result", {
                        "tool_name": tool_name,
                        "result": error_msg,
                    })
                    results.append(ToolMessage(
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=tool_call["id"],
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

        # Otherwise, end
        self.logger.log("decision", {
            "next_step": "end",
            "reason": "LLM provided final answer",
        })
        return "end"

    def invoke(self, question: str) -> dict:
        """
        Run the agent on a question.

        Args:
            question: User's question in natural language

        Returns:
            Dict with 'answer', 'messages', 'steps', and 'logs'
        """
        # Clear previous logs
        self.logger.clear()

        # Log user input
        self.logger.log("user_input", {"question": question})

        # Initial state
        initial_state = {
            "messages": [HumanMessage(content=question)]
        }

        # Run graph
        result = self.graph.invoke(initial_state)

        # Extract answer and steps
        messages = result["messages"]
        steps = self._extract_steps(messages)

        # Get final answer with fallback logic
        final_answer = self._extract_final_answer(messages, question)

        # Log final answer
        self.logger.log("final_answer", {"answer": final_answer[:500] if final_answer else ""})

        return {
            "answer": final_answer,
            "messages": messages,
            "steps": steps,
            "logs": self.logger.get_logs(),
        }

    def _extract_final_answer(self, messages: list[BaseMessage], question: str) -> str:
        """Extract final answer with fallback for empty responses."""
        # Try to get answer from last message
        if messages and hasattr(messages[-1], 'content') and messages[-1].content:
            return messages[-1].content

        # Fallback: Look for last meaningful content
        # Check if there's SQL result data that can be summarized
        last_tool_result = None
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                try:
                    result = json.loads(msg.content)
                    if result.get("success") and result.get("data"):
                        last_tool_result = result
                        break
                except:
                    pass

        # If we have data but no answer, generate a summary
        if last_tool_result:
            data = last_tool_result["data"]
            row_count = last_tool_result.get("row_count", len(data))

            # Check if visualization was requested
            q_lower = question.lower()
            if any(word in q_lower for word in ["chart", "plot", "graph", "map", "show", "visualize", "display"]):
                return f"I retrieved {row_count} records. However, I couldn't create the visualization. Here's the data summary: {json.dumps(data[:5], indent=2)}" + ("..." if row_count > 5 else "")
            else:
                # Simple data response
                if row_count == 1 and len(data[0]) == 1:
                    # Single value
                    value = list(data[0].values())[0]
                    return f"The result is: {value}"
                else:
                    return f"Query returned {row_count} records:\n{json.dumps(data[:10], indent=2)}" + ("..." if row_count > 10 else "")

        return "No answer generated"

    def stream(self, question: str):
        """
        Stream the agent execution step by step.

        Args:
            question: User's question in natural language

        Yields:
            Dict with current state and step info
        """
        self.logger.clear()
        self.logger.log("user_input", {"question": question})

        initial_state = {
            "messages": [HumanMessage(content=question)]
        }

        for event in self.graph.stream(initial_state):
            yield event

    def _extract_steps(self, messages: list[BaseMessage]) -> list[dict]:
        """Extract reasoning steps from message history."""
        steps = []

        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                steps.append({
                    "type": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                step = {
                    "type": "assistant",
                    "content": msg.content
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    step["tool_calls"] = [
                        {"name": tc["name"], "args": tc["args"]}
                        for tc in msg.tool_calls
                    ]
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