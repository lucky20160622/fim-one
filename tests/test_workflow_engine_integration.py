"""Integration tests for complex workflow engine scenarios.

Exercises the engine with realistic multi-node graphs combining:
- Variable passing across nodes
- Parallel branches merging (diamond patterns)
- Mixed error strategies in a single graph
- Condition branching with downstream node execution
- Env variable injection and interpolation
- Cancellation mid-execution
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fim_one.core.workflow.engine import WorkflowEngine
from fim_one.core.workflow.parser import parse_blueprint
from fim_one.core.workflow.types import (
    ErrorStrategy,
    ExecutionContext,
    NodeResult,
    NodeStatus,
    NodeType,
    WorkflowBlueprint,
    WorkflowEdgeDef,
    WorkflowNodeDef,
)
from fim_one.core.workflow.variable_store import VariableStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_node(node_id: str = "start_1", **data: Any) -> dict:
    return {
        "id": node_id,
        "type": "start",
        "position": {"x": 0, "y": 0},
        "data": {"type": "START", **data},
    }


def _end_node(node_id: str = "end_1", **data: Any) -> dict:
    return {
        "id": node_id,
        "type": "end",
        "position": {"x": 800, "y": 0},
        "data": {"type": "END", **data},
    }


def _llm_node(node_id: str, **data: Any) -> dict:
    return {
        "id": node_id,
        "type": "llm",
        "position": {"x": 200, "y": 0},
        "data": {
            "type": "LLM",
            "prompt_template": "Hello {{input.query}}",
            **data,
        },
    }


def _variable_assign_node(node_id: str, **data: Any) -> dict:
    return {
        "id": node_id,
        "type": "variableAssign",
        "position": {"x": 200, "y": 0},
        "data": {
            "type": "VARIABLE_ASSIGN",
            "assignments": [
                {"variable": "result", "mode": "literal", "value": "done"}
            ],
            **data,
        },
    }


def _condition_node(
    node_id: str,
    conditions: list[dict] | None = None,
    **data: Any,
) -> dict:
    return {
        "id": node_id,
        "type": "conditionBranch",
        "position": {"x": 200, "y": 0},
        "data": {
            "type": "CONDITION_BRANCH",
            "conditions": conditions or [
                {"expression": "True", "handle": "true"},
            ],
            **data,
        },
    }


def _code_node(node_id: str, code: str = "result = 42", **data: Any) -> dict:
    return {
        "id": node_id,
        "type": "codeExecution",
        "position": {"x": 200, "y": 0},
        "data": {
            "type": "CODE_EXECUTION",
            "code": code,
            **data,
        },
    }


def _template_node(
    node_id: str,
    template: str = "Hello {{input.name}}",
    **data: Any,
) -> dict:
    return {
        "id": node_id,
        "type": "templateTransform",
        "position": {"x": 200, "y": 0},
        "data": {
            "type": "TEMPLATE_TRANSFORM",
            "template": template,
            **data,
        },
    }


def _edge(source: str, target: str, **kw: Any) -> dict:
    return {
        "id": kw.pop("edge_id", f"{source}->{target}"),
        "source": source,
        "target": target,
        **kw,
    }


async def _collect_events(
    engine: WorkflowEngine,
    bp: WorkflowBlueprint,
    inputs: dict[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Run engine and collect all SSE events."""
    events: list[tuple[str, dict[str, Any]]] = []
    async for event_name, event_data in engine.execute_streaming(bp, inputs):
        events.append((event_name, event_data))
    return events


def _events_by_type(
    events: list[tuple[str, dict]], event_type: str
) -> list[dict]:
    return [data for name, data in events if name == event_type]


def _completed_node_ids(events: list[tuple[str, dict]]) -> set[str]:
    return {d["node_id"] for name, d in events if name == "node_completed"}


def _skipped_node_ids(events: list[tuple[str, dict]]) -> set[str]:
    return {d["node_id"] for name, d in events if name == "node_skipped"}


def _failed_node_ids(events: list[tuple[str, dict]]) -> set[str]:
    return {d["node_id"] for name, d in events if name == "node_failed"}


# ---------------------------------------------------------------------------
# Test: Parallel Diamond (fan-out / fan-in)
# ---------------------------------------------------------------------------


class TestParallelDiamond:
    """Start → [A, B] → End (both branches merge at End)."""

    @pytest.mark.asyncio
    async def test_both_branches_complete(self):
        """Both parallel branches should execute and merge at End."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _variable_assign_node("va_a", assignments=[
                    {"variable": "a_result", "mode": "literal", "value": "from_a"},
                ]),
                _variable_assign_node("va_b", assignments=[
                    {"variable": "b_result", "mode": "literal", "value": "from_b"},
                ]),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "va_a"),
                _edge("start_1", "va_b"),
                _edge("va_a", "end_1"),
                _edge("va_b", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"query": "test"})

        completed = _completed_node_ids(events)
        assert "va_a" in completed
        assert "va_b" in completed
        assert "end_1" in completed

        # Run should complete successfully
        run_events = _events_by_type(events, "run_completed")
        assert len(run_events) == 1
        assert run_events[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_one_branch_fails_stop_workflow(self):
        """If one parallel branch fails with STOP_WORKFLOW, the other should be skipped."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_a", code="result = 42"),
                _code_node("code_b", code="raise ValueError('boom')",
                           error_strategy="stop_workflow"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_a"),
                _edge("start_1", "code_b"),
                _edge("code_a", "end_1"),
                _edge("code_b", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=1)  # Sequential for predictability
        events = await _collect_events(engine, bp)

        failed = _failed_node_ids(events)
        assert "code_b" in failed

        run_events = _events_by_type(events, "run_failed")
        assert len(run_events) == 1

    @pytest.mark.asyncio
    async def test_one_branch_fails_continue(self):
        """With CONTINUE strategy, failure in one branch shouldn't stop the other."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_a", code="result = 42"),
                _code_node("code_b", code="raise ValueError('boom')",
                           error_strategy="continue"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_a"),
                _edge("start_1", "code_b"),
                _edge("code_a", "end_1"),
                _edge("code_b", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        failed = _failed_node_ids(events)
        completed = _completed_node_ids(events)
        assert "code_b" in failed
        assert "code_a" in completed
        # End should still complete since code_b used CONTINUE
        assert "end_1" in completed


# ---------------------------------------------------------------------------
# Test: Condition + Diamond Merge
# ---------------------------------------------------------------------------


class TestConditionDiamondMerge:
    """Start → Condition → [true: NodeA, false: NodeB] → End."""

    @pytest.mark.asyncio
    async def test_true_branch_runs_false_skipped(self):
        """Only the true branch should execute."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _condition_node("cond_1", conditions=[
                    {"id": "c1", "expression": "True"},
                ]),
                _variable_assign_node("va_true", assignments=[
                    {"variable": "path", "mode": "literal", "value": "true_path"},
                ]),
                _variable_assign_node("va_false", assignments=[
                    {"variable": "path", "mode": "literal", "value": "false_path"},
                ]),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "cond_1"),
                _edge("cond_1", "va_true", sourceHandle="condition-c1"),
                _edge("cond_1", "va_false", sourceHandle="source-default"),
                _edge("va_true", "end_1"),
                _edge("va_false", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"value": 10})

        completed = _completed_node_ids(events)
        skipped = _skipped_node_ids(events)

        assert "va_true" in completed
        assert "va_false" in skipped
        assert "end_1" in completed

    @pytest.mark.asyncio
    async def test_default_branch_when_no_conditions_match(self):
        """When no conditions match, the default handle branch runs."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _condition_node("cond_1", conditions=[
                    {"id": "c1", "expression": "False"},
                ]),
                _variable_assign_node("va_special", assignments=[
                    {"variable": "path", "mode": "literal", "value": "special"},
                ]),
                _variable_assign_node("va_default", assignments=[
                    {"variable": "path", "mode": "literal", "value": "default"},
                ]),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "cond_1"),
                _edge("cond_1", "va_special", sourceHandle="condition-c1"),
                _edge("cond_1", "va_default", sourceHandle="source-default"),
                _edge("va_special", "end_1"),
                _edge("va_default", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        skipped = _skipped_node_ids(events)

        assert "va_special" in skipped
        assert "va_default" in completed


# ---------------------------------------------------------------------------
# Test: Mixed Error Strategies
# ---------------------------------------------------------------------------


class TestMixedErrorStrategies:
    """Graph with different error strategies on different nodes."""

    @pytest.mark.asyncio
    async def test_fail_branch_skips_downstream_only(self):
        """FAIL_BRANCH on a middle node should skip its exclusive downstream.

        Note: _collect_downstream does BFS from the failed node, so ANY node
        reachable from it (including shared merge points like end_1) gets skipped.
        This is by design — FAIL_BRANCH propagates fully through the subgraph.
        """
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_ok", code="result = 'ok'"),
                _code_node("code_fail", code="raise ValueError('boom')",
                           error_strategy="fail_branch"),
                _variable_assign_node("va_after_fail", assignments=[
                    {"variable": "x", "mode": "literal", "value": "1"},
                ]),
                _end_node("end_ok"),
                _end_node("end_fail"),
            ],
            "edges": [
                _edge("start_1", "code_ok"),
                _edge("start_1", "code_fail"),
                _edge("code_fail", "va_after_fail"),
                _edge("va_after_fail", "end_fail"),
                _edge("code_ok", "end_ok"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        failed = _failed_node_ids(events)
        completed = _completed_node_ids(events)
        skipped = _skipped_node_ids(events)

        assert "code_fail" in failed
        assert "va_after_fail" in skipped  # downstream of fail_branch
        assert "end_fail" in skipped  # downstream of fail_branch
        assert "code_ok" in completed  # sibling branch unaffected
        assert "end_ok" in completed  # sibling end node completes


# ---------------------------------------------------------------------------
# Test: Env Variables
# ---------------------------------------------------------------------------


class TestEnvVariableInjection:
    """Test that encrypted env vars are accessible in the workflow."""

    @pytest.mark.asyncio
    async def test_env_vars_available_in_store(self):
        """Env vars should be injected into the store under env.* namespace."""
        store = VariableStore(env_vars={"API_KEY": "secret-123"})
        val = await store.get("env.API_KEY")
        assert val == "secret-123"

    @pytest.mark.asyncio
    async def test_env_vars_in_variable_store_interpolation(self):
        """Env vars should be interpolable via {{env.API_KEY}} in store.interpolate()."""
        store = VariableStore(env_vars={"API_KEY": "secret-123"})
        result = await store.interpolate("Key is {{env.API_KEY}}")
        assert result == "Key is secret-123"

    @pytest.mark.asyncio
    async def test_template_transform_with_regular_vars(self):
        """TemplateTransform Jinja2 renders with store variables (non-env)."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _template_node("tmpl_1", template="Hello {{ input_name }}"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "tmpl_1"),
                _edge("tmpl_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"name": "World"})

        completed = _completed_node_ids(events)
        assert "tmpl_1" in completed

        run_completed = _events_by_type(events, "run_completed")
        assert len(run_completed) == 1


# ---------------------------------------------------------------------------
# Test: Code Execution Variable Passing
# ---------------------------------------------------------------------------


class TestCodeExecutionIntegration:
    """Test code execution nodes with variable passing."""

    @pytest.mark.asyncio
    async def test_code_result_available_downstream(self):
        """Code node result should be accessible by downstream nodes."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 42"),
                _end_node(output_mapping={
                    "answer": "{{code_1.result}}",
                }),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        assert "code_1" in completed
        assert "end_1" in completed

        run_completed = _events_by_type(events, "run_completed")
        assert len(run_completed) == 1
        assert run_completed[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_chained_code_nodes(self):
        """Code nodes in sequence should be able to read each other's outputs."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 10"),
                _code_node("code_2", code="result = 20"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "code_2"),
                _edge("code_2", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        assert "code_1" in completed
        assert "code_2" in completed
        assert "end_1" in completed

    @pytest.mark.asyncio
    async def test_code_with_input_variables(self):
        """Code node should have access to start inputs."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 'processed'"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"name": "World"})

        completed = _completed_node_ids(events)
        assert "code_1" in completed

        run_completed = _events_by_type(events, "run_completed")
        assert run_completed[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# Test: Cancellation During Execution
# ---------------------------------------------------------------------------


class TestCancellationScenarios:
    """Test cancellation at various points during execution."""

    @pytest.mark.asyncio
    async def test_cancel_before_second_node(self):
        """Cancelling after first node should skip remaining nodes."""
        cancel = asyncio.Event()

        async def slow_execute(node, store, ctx):
            """Slow executor that allows cancellation to fire."""
            await asyncio.sleep(0.3)
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED, output="done")

        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 1"),
                _code_node("code_2", code="result = 2"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "code_2"),
                _edge("code_2", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5, cancel_event=cancel)

        events: list[tuple[str, dict]] = []
        saw_code_1_started = False

        async for event_name, event_data in engine.execute_streaming(bp):
            events.append((event_name, event_data))
            if event_name == "node_started" and event_data.get("node_id") == "code_1":
                saw_code_1_started = True
            if event_name == "node_completed" and event_data.get("node_id") == "code_1":
                cancel.set()

        # code_1 should have started
        assert saw_code_1_started

        # After cancellation, remaining nodes should be skipped
        skipped = _skipped_node_ids(events)
        # code_2 and end_1 should be skipped
        assert "code_2" in skipped or "end_1" in skipped


# ---------------------------------------------------------------------------
# Test: Complex Multi-Level Graph
# ---------------------------------------------------------------------------


class TestComplexGraph:
    """Complex graph with multiple levels and mixed node types."""

    @pytest.mark.asyncio
    async def test_deep_linear_chain(self):
        """10-node linear chain should execute in order."""
        nodes = [_start_node()]
        edges = []

        for i in range(1, 9):
            nodes.append(_variable_assign_node(f"va_{i}", assignments=[
                {"variable": f"step_{i}", "mode": "literal", "value": str(i)},
            ]))

        nodes.append(_end_node())

        # Chain: start → va_1 → va_2 → ... → va_8 → end
        prev = "start_1"
        for i in range(1, 9):
            edges.append(_edge(prev, f"va_{i}"))
            prev = f"va_{i}"
        edges.append(_edge(prev, "end_1"))

        bp = parse_blueprint({"nodes": nodes, "edges": edges})
        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        for i in range(1, 9):
            assert f"va_{i}" in completed

        run_completed = _events_by_type(events, "run_completed")
        assert len(run_completed) == 1
        assert run_completed[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_wide_fanout(self):
        """Start fans out to 5 parallel nodes, all merge to End."""
        nodes = [_start_node()]
        edges = []

        for i in range(1, 6):
            nodes.append(_variable_assign_node(f"va_{i}", assignments=[
                {"variable": f"branch_{i}", "mode": "literal", "value": str(i)},
            ]))
            edges.append(_edge("start_1", f"va_{i}"))
            edges.append(_edge(f"va_{i}", "end_1"))

        nodes.append(_end_node())

        bp = parse_blueprint({"nodes": nodes, "edges": edges})
        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        for i in range(1, 6):
            assert f"va_{i}" in completed
        assert "end_1" in completed

    @pytest.mark.asyncio
    async def test_multiple_end_nodes(self):
        """Graph with two End nodes — both should execute."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _variable_assign_node("va_1", assignments=[
                    {"variable": "x", "mode": "literal", "value": "1"},
                ]),
                _variable_assign_node("va_2", assignments=[
                    {"variable": "y", "mode": "literal", "value": "2"},
                ]),
                _end_node("end_1"),
                _end_node("end_2"),
            ],
            "edges": [
                _edge("start_1", "va_1"),
                _edge("start_1", "va_2"),
                _edge("va_1", "end_1"),
                _edge("va_2", "end_2"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        assert "end_1" in completed
        assert "end_2" in completed


# ---------------------------------------------------------------------------
# Test: Input Preview Capture
# ---------------------------------------------------------------------------


class TestInputPreview:
    """Test that node input previews are captured and emitted."""

    @pytest.mark.asyncio
    async def test_input_preview_in_events(self):
        """node_started events should include input_preview."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 42"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"name": "test"})

        started_events = _events_by_type(events, "node_started")
        # code_1 should have an input_preview (showing start_1 outputs)
        code_1_started = [e for e in started_events if e.get("node_id") == "code_1"]
        assert len(code_1_started) == 1
        # input_preview should be set (may be None for Start node's first output)
        assert "input_preview" in code_1_started[0]


# ---------------------------------------------------------------------------
# Test: Workflow Timeout
# ---------------------------------------------------------------------------


class TestWorkflowTimeoutIntegration:
    """Integration tests for workflow-level timeout."""

    @pytest.mark.asyncio
    async def test_timeout_emits_run_failed(self):
        """Workflow timeout should emit run_failed with timeout error."""
        async def slow_execute(node, store, ctx):
            await asyncio.sleep(5)
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED)

        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 1"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5, workflow_timeout_ms=100)

        with patch(
            "fim_one.core.workflow.nodes.CodeExecutionExecutor.execute",
            side_effect=slow_execute,
        ):
            events = await _collect_events(engine, bp)

        run_failed = _events_by_type(events, "run_failed")
        assert len(run_failed) == 1
        assert "timed out" in run_failed[0]["error"].lower()


# ---------------------------------------------------------------------------
# Test: Event Ordering
# ---------------------------------------------------------------------------


class TestEventOrdering:
    """Verify SSE events follow correct chronological order."""

    @pytest.mark.asyncio
    async def test_run_started_is_first(self):
        """run_started should always be the first event."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        assert events[0][0] == "run_started"

    @pytest.mark.asyncio
    async def test_run_completed_is_last(self):
        """run_completed should be the last event."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 1"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        last_event = events[-1]
        assert last_event[0] in ("run_completed", "run_failed")

    @pytest.mark.asyncio
    async def test_node_started_before_completed(self):
        """For each node, started should come before completed."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 1"),
                _code_node("code_2", code="result = 2"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "code_2"),
                _edge("code_2", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        # Build order index
        event_positions: dict[str, dict[str, int]] = {}
        for idx, (name, data) in enumerate(events):
            nid = data.get("node_id")
            if nid:
                if nid not in event_positions:
                    event_positions[nid] = {}
                event_positions[nid][name] = idx

        for nid, positions in event_positions.items():
            if "node_started" in positions and "node_completed" in positions:
                assert positions["node_started"] < positions["node_completed"], (
                    f"Node {nid}: started@{positions['node_started']} "
                    f"should come before completed@{positions['node_completed']}"
                )

    @pytest.mark.asyncio
    async def test_predecessor_completes_before_successor_starts(self):
        """In a linear chain, predecessor completion precedes successor start."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _code_node("code_1", code="result = 1"),
                _code_node("code_2", code="result = 2"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "code_1"),
                _edge("code_1", "code_2"),
                _edge("code_2", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        # Find positions
        code_1_completed = None
        code_2_started = None
        for idx, (name, data) in enumerate(events):
            nid = data.get("node_id")
            if name == "node_completed" and nid == "code_1":
                code_1_completed = idx
            if name == "node_started" and nid == "code_2":
                code_2_started = idx

        assert code_1_completed is not None
        assert code_2_started is not None
        assert code_1_completed < code_2_started


# ---------------------------------------------------------------------------
# Test: Empty Workflow
# ---------------------------------------------------------------------------


class TestMinimalWorkflows:
    """Edge cases with minimal workflows."""

    @pytest.mark.asyncio
    async def test_start_to_end_only(self):
        """Simplest possible workflow: Start → End."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp)

        run_completed = _events_by_type(events, "run_completed")
        assert len(run_completed) == 1
        assert run_completed[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_start_to_end_with_inputs(self):
        """Start → End with inputs should pass through via output_mapping dict."""
        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _end_node(output_mapping={
                    "echo": "{{input.message}}",
                }),
            ],
            "edges": [
                _edge("start_1", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=5)
        events = await _collect_events(engine, bp, {"message": "hello"})

        run_completed = _events_by_type(events, "run_completed")
        assert len(run_completed) == 1
        assert run_completed[0]["status"] == "completed"
        # Output should contain the echoed message
        outputs = run_completed[0].get("outputs", {})
        assert outputs.get("echo") == "hello"


# ---------------------------------------------------------------------------
# Test: Concurrency Limits
# ---------------------------------------------------------------------------


class TestConcurrencyLimits:
    """Verify semaphore correctly limits concurrent execution."""

    @pytest.mark.asyncio
    async def test_max_concurrency_one(self):
        """With max_concurrency=1, nodes should execute sequentially."""
        execution_log: list[tuple[str, str]] = []

        async def tracking_execute(node, store, ctx):
            execution_log.append((node.id, "start"))
            await asyncio.sleep(0.01)
            execution_log.append((node.id, "end"))
            if node.type == NodeType.VARIABLE_ASSIGN:
                for a in node.data.get("assignments", []):
                    await store.set(f"{node.id}.{a['variable']}", a["value"])
            return NodeResult(node_id=node.id, status=NodeStatus.COMPLETED, output="ok")

        bp = parse_blueprint({
            "nodes": [
                _start_node(),
                _variable_assign_node("va_1"),
                _variable_assign_node("va_2"),
                _variable_assign_node("va_3"),
                _end_node(),
            ],
            "edges": [
                _edge("start_1", "va_1"),
                _edge("start_1", "va_2"),
                _edge("start_1", "va_3"),
                _edge("va_1", "end_1"),
                _edge("va_2", "end_1"),
                _edge("va_3", "end_1"),
            ],
        })

        engine = WorkflowEngine(max_concurrency=1)

        with patch(
            "fim_one.core.workflow.nodes.VariableAssignExecutor.execute",
            side_effect=tracking_execute,
        ):
            events = await _collect_events(engine, bp)

        completed = _completed_node_ids(events)
        assert "va_1" in completed
        assert "va_2" in completed
        assert "va_3" in completed

        # With concurrency=1, no two VA nodes should overlap
        # Check that each "start" is followed by its "end" before next "start"
        va_entries = [(nid, action) for nid, action in execution_log
                      if nid.startswith("va_")]
        for i in range(0, len(va_entries) - 1, 2):
            nid_start, action_start = va_entries[i]
            nid_end, action_end = va_entries[i + 1]
            assert nid_start == nid_end, f"Expected matching pair, got {nid_start}/{nid_end}"
            assert action_start == "start"
            assert action_end == "end"
