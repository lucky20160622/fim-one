# Execution Modes

### Three execution modes

fim-agent provides a spectrum of execution modes so users can choose the right trade-off between determinism and flexibility for each scenario:

| Mode | Best for | Determinism | Flexibility | Status |
|---|---|---|---|---|
| **Static Workflow** | Fixed processes, compliance-sensitive flows | High | Low | Roadmap v0.9 |
| **ReAct Agent** | Single complex queries, tool-use loops | Medium | Medium | Implemented |
| **DAG Planning** | Multi-step tasks with parallelizable subtasks | Medium | High | Implemented |

ReAct is the atomic execution unit -- a single agent that reasons, acts, and observes in a loop. DAG Planning is the orchestration layer on top -- it decomposes a goal into a dependency graph and runs independent steps concurrently, with each step powered by its own ReAct Agent. Static Workflow (coming in v0.9) will add a drag-and-drop visual editor for users who need fully deterministic execution paths.

```
DAG Planning (orchestration layer)
  |
  +-- step_1 --> ReAct Agent --> Tools     \
  |                                         |  step_1 & step_2 run in parallel
  +-- step_2 --> ReAct Agent --> Tools     /
  |
  +-- step_3 --> ReAct Agent --> Tools        (waits for step_1 & step_2)
```

These modes are not mutually exclusive. An organization can use Static Workflow for regulated processes, ReAct for ad-hoc queries, and DAG Planning for complex analytical tasks -- all within the same framework.
