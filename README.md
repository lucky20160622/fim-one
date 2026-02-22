# fim-agent

**LLM-powered Agent Runtime with Dynamic DAG Planning & Concurrent Execution**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

---

## Overview

fim-agent is a lightweight Python framework that lets an LLM dynamically decompose complex goals into directed acyclic graphs (DAGs) and execute them with maximum parallelism.

Traditional workflow engines (Dify, LangGraph, etc.) require developers to hard-code execution graphs at design time. fim-agent takes a different approach: **the LLM decides the execution graph at runtime**. Given a high-level goal, the planner produces a dependency-aware DAG of steps, the executor runs independent steps concurrently, and an analyzer verifies whether the goal was achieved -- re-planning if necessary.

The framework also ships a ReAct agent for single-query tool-use loops and an extensible RAG retriever interface, making it a complete building block for agentic applications.

## Key Features

- **Dynamic DAG Planning** -- An LLM decomposes goals into dependency graphs at runtime. No hard-coded workflows.
- **Concurrent Execution** -- Independent DAG steps run in parallel via `asyncio`, bounded by a configurable concurrency limit.
- **ReAct Agent** -- Structured reasoning-and-acting loop with JSON-based tool calls, automatic error recovery, and iteration limits.
- **OpenAI-Compatible** -- Works with any provider exposing the `/v1/chat/completions` interface (OpenAI, DeepSeek, Qwen, Ollama, vLLM, and others).
- **Pluggable Tool System** -- Protocol-based tool interface with a central registry. Ships with a built-in Python code executor.
- **RAG Ready** -- Abstract `BaseRetriever` / `Document` interface for plugging in vector stores and search backends.
- **Minimal Dependencies** -- Only three runtime dependencies: `openai`, `httpx`, `pydantic`.

## Architecture

```
User Query
    |
    v
+--------------+
|  DAG Planner |  LLM decomposes the goal into steps + dependency edges
+--------------+
    |
    v
+--------------+
| DAG Executor |  Launches independent steps concurrently (asyncio)
|              |  Each step is handled by a ReAct Agent
+--------------+
    |                         +-------+
    +--- ReAct Agent [1] ---> | Tools |  (python_exec, custom, ...)
    |                         +-------+
    +--- ReAct Agent [2] ---> | RAG   |  (retriever interface)
    |                         +-------+
    +--- ReAct Agent [N] ---> | ...   |
    |
    v
+---------------+
| Plan Analyzer |  LLM evaluates results; re-plans if goal not met
+---------------+
    |
    v
 Final Answer
```

## Quick Start

### Installation

```bash
# Using uv (recommended)
uv add fim-agent

# Or install from source
git clone https://github.com/fim-ai/fim-agent.git
cd fim-agent
uv sync
```

### Basic Usage

```python
import asyncio
import os

from fim_agent.core.agent import ReActAgent
from fim_agent.core.model import OpenAICompatibleLLM
from fim_agent.core.tool import ToolRegistry
from fim_agent.core.tool.builtin.python_exec import PythonExecTool


async def main() -> None:
    llm = OpenAICompatibleLLM(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=os.environ.get("LLM_MODEL", "gpt-4o"),
    )

    tools = ToolRegistry()
    tools.register(PythonExecTool())

    agent = ReActAgent(llm=llm, tools=tools)
    result = await agent.run("Calculate the factorial of 10 using Python.")
    print(result.answer)


asyncio.run(main())
```

### DAG Planning

```python
from fim_agent.core.planner import DAGPlanner, DAGExecutor, PlanAnalyzer

planner = DAGPlanner(llm=llm)
plan = await planner.plan("Compare bubble sort vs built-in sorted() on 5000 random ints.")

executor = DAGExecutor(agent=agent, max_concurrency=3)
plan = await executor.execute(plan)

analyzer = PlanAnalyzer(llm=llm)
analysis = await analyzer.analyze(plan.goal, plan)
print(analysis.final_answer)
```

See [`examples/quickstart.py`](examples/quickstart.py) for a complete runnable example.

## Configuration

All configuration is done through environment variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | Yes | -- | API key for the LLM provider |
| `LLM_BASE_URL` | No | `https://api.openai.com/v1` | Base URL of the OpenAI-compatible API |
| `LLM_MODEL` | No | `gpt-4o` | Model identifier to use |
| `LLM_TEMPERATURE` | No | `0.7` | Default sampling temperature |
| `MAX_CONCURRENCY` | No | `5` | Max parallel steps in DAG executor |

Copy `example.env` to `.env` and fill in your values:

```bash
cp example.env .env
```

## Development

```bash
# Install all dependencies (including dev extras)
uv sync --all-extras

# Run tests
pytest

# Run tests with coverage
pytest --cov=fim_agent --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Project Structure

```
fim-agent/
  src/fim_agent/
    core/
      model/          # LLM abstraction (OpenAI-compatible)
      tool/           # Tool protocol, registry, built-in tools
      agent/          # ReAct agent implementation
      planner/        # DAG planner, executor, analyzer
    rag/              # RAG retriever interface
  tests/
  examples/
    quickstart.py     # Runnable quick start example
  pyproject.toml
```

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
