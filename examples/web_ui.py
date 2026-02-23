"""Simple web UI for testing fim-agent.

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

app = FastAPI(title="fim-agent playground")

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
            agent = ReActAgent(llm=llm, tools=registry, max_iterations=8)
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
<title>fim-agent playground</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e4e4e7;
    --text-dim: #8b8d98;
    --accent: #6366f1;
    --accent-light: #818cf8;
    --green: #34d399;
    --orange: #fb923c;
    --red: #f87171;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  .container { max-width: 860px; margin: 0 auto; padding: 2rem 1.5rem; }
  header {
    display: flex; align-items: center; gap: 0.75rem;
    margin-bottom: 2rem;
  }
  header h1 { font-size: 1.5rem; font-weight: 600; }
  header span { color: var(--text-dim); font-size: 0.85rem; }

  .input-area {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
  }
  .mode-tabs {
    display: flex; gap: 0.5rem; margin-bottom: 1rem;
  }
  .mode-tabs button {
    padding: 0.4rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
  }
  .mode-tabs button.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }
  .input-row { display: flex; gap: 0.75rem; }
  textarea {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 0.75rem 1rem;
    font-size: 0.95rem;
    resize: vertical;
    min-height: 56px;
    font-family: inherit;
  }
  textarea:focus { outline: none; border-color: var(--accent); }
  .send-btn {
    padding: 0 1.5rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
  }
  .send-btn:hover { background: var(--accent-light); }
  .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  #output {
    display: flex; flex-direction: column; gap: 0.75rem;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    animation: fadeIn 0.3s ease;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .card-header {
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 0.5rem; font-size: 0.8rem;
    color: var(--text-dim); text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .badge {
    display: inline-block; padding: 0.15rem 0.5rem;
    border-radius: 4px; font-size: 0.75rem; font-weight: 500;
  }
  .badge-tool { background: #1e293b; color: var(--accent-light); }
  .badge-think { background: #1a1a2e; color: var(--orange); }
  .badge-plan { background: #0f2922; color: var(--green); }
  .badge-done { background: #1a2e1a; color: var(--green); }
  .badge-error { background: #2e1a1a; color: var(--red); }

  .card-body { font-size: 0.9rem; line-height: 1.6; }
  .card-body pre {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem;
    overflow-x: auto;
    font-size: 0.82rem;
    margin-top: 0.5rem;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .reasoning { color: var(--text-dim); font-style: italic; margin-bottom: 0.4rem; }

  .result-card {
    border-color: var(--accent);
    background: linear-gradient(135deg, var(--surface) 0%, #1a1a2e 100%);
  }
  .result-card .answer {
    font-size: 1rem; line-height: 1.7;
    white-space: pre-wrap;
  }
  .meta { color: var(--text-dim); font-size: 0.8rem; margin-top: 0.75rem; }

  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .step-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .step-item {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.82rem;
  }
  .step-item .step-id { color: var(--accent-light); font-weight: 600; }
  .step-item .step-deps { color: var(--text-dim); font-size: 0.75rem; }
  .step-status-completed { color: var(--green); }
  .step-status-failed { color: var(--red); }

  .examples {
    display: flex; flex-wrap: wrap; gap: 0.5rem;
    margin-top: 0.75rem;
  }
  .example-chip {
    padding: 0.35rem 0.75rem;
    border-radius: 20px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-dim);
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .example-chip:hover {
    border-color: var(--accent);
    color: var(--accent-light);
    background: rgba(99,102,241,0.08);
  }

  @media (max-width: 640px) {
    .step-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>fim-agent</h1>
    <span>playground</span>
  </header>

  <div class="input-area">
    <div class="mode-tabs">
      <button id="btn-react" class="active" onclick="setMode('react')">ReAct Agent</button>
      <button id="btn-dag" onclick="setMode('dag')">DAG Planner</button>
    </div>
    <div class="input-row">
      <textarea id="query" rows="2" placeholder="Ask anything..."></textarea>
      <button class="send-btn" id="send" onclick="run()">Run</button>
    </div>
    <div class="examples" id="examples"></div>
  </div>

  <div id="output"></div>
</div>

<script>
let mode = 'react';
let running = false;

const EXAMPLES = {
  react: [
    "Write Python to generate a random 4x4 matrix and compute its determinant",
    "Run a script that counts how many days until Christmas 2026",
    "Write a haiku about programming, then translate it to Chinese",
    "What are the SOLID principles in software engineering? Explain each in one sentence",
    "Write Python to simulate rolling 2 dice 1000 times and report the most common sum",
    "Generate a random strong password of 16 characters and check if it meets common security rules",
    "Compare TCP and UDP protocols in a simple table format",
    "Write Python code to check if 'racecar', 'hello', and 'madam' are palindromes",
  ],
  dag: [
    "Calculate 15! and 20!, then tell me which one has more digits",
    "Find the area of a circle with radius 7 and volume of a sphere with radius 7, then compare which is larger",
    "Count the words in 'To be or not to be that is the question' and count characters (no spaces), then report both",
    "List 3 advantages of Python and 3 advantages of Rust, then write a summary comparing them",
    "Generate a random 6-digit number and check divisibility by 3, 7, and 11, then summarize",
    "Write a function to reverse a string AND a function to check palindromes, then test both with 'racecar'",
    "Explain Docker in 2 sentences AND Kubernetes in 2 sentences, then explain how they work together",
    "Calculate sum of 1-100 using n*(n+1)/2 and also by adding with Python, then verify they match",
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

function renderMd(s) {
  if (!s) return '';
  let h = esc(s);
  // code blocks
  h = h.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre>$2</pre>');
  // inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  // bold
  h = h.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
  // headers
  h = h.replace(/^### (.+)$/gm, '<strong style="font-size:1rem">$1</strong>');
  h = h.replace(/^## (.+)$/gm, '<strong style="font-size:1.05rem">$1</strong>');
  // lists
  h = h.replace(/^[\\-\\*] (.+)$/gm, '&bull; $1');
  h = h.replace(/^(\\d+)\\. (.+)$/gm, '$1. $2');
  // newlines
  h = h.replace(/\\n/g, '<br>');
  return h;
}

function addCard(html) {
  const out = document.getElementById('output');
  const div = document.createElement('div');
  div.innerHTML = html;
  out.appendChild(div.firstElementChild);
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
          <pre>${esc(JSON.stringify(d.tool_args, null, 2))}</pre>
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
    removeSpinner();

    if (d.event === 'started') {
      const startTime = d.started_at ? new Date(d.started_at * 1000).toLocaleTimeString('en-GB', {hour12: false}) : '';
      const timeInfo = startTime ? ` (started at ${startTime})` : '';
      addCard(`<div class="card" id="spinner-card">
        <div class="card-header"><span class="spinner"></span> Running <strong>${esc(d.step_id)}</strong>: ${esc(d.task)}${timeInfo}</div>
      </div>`);
    } else if (d.event === 'completed') {
      const cls = d.status === 'completed' ? 'badge-done' : 'badge-error';
      const label = d.status === 'completed' ? 'DONE' : 'FAILED';
      const durInfo = d.duration != null ? ` (${d.duration}s)` : '';
      addCard(`<div class="card">
        <div class="card-header"><span class="badge ${cls}">${label}</span> ${esc(d.step_id)}: ${esc(d.task)}${durInfo}</div>
        <div class="card-body"><pre>${esc(d.result || '(no result)')}</pre></div>
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
        const deps = s.deps.length ? 'depends: ' + s.deps.join(', ') : 'no deps';
        stepsHtml += `<div class="step-item"><span class="step-id">${esc(s.id)}</span> ${esc(s.task)}<br><span class="step-deps">${deps}</span></div>`;
      }
      stepsHtml += '</div>';
      addCard(`<div class="card">
        <div class="card-header"><span class="badge badge-plan">PLAN</span> ${d.steps.length} steps generated</div>
        <div class="card-body">${stepsHtml}</div>
      </div>`);
    } else if (d.name === 'executing' && d.status === 'done') {
      let resHtml = '<div class="step-grid">';
      for (const s of d.results) {
        const durLabel = s.duration != null ? ` (${s.duration}s)` : '';
        resHtml += `<div class="step-item">
          <span class="step-id">${esc(s.id)}</span>
          <span class="step-status-${s.status}">[${s.status}]</span>
          ${esc(s.task)}${durLabel}<br>
          <pre>${esc(s.result || '(no result)')}</pre>
        </div>`;
      }
      resHtml += '</div>';
      addCard(`<div class="card">
        <div class="card-header"><span class="badge badge-tool">EXEC</span> Execution complete</div>
        <div class="card-body">${resHtml}</div>
      </div>`);
    } else if (d.name === 'analyzing' && d.status === 'done') {
      const badge = d.achieved ? 'badge-done' : 'badge-error';
      const label = d.achieved ? 'ACHIEVED' : 'NOT ACHIEVED';
      addCard(`<div class="card">
        <div class="card-header"><span class="badge ${badge}">${label}</span> Confidence: ${(d.confidence * 100).toFixed(0)}%</div>
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

    print("Starting fim-agent playground at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
