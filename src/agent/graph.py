"""
LangGraph Agent for CityGrid AI Analyst.

ReAct-style agent that can query the database and analyze results.
"""

from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import SQL_TOOLS
from agent.prompts import SYSTEM_PROMPT


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
    ):
        self.model_name = model_name
        self.max_iterations = max_iterations
        
        # Initialize LLM
        self.llm = ChatOllama(
            model=model_name,
            base_url=ollama_base_url,
            temperature=temperature,
        )
        
        # Bind tools to LLM
        self.tools = SQL_TOOLS
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Build graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph agent graph."""
        
        # Create graph
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", ToolNode(self.tools))
        
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
        
        # Add system prompt if first message
        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            system_message = ("system", SYSTEM_PROMPT)
            response = self.llm_with_tools.invoke([system_message] + list(messages))
        else:
            response = self.llm_with_tools.invoke(messages)
        
        return {"messages": [response]}
    
    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue with tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If LLM wants to use tools, continue
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        
        # Otherwise, end
        return "end"
    
    def invoke(self, question: str) -> dict:
        """
        Run the agent on a question.
        
        Args:
            question: User's question in natural language
            
        Returns:
            Dict with 'answer', 'messages', and 'steps'
        """
        # Initial state
        initial_state = {
            "messages": [HumanMessage(content=question)]
        }
        
        # Run graph
        result = self.graph.invoke(initial_state)
        
        # Extract answer and steps
        messages = result["messages"]
        steps = self._extract_steps(messages)
        
        # Get final answer
        final_answer = messages[-1].content if messages else "No answer generated"
        
        return {
            "answer": final_answer,
            "messages": messages,
            "steps": steps,
        }
    
    def stream(self, question: str):
        """
        Stream the agent execution step by step.
        
        Args:
            question: User's question in natural language
            
        Yields:
            Dict with current state and step info
        """
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
    **kwargs
) -> CityGridAgent:
    """Create a CityGrid agent instance."""
    return CityGridAgent(model_name=model_name, **kwargs)
