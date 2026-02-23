"""Simple web UI for testing FIM Agent.

Run with:
    uv run python examples/web_ui.py

Then open http://localhost:8000 in your browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

load_dotenv()

from fim_agent.core.agent import ReActAgent
from fim_agent.core.model import OpenAICompatibleLLM
from fim_agent.core.planner import DAGExecutor, DAGPlanner, PlanAnalyzer
from fim_agent.core.tool import ToolRegistry
from fim_agent.core.tool.builtin.python_exec import PythonExecTool

app = FastAPI(title="FIM Agent playground")

# ---------------------------------------------------------------------------
# LLM + Tools setup
# ---------------------------------------------------------------------------

llm = OpenAICompatibleLLM(
    api_key=os.environ.get("LLM_API_KEY", ""),
    base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    model=os.environ.get("LLM_MODEL", "gpt-4o"),
)

registry = ToolRegistry()
registry.register(PythonExecTool())


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(event: str, data: Any) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML_PAGE


@app.get("/api/react")
async def react_endpoint(q: str) -> StreamingResponse:
    """Run a ReAct agent query with SSE progress updates."""

    async def generate():
        t0 = time.time()
        yield _sse("step", {"type": "thinking", "iteration": 0})

        try:
            agent = ReActAgent(llm=llm, tools=registry, max_iterations=20)
            result = await agent.run(q)

            # Replay each step for the UI
            for i, step in enumerate(result.steps, 1):
                if step.action.type == "tool_call":
                    yield _sse(
                        "step",
                        {
                            "type": "tool_call",
                            "iteration": i,
                            "tool_name": step.action.tool_name,
                            "tool_args": step.action.tool_args,
                            "reasoning": step.action.reasoning,
                            "observation": step.observation,
                            "error": step.error,
                        },
                    )

            elapsed = round(time.time() - t0, 2)
            yield _sse(
                "done",
                {
                    "answer": result.answer,
                    "iterations": result.iterations,
                    "elapsed": elapsed,
                },
            )
        except Exception as exc:
            logger.exception("ReAct agent failed")
            elapsed = round(time.time() - t0, 2)
            yield _sse(
                "done",
                {
                    "answer": f"Agent error: {type(exc).__name__}: {exc}",
                    "iterations": 0,
                    "elapsed": elapsed,
                },
            )

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/dag")
async def dag_endpoint(q: str) -> StreamingResponse:
    """Run a DAG planner pipeline with SSE progress updates."""

    async def generate():
        t0 = time.time()

        # Queue bridges the executor's synchronous callback into the async SSE stream.
        progress_queue: asyncio.Queue[str] = asyncio.Queue()

        def on_step_progress(step_id: str, event: str, data: dict) -> None:
            progress_queue.put_nowait(
                _sse("step_progress", {"step_id": step_id, "event": event, **data})
            )

        try:
            # Phase 1: Plan
            yield _sse("phase", {"name": "planning", "status": "start"})
            planner = DAGPlanner(llm=llm)
            plan = await planner.plan(q)
            yield _sse(
                "phase",
                {
                    "name": "planning",
                    "status": "done",
                    "steps": [
                        {"id": s.id, "task": s.task, "deps": s.dependencies, "tool_hint": s.tool_hint}
                        for s in plan.steps
                    ],
                },
            )

            # Phase 2: Execute (with real-time step progress)
            yield _sse("phase", {"name": "executing", "status": "start"})
            agent = ReActAgent(llm=llm, tools=registry, max_iterations=15)
            executor = DAGExecutor(agent=agent, max_concurrency=3)

            # Run executor in a background task so we can drain progress events.
            exec_task = asyncio.create_task(
                executor.execute(plan, on_progress=on_step_progress)
            )

            while not exec_task.done():
                # Drain all queued progress events.
                while not progress_queue.empty():
                    yield progress_queue.get_nowait()
                # Yield a keepalive comment to prevent connection timeout.
                yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

            # Collect the result (re-raises if executor failed).
            plan = exec_task.result()

            # Drain any remaining progress events.
            while not progress_queue.empty():
                yield progress_queue.get_nowait()

            yield _sse(
                "phase",
                {
                    "name": "executing",
                    "status": "done",
                    "results": [
                        {
                            "id": s.id,
                            "task": s.task,
                            "status": s.status,
                            "result": s.result,
                            "started_at": s.started_at,
                            "completed_at": s.completed_at,
                            "duration": s.duration,
                        }
                        for s in plan.steps
                    ],
                },
            )

            # Phase 3: Analyze
            yield _sse("phase", {"name": "analyzing", "status": "start"})
            analyzer = PlanAnalyzer(llm=llm)
            analysis = await analyzer.analyze(plan.goal, plan)
            elapsed = round(time.time() - t0, 2)
            yield _sse(
                "phase",
                {
                    "name": "analyzing",
                    "status": "done",
                    "achieved": analysis.achieved,
                    "confidence": analysis.confidence,
                    "reasoning": analysis.reasoning,
                },
            )

            yield _sse(
                "done",
                {
                    "answer": analysis.final_answer or "(goal not achieved)",
                    "achieved": analysis.achieved,
                    "confidence": analysis.confidence,
                    "elapsed": elapsed,
                },
            )
        except Exception as exc:
            logger.exception("DAG pipeline failed")
            elapsed = round(time.time() - t0, 2)
            yield _sse(
                "done",
                {
                    "answer": f"Pipeline error: {type(exc).__name__}: {exc}",
                    "achieved": False,
                    "confidence": 0.0,
                    "elapsed": elapsed,
                },
            )

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Inline HTML
# ---------------------------------------------------------------------------

HTML_PAGE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FIM Agent - AI Playground</title>
<style>
  :root {
    --bg: #0a0b10;
    --bg-subtle: #0e0f16;
    --surface: #151722;
    --surface-hover: #1a1d2a;
    --border: #232638;
    --border-light: #2e3248;
    --text: #e8e8ec;
    --text-dim: #7c7f95;
    --text-muted: #52556a;
    --accent: #3b82f6;
    --accent-light: #60a5fa;
    --accent-glow: rgba(59, 130, 246, 0.15);
    --accent-glow-strong: rgba(59, 130, 246, 0.3);
    --green: #34d399;
    --green-dim: rgba(52, 211, 153, 0.12);
    --orange: #fb923c;
    --orange-dim: rgba(251, 146, 60, 0.12);
    --red: #f87171;
    --red-dim: rgba(248, 113, 113, 0.12);
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --shadow-card: 0 2px 8px rgba(0,0,0,0.2), 0 1px 3px rgba(0,0,0,0.15);
    --shadow-card-hover: 0 4px 16px rgba(0,0,0,0.3), 0 2px 6px rgba(0,0,0,0.2);
    --shadow-glow: 0 0 20px var(--accent-glow), 0 0 40px rgba(59,130,246,0.05);
    --transition-fast: 0.15s ease;
    --transition-normal: 0.25s ease;
    --transition-slow: 0.4s ease;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }

  /* Custom scrollbar */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--border-light); }

  /* Selection color */
  ::selection { background: var(--accent-glow-strong); color: var(--text); }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    position: relative;
    overflow-x: hidden;
  }

  /* Subtle background pattern */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
      radial-gradient(ellipse 80% 60% at 50% -10%, rgba(59,130,246,0.08) 0%, transparent 60%),
      radial-gradient(ellipse 50% 40% at 80% 50%, rgba(59,130,246,0.03) 0%, transparent 50%),
      radial-gradient(ellipse 50% 40% at 20% 80%, rgba(59,130,246,0.03) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }

  /* Grid dot pattern overlay */
  body::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 24px 24px;
    pointer-events: none;
    z-index: 0;
  }

  .container {
    max-width: 900px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 1.5rem;
    position: relative;
    z-index: 1;
  }

  /* ---- Header ---- */
  header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 2.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
    position: relative;
  }
  .header-logo {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, var(--accent) 0%, #93c5fd 100%);
    border-radius: var(--radius-md);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 2px 12px var(--accent-glow);
  }
  .header-logo svg { width: 24px; height: 24px; }
  .header-text { display: flex; flex-direction: column; gap: 0.15rem; }
  header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--text) 0%, var(--accent-light) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .header-tagline {
    color: var(--text-dim);
    font-size: 0.82rem;
    letter-spacing: 0.02em;
  }
  .header-version {
    margin-left: auto;
    padding: 0.25rem 0.65rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 0.7rem;
    color: var(--text-dim);
    font-weight: 500;
    letter-spacing: 0.03em;
  }

  /* ---- Input area ---- */
  .input-area {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
    margin-bottom: 1.75rem;
    box-shadow: var(--shadow-card);
    transition: border-color var(--transition-normal), box-shadow var(--transition-normal);
    position: relative;
  }
  .input-area:focus-within {
    border-color: rgba(59,130,246,0.4);
    box-shadow: var(--shadow-card), var(--shadow-glow);
  }

  /* ---- Mode tabs ---- */
  .mode-tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
    background: var(--bg);
    padding: 4px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
  }
  .mode-tabs button {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.65rem 1.25rem;
    border-radius: var(--radius-sm);
    border: none;
    background: transparent;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.88rem;
    font-weight: 500;
    transition: all var(--transition-normal);
    position: relative;
  }
  .mode-tabs button:hover {
    color: var(--text);
    background: rgba(255,255,255,0.03);
  }
  .mode-tabs button .mode-icon {
    font-size: 1.05rem;
    line-height: 1;
  }
  .mode-tabs button .mode-desc {
    display: none;
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--text-dim);
    margin-top: 0.1rem;
  }
  .mode-tabs button.active {
    background: var(--accent);
    color: #fff;
    box-shadow: 0 2px 8px var(--accent-glow);
  }
  .mode-tabs button.active .mode-desc {
    color: rgba(255,255,255,0.75);
  }

  @media (min-width: 480px) {
    .mode-tabs button {
      flex-direction: column;
      padding: 0.7rem 1.25rem;
      gap: 0.2rem;
    }
    .mode-tabs button .mode-desc {
      display: block;
    }
  }

  /* ---- Input row ---- */
  .input-row { display: flex; gap: 0.75rem; }
  textarea {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    padding: 0.85rem 1rem;
    font-size: 0.95rem;
    resize: vertical;
    min-height: 60px;
    font-family: inherit;
    transition: border-color var(--transition-normal), box-shadow var(--transition-normal);
    line-height: 1.5;
  }
  textarea::placeholder {
    color: var(--text-muted);
  }
  textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }

  .input-hint {
    margin-top: 0.6rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .input-hint kbd {
    display: inline-block;
    padding: 0.1rem 0.35rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.68rem;
    font-family: inherit;
    color: var(--text-dim);
  }

  .send-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0 1.75rem;
    background: linear-gradient(135deg, var(--accent) 0%, #5b9ef5 100%);
    color: #fff;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-normal);
    white-space: nowrap;
    box-shadow: 0 2px 8px var(--accent-glow);
    min-width: 100px;
  }
  .send-btn .btn-icon {
    font-size: 1.1rem;
    line-height: 1;
    transition: transform var(--transition-normal);
  }
  .send-btn:hover {
    background: linear-gradient(135deg, var(--accent-light) 0%, #6db0f6 100%);
    box-shadow: 0 4px 16px var(--accent-glow-strong);
    transform: translateY(-1px);
  }
  .send-btn:hover .btn-icon { transform: scale(1.15); }
  .send-btn:active { transform: translateY(0); }
  .send-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  /* ---- Output cards ---- */
  #output {
    display: flex; flex-direction: column; gap: 0.85rem;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.1rem 1.35rem;
    animation: fadeIn 0.35s ease;
    box-shadow: var(--shadow-card);
    transition: border-color var(--transition-normal), box-shadow var(--transition-normal);
  }
  .card:hover {
    border-color: var(--border-light);
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .card-header {
    display: flex; align-items: center; gap: 0.6rem;
    margin-bottom: 0.65rem; font-size: 0.8rem;
    color: var(--text-dim);
    letter-spacing: 0.02em; font-weight: 500;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border: 1px solid transparent;
  }
  .badge-tool {
    background: rgba(59,130,246,0.1);
    color: var(--accent-light);
    border-color: rgba(59,130,246,0.2);
  }
  .badge-think {
    background: var(--orange-dim);
    color: var(--orange);
    border-color: rgba(251,146,60,0.2);
  }
  .badge-plan {
    background: var(--green-dim);
    color: var(--green);
    border-color: rgba(52,211,153,0.2);
  }
  .badge-done {
    background: var(--green-dim);
    color: var(--green);
    border-color: rgba(52,211,153,0.2);
  }
  .badge-error {
    background: var(--red-dim);
    color: var(--red);
    border-color: rgba(248,113,113,0.2);
  }
  .badge-step {
    background: rgba(59,130,246,0.12);
    color: var(--accent-light);
    border-color: rgba(59,130,246,0.25);
    font-variant-numeric: tabular-nums;
  }
  .time-badge {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--text-dim);
    background: rgba(255,255,255,0.06);
    padding: 0.15rem 0.5rem;
    border-radius: 9999px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .card-body { font-size: 0.9rem; line-height: 1.65; }
  .card-body pre {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.85rem;
    overflow-x: auto;
    font-size: 0.82rem;
    margin-top: 0.5rem;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .reasoning {
    color: var(--text-dim);
    font-style: italic;
    margin-bottom: 0.5rem;
    padding-left: 0.75rem;
    border-left: 2px solid var(--border-light);
  }

  /* ---- Result card ---- */
  .result-card {
    border-color: rgba(59,130,246,0.4);
    background: linear-gradient(135deg, var(--surface) 0%, rgba(59,130,246,0.06) 50%, rgba(20,30,48,0.8) 100%);
    box-shadow: var(--shadow-card), 0 0 30px var(--accent-glow), 0 0 60px rgba(59,130,246,0.05);
    position: relative;
    overflow: hidden;
  }
  .result-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), #93c5fd, var(--accent));
  }
  .result-card .answer {
    font-size: 1rem; line-height: 1.75;
  }
  .answer pre {
    background: rgba(0,0,0,0.3); padding: 0.85rem; border-radius: var(--radius-sm);
    overflow-x: auto; margin: 0.75rem 0;
    border: 1px solid var(--border);
  }
  .answer code {
    background: rgba(255,255,255,0.08); padding: 0.15rem 0.4rem;
    border-radius: 4px; font-size: 0.88em;
  }
  .answer pre code { background: none; padding: 0; }
  .answer table {
    border-collapse: collapse; width: 100%; margin: 0.75rem 0;
    border-radius: var(--radius-sm);
    overflow: hidden;
  }
  .answer th, .answer td {
    border: 1px solid var(--border); padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
  }
  .answer th {
    background: rgba(255,255,255,0.06); font-weight: 600;
  }
  .answer tr:hover td { background: rgba(255,255,255,0.03); }
  .answer hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
  .answer blockquote {
    border-left: 3px solid var(--accent); padding-left: 0.75rem;
    color: var(--text-dim); margin: 0.5rem 0;
  }
  .answer ul, .answer ol {
    padding-left: 2rem; margin: 0.5rem 0;
  }
  .answer li { margin-bottom: 0.25rem; }
  .meta {
    color: var(--text-dim);
    font-size: 0.78rem;
    margin-top: 0.85rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  /* ---- Spinner ---- */
  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    min-width: 14px;
    min-height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ---- Step grid ---- */
  .step-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem;
    margin-top: 0.6rem;
  }
  .step-item {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.85rem;
    font-size: 0.82rem;
    transition: border-color var(--transition-fast);
  }
  .step-item:hover { border-color: var(--border-light); }
  .step-item .step-deps { margin-top: 0.4rem; font-size: 0.72rem; color: var(--text-dim); font-style: italic; }
  .step-status-completed { color: var(--green); }
  .step-status-failed { color: var(--red); }

  /* ---- Step iteration items (DAG inner ReAct visibility) ---- */
  .step-iterations { margin-top: 0.5rem; }
  .step-iter-item {
    border-left: 2px solid var(--accent);
    margin: 0.4rem 0 0.4rem 0.5rem;
    padding: 0.5rem 0.75rem;
    background: rgba(0,0,0,0.15);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  }
  .iter-header {
    display: flex; align-items: center; gap: 0.5rem;
    font-size: 0.8rem; font-weight: 500; color: var(--text-dim);
    margin-bottom: 0.35rem;
  }
  .step-iter-item .reasoning {
    font-size: 0.8rem; margin-bottom: 0.35rem;
  }
  .step-iter-item pre {
    font-size: 0.78rem; margin: 0.3rem 0;
    padding: 0.5rem; max-height: 200px; overflow-y: auto;
  }

  /* ---- Example chips ---- */
  .examples {
    display: flex; flex-wrap: wrap; gap: 0.5rem;
    margin-top: 1rem;
    padding-top: 0.85rem;
    border-top: 1px solid var(--border);
    position: relative;
  }
  .examples::before {
    content: 'Try an example';
    display: block;
    width: 100%;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 0.15rem;
  }
  .example-chip {
    padding: 0.4rem 0.85rem;
    border-radius: 20px;
    border: 1px solid var(--border);
    background: linear-gradient(135deg, transparent 0%, rgba(59,130,246,0.03) 100%);
    color: var(--text-dim);
    font-size: 0.78rem;
    cursor: pointer;
    transition: all var(--transition-normal);
    line-height: 1.4;
    max-width: 100%;
    text-align: left;
  }
  .example-chip:hover {
    border-color: var(--accent);
    color: var(--accent-light);
    background: linear-gradient(135deg, rgba(59,130,246,0.06) 0%, rgba(59,130,246,0.12) 100%);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px var(--accent-glow);
  }
  .example-chip:active {
    transform: translateY(0);
  }

  /* ---- Footer ---- */
  .site-footer {
    margin-top: 3rem;
    padding: 1.25rem 0;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 0.73rem;
    color: var(--text-muted);
    letter-spacing: 0.02em;
  }
  .site-footer a {
    color: var(--text-dim);
    text-decoration: none;
    transition: color var(--transition-fast);
  }
  .site-footer a:hover { color: var(--accent-light); }
  .footer-dot {
    display: inline-block;
    width: 3px; height: 3px;
    background: var(--text-muted);
    border-radius: 50%;
    margin: 0 0.5rem;
    vertical-align: middle;
  }

  @media (max-width: 640px) {
    .container { padding: 1.5rem 1rem 1rem; }
    .step-grid { grid-template-columns: 1fr; }
    .header-version { display: none; }
    .send-btn { padding: 0 1.25rem; min-width: 80px; }
  }
</style>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark-dimmed.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
</head>
<body>
<div class="container">
  <header>
    <div class="header-logo">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L2 7l10 5 10-5-10-5z" fill="rgba(255,255,255,0.9)"/>
        <path d="M2 17l10 5 10-5" stroke="rgba(255,255,255,0.7)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        <path d="M2 12l10 5 10-5" stroke="rgba(255,255,255,0.85)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      </svg>
    </div>
    <div class="header-text">
      <h1>FIM Agent</h1>
      <span class="header-tagline">Interactive AI playground for reasoning and planning</span>
    </div>
    <span class="header-version">v0.1.0</span>
  </header>

  <div class="input-area">
    <div class="mode-tabs">
      <button id="btn-react" class="active" onclick="setMode('react')">
        <span class="mode-icon">&#9881;</span>
        <span>ReAct Agent</span>
        <span class="mode-desc">Step-by-step reasoning</span>
      </button>
      <button id="btn-dag" onclick="setMode('dag')">
        <span class="mode-icon">&#9670;</span>
        <span>DAG Planner</span>
        <span class="mode-desc">Parallel task execution</span>
      </button>
    </div>
    <div class="input-row">
      <textarea id="query" rows="2" placeholder="Describe a task or ask a question..."></textarea>
      <button class="send-btn" id="send" onclick="run()"><span class="btn-icon">&#9654;</span> Run</button>
    </div>
    <div class="input-hint">
      Press <kbd>Enter</kbd> to run, <kbd>Shift + Enter</kbd> for a new line
    </div>
    <div class="examples" id="examples"></div>
  </div>

  <div id="output"></div>

  <footer class="site-footer">
    Powered by <a href="#">FIM Agent</a>
    <span class="footer-dot"></span>
    Built with FastAPI and Server-Sent Events
  </footer>
</div>

<script>
let mode = 'react';
let running = false;

const EXAMPLES = {
  react: [
    // Probability & statistics — counterintuitive results that need real simulation
    "Simulate the Monty Hall problem 10,000 times — should you switch doors? Show the win rates",
    "Simulate the Birthday Paradox: how often do 2 of 23 people share a birthday? Run 10,000 trials",
    "Estimate pi by throwing 1,000,000 random darts at a unit square — how close can you get?",
    // Algorithms & puzzles — need real computation, LLM alone would fake it
    "Solve the 8-queens puzzle: place 8 queens on a chessboard so none attack each other. How many solutions exist?",
    "Generate a random 15x15 maze and solve it with BFS, show the maze and solution path as ASCII art",
    "Find all Pythagorean triples (a² + b² = c²) where c < 100. How many are there?",
    // Games & simulations — real randomness required
    "Simulate 5,000 hands of Blackjack with basic strategy (hit below 17) — what's the player win rate?",
    "Crack this Caesar cipher: 'Wkh txlfn eurzq ira mxpsv ryhu wkh odcb grj' — try all 26 shifts, score by English letter frequency",
  ],
  dag: [
    // Algorithm races — two implementations built in parallel, then compared
    "Implement bubble sort AND quicksort separately, benchmark both on a 10,000-element random list, then compare their speeds",
    "Implement linear search AND binary search, race both finding 1,000 random targets in a sorted 100,000-element list, then compare total operations",
    // Strategy showdowns — two independent simulations, then compared
    "Simulate 10,000 Monty Hall rounds with always-switch AND 10,000 with always-stay, then compare win rates and explain the paradox",
    "Simulate Martingale betting AND flat-bet strategy over 500 coin flips starting with $1,000 each, then compare who survived longer",
    // Parallel computation — two independent calculations, then combined
    "Estimate pi via Monte Carlo (1M darts) AND via the Leibniz series (1M terms), then compare which method is more accurate",
    "Compute the first 50 Fibonacci numbers AND the first 50 primes, then find which numbers appear in both sequences",
    // Build & test — two components built in parallel, then integrated
    "Write a Caesar cipher encoder AND a brute-force decoder, encode 'ATTACK AT DAWN' with a random shift, then crack it with the decoder",
    "Generate a random 20x20 maze, then solve it using BFS AND DFS in parallel, compare which algorithm explored fewer cells",
  ]
};

function renderExamples() {
  const container = document.getElementById('examples');
  container.innerHTML = '';
  for (const text of EXAMPLES[mode]) {
    const btn = document.createElement('button');
    btn.className = 'example-chip';
    btn.textContent = text;
    btn.onclick = () => {
      document.getElementById('query').value = text;
      run();
    };
    container.appendChild(btn);
  }
}

function setMode(m) {
  mode = m;
  document.getElementById('btn-react').classList.toggle('active', m === 'react');
  document.getElementById('btn-dag').classList.toggle('active', m === 'dag');
  renderExamples();
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatToolArgs(args) {
  // For tool args containing code, show code separately highlighted
  if (args && typeof args === 'object' && typeof args.code === 'string') {
    const code = args.code;
    const rest = Object.assign({}, args);
    delete rest.code;
    const restKeys = Object.keys(rest);
    let highlighted;
    try { highlighted = hljs.highlight(code, { language: 'python' }).value; } catch(e) { highlighted = esc(code); }
    let out = '<pre class="hljs"><code class="language-python">' + highlighted + '</code></pre>';
    if (restKeys.length > 0) {
      out += '<pre>' + esc(JSON.stringify(rest, null, 2)) + '</pre>';
    }
    return out;
  }
  return '<pre>' + esc(JSON.stringify(args, null, 2)) + '</pre>';
}

// Configure marked to use highlight.js
marked.setOptions({
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  }
});

function renderMd(s) {
  if (!s) return '';
  return marked.parse(s);
}

function addCard(html) {
  const out = document.getElementById('output');
  const div = document.createElement('div');
  div.innerHTML = html;
  const card = div.firstElementChild;
  out.appendChild(card);
  // Apply syntax highlighting to all code blocks in this card
  card.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  // Also highlight plain <pre> blocks (tool args) that don't have <code> wrappers
  card.querySelectorAll('pre:not(:has(code))').forEach(el => {
    const text = el.textContent;
    // Auto-detect and highlight if it looks like code
    if (text.length > 20) {
      const result = hljs.highlightAuto(text);
      if (result.relevance > 3) {
        el.innerHTML = result.value;
        el.classList.add('hljs');
      }
    }
  });
  out.scrollTop = out.scrollHeight;
  window.scrollTo(0, document.body.scrollHeight);
}

function removeSpinner() {
  const el = document.getElementById('spinner-card');
  if (el) el.remove();
}

function run() {
  if (running) return;
  const q = document.getElementById('query').value.trim();
  if (!q) return;

  running = true;
  document.getElementById('send').disabled = true;
  document.getElementById('output').innerHTML = '';

  addCard('<div class="card" id="spinner-card"><div class="card-header"><span class="spinner"></span> Running...</div></div>');

  const url = mode === 'react'
    ? '/api/react?q=' + encodeURIComponent(q)
    : '/api/dag?q=' + encodeURIComponent(q);

  const es = new EventSource(url);

  es.addEventListener('step', e => {
    const d = JSON.parse(e.data);
    removeSpinner();

    if (d.type === 'thinking') {
      addCard(`<div class="card" id="spinner-card">
        <div class="card-header"><span class="spinner"></span> Iteration ${d.iteration} &mdash; Thinking...</div>
      </div>`);
    } else if (d.type === 'tool_call') {
      const obs = d.error
        ? `<span class="badge badge-error">ERROR</span><pre>${esc(d.error)}</pre>`
        : `<pre>${esc(d.observation)}</pre>`;
      addCard(`<div class="card">
        <div class="card-header"><span class="badge badge-tool">TOOL</span> Step ${d.iteration} &mdash; ${esc(d.tool_name)}</div>
        <div class="card-body">
          <div class="reasoning">${esc(d.reasoning)}</div>
          ${formatToolArgs(d.tool_args)}
          ${obs}
        </div>
      </div>`);
      addCard(`<div class="card" id="spinner-card">
        <div class="card-header"><span class="spinner"></span> Thinking...</div>
      </div>`);
    } else if (d.type === 'final_answer') {
      // will be shown in 'done' event
    }
  });

  es.addEventListener('step_progress', e => {
    const d = JSON.parse(e.data);
    // Insert into the pre-created slot so steps always appear in plan order
    const slot = document.getElementById('step-slot-' + d.step_id);

    function addToSlot(html) {
      if (slot) {
        slot.insertAdjacentHTML('beforeend', html);
        const added = slot.lastElementChild;
        if (added) added.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
      } else {
        addCard(html);  // fallback
      }
      const out = document.getElementById('output');
      out.scrollTop = out.scrollHeight;
      window.scrollTo(0, document.body.scrollHeight);
    }

    if (d.event === 'started') {
      const startTime = d.started_at ? new Date(d.started_at * 1000).toLocaleTimeString('en-GB', {hour12: false}) : '';
      const timeBadge = startTime ? `<span class="time-badge">${startTime}</span>` : '';
      removeSpinner();
      addToSlot(`<div class="card step-running-card" id="step-running-${esc(d.step_id)}">
        <div class="card-header"><span class="spinner"></span> <span class="badge badge-step">${esc(d.step_id)}</span> ${esc(d.task)}${timeBadge}</div>
        <div class="step-iterations" id="step-iters-${esc(d.step_id)}"></div>
      </div>`);
    } else if (d.event === 'iteration') {
      const container = document.getElementById('step-iters-' + d.step_id);
      if (container) {
        if (d.type === 'tool_call') {
          const obs = d.error
            ? `<span class="badge badge-error">ERROR</span><pre>${esc(d.error)}</pre>`
            : `<pre>${esc(d.observation || '')}</pre>`;
          container.insertAdjacentHTML('beforeend', `<div class="step-iter-item">
            <div class="iter-header"><span class="badge badge-tool">ITER ${d.iteration}</span> ${esc(d.tool_name || '')}</div>
            <div class="reasoning">${esc(d.reasoning || '')}</div>
            ${formatToolArgs(d.tool_args)}
            ${obs}
          </div>`);
          const lastIter = container.lastElementChild;
          if (lastIter) lastIter.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
        }
        const out = document.getElementById('output');
        out.scrollTop = out.scrollHeight;
        window.scrollTo(0, document.body.scrollHeight);
      }
    } else if (d.event === 'completed') {
      const runningEl = document.getElementById('step-running-' + d.step_id);
      if (runningEl) runningEl.remove();
      const cls = d.status === 'completed' ? 'badge-done' : 'badge-error';
      const label = d.status === 'completed' ? 'DONE' : 'FAILED';
      const durBadge = d.duration != null ? `<span class="time-badge">${d.duration}s</span>` : '';
      addToSlot(`<div class="card">
        <div class="card-header"><span class="badge ${cls}">${label}</span> <span class="badge badge-step">${esc(d.step_id)}</span> ${esc(d.task)}${durBadge}</div>
        <div class="card-body"><div class="answer">${renderMd(d.result || '(no result)')}</div></div>
      </div>`);
    }
  });

  es.addEventListener('phase', e => {
    const d = JSON.parse(e.data);
    removeSpinner();

    if (d.status === 'start') {
      const labels = { planning: 'Planning DAG...', executing: 'Executing steps...', analyzing: 'Analyzing results...' };
      addCard(`<div class="card" id="spinner-card">
        <div class="card-header"><span class="spinner"></span> ${labels[d.name] || d.name}</div>
      </div>`);
    } else if (d.name === 'planning' && d.status === 'done') {
      let stepsHtml = '<div class="step-grid">';
      for (const s of d.steps) {
        const depsText = s.deps.length ? s.deps.join(', ') : 'independent';
        stepsHtml += `<div class="step-item"><span class="badge badge-step">${esc(s.id)}</span> ${esc(s.task)}<div class="step-deps">${esc(depsText)}</div></div>`;
      }
      stepsHtml += '</div>';
      addCard(`<div class="card">
        <div class="card-header"><span class="badge badge-plan">PLAN</span> ${d.steps.length} steps generated</div>
        <div class="card-body">${stepsHtml}</div>
      </div>`);
      // Create ordered slot container so steps always appear in plan order
      const slotsDiv = document.createElement('div');
      slotsDiv.id = 'step-slots';
      for (const s of d.steps) {
        const slot = document.createElement('div');
        slot.id = 'step-slot-' + s.id;
        slotsDiv.appendChild(slot);
      }
      document.getElementById('output').appendChild(slotsDiv);
    } else if (d.name === 'executing' && d.status === 'done') {
      // execution summary is already shown per step_progress, just note completion
      addCard(`<div class="card">
        <div class="card-header"><span class="badge badge-done">EXEC</span> All ${d.results.length} steps completed</div>
      </div>`);
    } else if (d.name === 'analyzing' && d.status === 'done') {
      const badge = d.achieved ? 'badge-done' : 'badge-error';
      const label = d.achieved ? 'Goal Achieved' : 'Goal Not Achieved';
      const confPct = (d.confidence * 100).toFixed(0);
      addCard(`<div class="card">
        <div class="card-header"><span class="badge ${badge}">${label}</span> Verification confidence: ${confPct}%</div>
        <div class="card-body"><div class="reasoning">${esc(d.reasoning)}</div></div>
      </div>`);
    }
  });

  es.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    removeSpinner();
    es.close();

    const meta = [];
    if (d.iterations) meta.push(d.iterations + ' iterations');
    if (d.elapsed) meta.push(d.elapsed + 's');
    if (d.confidence !== undefined) meta.push('confidence: ' + (d.confidence * 100).toFixed(0) + '%');

    addCard(`<div class="card result-card">
      <div class="card-header"><span class="badge badge-done">RESULT</span></div>
      <div class="card-body">
        <div class="answer">${renderMd(d.answer)}</div>
        <div class="meta">${meta.join(' &bull; ')}</div>
      </div>
    </div>`);

    running = false;
    document.getElementById('send').disabled = false;
  });

  es.onerror = () => {
    removeSpinner();
    es.close();
    addCard(`<div class="card">
      <div class="card-header"><span class="badge badge-error">ERROR</span></div>
      <div class="card-body">Connection lost or server error.</div>
    </div>`);
    running = false;
    document.getElementById('send').disabled = false;
  };
}

// Enter to send (Shift+Enter for newline)
document.getElementById('query').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    run();
  }
});

// Init
renderExamples();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("Starting FIM Agent playground at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
