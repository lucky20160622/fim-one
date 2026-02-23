# fim-agent

**LLM-powered Agent Runtime with Dynamic DAG Planning & Concurrent Execution**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-Apache%202.0-green)

---

## Overview

fim-agent is a lightweight Python framework that lets an LLM dynamically decompose complex goals into directed acyclic graphs (DAGs) and execute them with maximum parallelism.

Traditional workflow engines (Dify, LangGraph, etc.) require developers to hard-code execution graphs at design time. fim-agent takes a different approach: **the LLM decides the execution graph at runtime**. Given a high-level goal, the planner produces a dependency-aware DAG of steps, the executor runs independent steps concurrently, and an analyzer verifies whether the goal was achieved -- re-planning if necessary.

The framework also ships a ReAct agent for single-query tool-use loops and an extensible RAG retriever interface, making it a complete building block for agentic applications.

## Philosophy

### Why dynamic planning is the hard middle ground

The AI agent landscape split into two camps, and both picked the easy path. Traditional workflow engines -- Dify, n8n, Coze -- chose static orchestration: visual drag-and-drop flowcharts with fixed execution paths. This was not ignorance; enterprise customers demand determinism (same input, stable output), and static graphs deliver that. On the other extreme, fully autonomous agents (AutoGPT and its descendants) promised end-to-end autonomy but proved impractical: unreliable task decomposition, runaway token costs, and behavior nobody could predict or debug.

The sweet spot is narrow but real. Simple tasks do not need a planner. Tasks complex enough to require dozens of interdependent steps overwhelm current LLMs. But in between lies a rich class of problems -- tasks with clear parallel subtasks that are tedious to hard-code yet tractable for an LLM to decompose. Dynamic DAG planning targets exactly this zone: the model proposes the execution graph at runtime, the framework validates the structure and runs it with maximum concurrency. No drag-and-drop, no YOLO autonomy.

### The bet on improving models

Every few months the foundation shifts -- GPT-4, function calling, Claude 3, the MCP protocol. Building a rigid abstraction on shifting ground is risky; LangChain's over-abstraction is the cautionary tale everyone in this space has internalized. fim-agent takes the opposite approach: **minimal abstraction, maximum extensibility**. The framework owns orchestration, concurrency, and observability. The intelligence comes from the model, and the model keeps getting better.

Today, LLM task decomposition accuracy sits around 70-80% for non-trivial goals. When that reaches 90%+, the "sweet spot" for dynamic planning expands dramatically -- problems that were too complex yesterday become tractable tomorrow. fim-agent's DAG framework is designed to capture that expanding value without rewriting the plumbing.

### Will ReAct and DAG planning become obsolete?

ReAct will not disappear -- it will sink into the model. Consider the analogy: you do not hand-write TCP handshakes, but TCP did not go away; it got absorbed into the operating system. When models are strong enough, the think-act-observe loop becomes implicit behavior inside the model, not explicit framework code. This is already happening: Claude Code is essentially a ReAct agent where the loop is driven by the model itself, not by an external harness.

DAG planning's lasting value is not "helping dumb models decompose tasks" -- it is **concurrent scheduling**. Even with infinitely capable models, physics imposes latency: a serial chain of 10 LLM calls takes 10x longer than 3 parallel waves. DAG is an engineering problem (how to run things fast and reliably), not an intelligence problem (how to decide what to run). Retry logic, cost control, timeout management, observability -- these do not go away when models get smarter.

The endgame: **models own the "what" (planning intelligence internalizes into the model), frameworks own the "how" (concurrency, retry, monitoring, cost governance)**. A framework's lasting value is not intelligence -- it is governance.

### Four kinds of "planning" in the AI tooling landscape

The word "planning" is overloaded. At least four distinct approaches exist today, and they solve different problems:

| Approach | Plan format | Execution | Approval | Core value |
|---|---|---|---|---|
| **Implicit model planning** | Internal chain-of-thought | Single inference pass | None | The model thinks through steps on its own |
| **Claude Code plan mode** | Markdown document | Serial | Human reviews before execution | Align on approach before touching code |
| **Kiro spec-driven dev** | Structured spec (requirements + design + tasks) | Serial | Human reviews spec | Traceable requirements, acceptance criteria |
| **fim-agent DAG** | JSON dependency graph | **Concurrent** | Automatic (PlanAnalyzer) | Parallel execution + runtime scheduling |

The first three are **design-time** planning -- they produce a plan *before* work begins, and a human (or the model itself) follows it step by step. fim-agent's DAG is **runtime** planning -- the execution graph is generated, validated, and scheduled programmatically, with independent branches running in parallel.

These approaches are not competitors; they are complementary layers. A Kiro-style spec can define *what* to build, while a fim-agent DAG can schedule *how* to execute the subtasks concurrently. Claude Code's plan mode ensures a human agrees with the approach; fim-agent's PlanAnalyzer verifies the outcome automatically.

### Where fim-agent stands

fim-agent is not an "AGI task scheduler" and not a static workflow engine. It occupies the middle ground: planning capability with constraints, concurrency with observability.

- Compared to **Dify**: more flexible -- runtime DAG generation vs. design-time flowcharts. You do not need to anticipate every execution path in advance.
- Compared to **AutoGPT**: more controlled -- bounded iterations, re-planning limits, with human-in-the-loop on the roadmap. Autonomy within guardrails.

The strategy is straightforward: build the orchestration framework now, and let improving models fill it with capability over time.

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

### Web UI Playground

```bash
# Install web dependencies
uv sync --extra web

# Create .env with your LLM credentials
cp example.env .env
# Edit .env with your API key

# Start the playground
uv run python examples/web_ui.py
```

Then open http://localhost:8000 -- two modes available: **ReAct Agent** (single-query tool loop) and **DAG Planner** (multi-step planning with concurrent execution).

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

## Roadmap

> Goal: Build a complete **Dify alternative** -- from agent runtime to visual workflow builder.

### v0.2 -- Core Enhancements

- [ ] **Native Function Calling**: Support OpenAI-style `tool_choice` / `parallel_tool_calls` alongside the ReAct JSON mode
- [ ] **Streaming Agent Output**: Yield intermediate reasoning and tool results as they happen via `AsyncIterator`
- [ ] **Conversation Memory**: Short-term message window + long-term summary (LanceDB) for multi-turn agent sessions
- [ ] **Retry & Fallback**: Configurable retry policies for LLM calls and tool executions with exponential backoff
- [ ] **Multi-Model Support**: Configure multiple LLMs per project (general / fast / vision / compact), switch per step

### v0.3 -- Rich Tool Ecosystem

- [ ] **Built-in Tools**: Calculator, file ops, web search, browser automation, image understanding/generation
- [ ] **MCP Integration**: Model Context Protocol server management for dynamic tool discovery and invocation
- [ ] **Tool Categories & Permissions**: Group tools by category, enable/disable per agent
- [ ] **Skill System**: Reusable prompt-based skills that agents can compose

### v0.4 -- RAG & Knowledge

- [ ] **Vector Store Retrievers**: Built-in implementations for LanceDB, FAISS, Chroma, and Milvus
- [ ] **Hybrid Retrieval**: Combine dense vector search with BM25 sparse retrieval
- [ ] **Knowledge Base Management**: Create, upload, search, and manage multiple knowledge bases
- [ ] **Document Loaders**: File parsers for PDF, Markdown, HTML, DOCX, and CSV
- [ ] **Chunking Strategies**: Fixed-size, recursive, and semantic chunking out of the box

### v0.5 -- Agent Builder & Marketplace

- [ ] **Agent Builder**: Visual UI to create custom agents -- set instructions, pick model, attach knowledge bases, configure tools
- [ ] **Agent Publishing**: Draft / published lifecycle, share agents with teammates
- [ ] **Agent Templates**: Pre-built agent templates for common use cases (code assistant, research, data analysis)
- [ ] **Text2SQL Agent**: Specialized agent that connects to databases and generates SQL from natural language
- [ ] **Vibe Mode**: Alternative creative execution mode for open-ended exploration tasks

### v0.6 -- Multi-Agent Collaboration

- [ ] **Agent Roles**: Define specialized agents (researcher, coder, reviewer) within a single DAG plan
- [ ] **Inter-Agent Messaging**: Shared context bus for agents to exchange intermediate results
- [ ] **Human-in-the-Loop**: Approval gates and intervention points in DAG steps for high-stakes decisions
- [ ] **Agent Delegation**: Allow agents to spawn sub-agents for nested task decomposition
- [ ] **Task Pause / Resume**: Persist and resume long-running agent tasks

### v0.7 -- Production Platform

- [ ] **User Management**: Multi-user with JWT auth, role-based permissions, workspace isolation
- [ ] **Persistent Storage**: SQLAlchemy ORM with PostgreSQL / SQLite for tasks, agents, and execution history
- [ ] **File Workspace**: Per-task file management -- upload, download, preview, input/output directories
- [ ] **WebSocket Communication**: Real-time bi-directional streaming replacing SSE for richer interaction
- [ ] **DAG Visualization**: Interactive Dagre/XYFlow graph rendering of execution plans

### v0.8 -- Observability & Operations

- [ ] **OpenTelemetry Traces**: Structured tracing for every LLM call, tool execution, and DAG step
- [ ] **Token & Cost Tracking**: Token usage aggregation across planning, execution, and analysis rounds
- [ ] **Monitoring Dashboard**: Task history, execution metrics, performance analytics
- [ ] **Rate Limiting**: Token-aware rate limiter respecting provider quotas
- [ ] **Execution Replay**: Historical trace replay for debugging and auditing

### v0.9 -- Workflow Engine (Dify Parity)

- [ ] **Visual Workflow Editor**: Drag-and-drop node-based workflow builder (like Dify / n8n)
- [ ] **Workflow Templates**: Pre-built workflow templates for common patterns (chatbot, RAG pipeline, data processing)
- [ ] **Conditional Branching**: If/else nodes, switch nodes, loop nodes in visual workflows
- [ ] **Variable System**: Global and step-scoped variables with type validation
- [ ] **Trigger System**: HTTP webhook, scheduled cron, and event-based workflow triggers
- [ ] **Workflow Versioning**: Version control for published workflows with rollback support

### v1.0 -- Ecosystem & Enterprise

- [ ] **Plugin System**: Pip-installable tool / retriever / agent packages with auto-registration
- [ ] **Full Web UI**: Next.js dashboard with agent marketplace, task management, and workflow editor
- [ ] **Docker Deployment**: Production-ready Docker Compose with PostgreSQL, Redis, and worker processes
- [ ] **REST & SSE API**: Complete HTTP API for programmatic access to all platform features
- [ ] **Benchmarks**: Standardized evaluation suite against SWE-bench, HotpotQA, and custom enterprise tasks
- [ ] **i18n**: Multi-language support for UI and agent prompts (Chinese, English, Japanese)

Contributions and ideas are welcome -- open an issue or submit a PR on [GitHub](https://github.com/fim-ai/fim-agent).

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
