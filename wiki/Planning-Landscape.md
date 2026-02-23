# Planning Landscape

### Four kinds of "planning" in the AI tooling landscape

The word "planning" is overloaded. At least four distinct approaches exist today, and they solve different problems:

| Approach | Plan format | Execution | Approval | Core value |
|---|---|---|---|---|
| **Implicit model planning** | Internal chain-of-thought | Single inference pass | None | The model thinks through steps on its own |
| **Claude Code plan mode** | Markdown document | Serial | Human reviews before execution | Align on approach before touching code |
| **Kiro spec-driven dev** | Structured spec (requirements + design + tasks) | Serial | Human reviews spec | Traceable requirements, acceptance criteria |
| **FIM Agent DAG** | JSON dependency graph | **Concurrent** | Automatic (PlanAnalyzer) | Parallel execution + runtime scheduling |

The first three are **design-time** planning -- they produce a plan *before* work begins, and a human (or the model itself) follows it step by step. FIM Agent's DAG is **runtime** planning -- the execution graph is generated, validated, and scheduled programmatically, with independent branches running in parallel.

These approaches are not competitors; they are complementary layers. A Kiro-style spec can define *what* to build, while a FIM Agent DAG can schedule *how* to execute the subtasks concurrently. Claude Code's plan mode ensures a human agrees with the approach; FIM Agent's PlanAnalyzer verifies the outcome automatically.
