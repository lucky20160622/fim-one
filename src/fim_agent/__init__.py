"""fim-agent: LLM-powered Agent Runtime with dynamic DAG planning and concurrent execution."""

__version__ = "0.1.0"

from .core.agent import AgentResult, ReActAgent
from .core.model import BaseLLM, ChatMessage, OpenAICompatibleLLM
from .core.planner import DAGExecutor, DAGPlanner, PlanAnalyzer
from .core.tool import BaseTool, Tool, ToolRegistry
from .rag import BaseRetriever, Document

__all__ = [
    "AgentResult",
    "BaseLLM",
    "BaseRetriever",
    "BaseTool",
    "ChatMessage",
    "DAGExecutor",
    "DAGPlanner",
    "Document",
    "OpenAICompatibleLLM",
    "PlanAnalyzer",
    "ReActAgent",
    "Tool",
    "ToolRegistry",
]
