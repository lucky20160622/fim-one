### Why dynamic planning is the hard middle ground

The AI agent landscape split into two camps, and both picked the easy path. Traditional workflow engines -- Dify, n8n, Coze -- chose static orchestration: visual drag-and-drop flowcharts with fixed execution paths. This was not ignorance; enterprise customers demand determinism (same input, stable output), and static graphs deliver that. On the other extreme, fully autonomous agents (AutoGPT and its descendants) promised end-to-end autonomy but proved impractical: unreliable task decomposition, runaway token costs, and behavior nobody could predict or debug.

The sweet spot is narrow but real. Simple tasks do not need a planner. Tasks complex enough to require dozens of interdependent steps overwhelm current LLMs. But in between lies a rich class of problems -- tasks with clear parallel subtasks that are tedious to hard-code yet tractable for an LLM to decompose. Dynamic DAG planning targets exactly this zone: the model proposes the execution graph at runtime, the framework validates the structure and runs it with maximum concurrency. No drag-and-drop, no YOLO autonomy.

### The bet on improving models

Every few months the foundation shifts -- GPT-4, function calling, Claude 3, the MCP protocol. Building a rigid abstraction on shifting ground is risky; LangChain's over-abstraction is the cautionary tale everyone in this space has internalized. FIM Agent takes the opposite approach: **minimal abstraction, maximum extensibility**. The framework owns orchestration, concurrency, and observability. The intelligence comes from the model, and the model keeps getting better.

Today, LLM task decomposition accuracy sits around 70-80% for non-trivial goals. When that reaches 90%+, the "sweet spot" for dynamic planning expands dramatically -- problems that were too complex yesterday become tractable tomorrow. FIM Agent's DAG framework is designed to capture that expanding value without rewriting the plumbing.

### Will ReAct and DAG planning become obsolete?

ReAct will not disappear -- it will sink into the model. Consider the analogy: you do not hand-write TCP handshakes, but TCP did not go away; it got absorbed into the operating system. When models are strong enough, the think-act-observe loop becomes implicit behavior inside the model, not explicit framework code. This is already happening: Claude Code is essentially a ReAct agent where the loop is driven by the model itself, not by an external harness.

DAG planning's lasting value is not "helping dumb models decompose tasks" -- it is **concurrent scheduling**. Even with infinitely capable models, physics imposes latency: a serial chain of 10 LLM calls takes 10x longer than 3 parallel waves. DAG is an engineering problem (how to run things fast and reliably), not an intelligence problem (how to decide what to run). Retry logic, cost control, timeout management, observability -- these do not go away when models get smarter.

The endgame: **models own the "what" (planning intelligence internalizes into the model), frameworks own the "how" (concurrency, retry, monitoring, cost governance)**. A framework's lasting value is not intelligence -- it is governance.

### Where FIM Agent stands

FIM Agent is not an "AGI task scheduler" and not a static workflow engine. It occupies the middle ground: planning capability with constraints, concurrency with observability.

- Compared to **Dify**: more flexible -- runtime DAG generation vs. design-time flowcharts. You do not need to anticipate every execution path in advance.
- Compared to **AutoGPT**: more controlled -- bounded iterations, re-planning limits, with human-in-the-loop on the roadmap. Autonomy within guardrails.

The strategy is straightforward: build the orchestration framework now, and let improving models fill it with capability over time.
