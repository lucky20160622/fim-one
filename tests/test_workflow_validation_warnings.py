"""Comprehensive tests for workflow blueprint validation warnings.

Tests ``validate_blueprint()`` which returns non-fatal ``BlueprintWarning``
objects covering disconnected nodes, reachability, and node-specific field
checks across all supported node types.
"""

from __future__ import annotations

from typing import Any

import pytest

from fim_one.core.workflow.parser import (
    BlueprintWarning,
    parse_blueprint,
    validate_blueprint,
)
from fim_one.core.workflow.types import (
    NodeType,
    WorkflowBlueprint,
    WorkflowEdgeDef,
    WorkflowNodeDef,
)


# ---------------------------------------------------------------------------
# Helpers: build raw blueprint dicts for parse_blueprint()
# ---------------------------------------------------------------------------


def _node(node_id: str, node_type: str, **data: Any) -> dict:
    """Build a raw node dict suitable for parse_blueprint()."""
    return {
        "id": node_id,
        "position": {"x": 0, "y": 0},
        "data": {"type": node_type, **data},
    }


def _start(node_id: str = "start") -> dict:
    return _node(node_id, "START")


def _end(node_id: str = "end") -> dict:
    return _node(node_id, "END")


def _edge(source: str, target: str, source_handle: str | None = None) -> dict:
    e: dict[str, Any] = {
        "id": f"e-{source}-{target}",
        "source": source,
        "target": target,
    }
    if source_handle is not None:
        e["sourceHandle"] = source_handle
    return e


def _make_blueprint(
    nodes: list[dict],
    edges: list[dict] | None = None,
) -> WorkflowBlueprint:
    """Parse a raw blueprint dict into a WorkflowBlueprint."""
    raw = {
        "nodes": nodes,
        "edges": edges or [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    return parse_blueprint(raw)


def _warning_codes(warnings: list[BlueprintWarning]) -> list[str]:
    """Extract warning codes sorted for deterministic assertions."""
    return sorted(w.code for w in warnings)


def _warnings_for_node(
    warnings: list[BlueprintWarning], node_id: str
) -> list[BlueprintWarning]:
    """Filter warnings belonging to a specific node."""
    return [w for w in warnings if w.node_id == node_id]


def _has_warning(
    warnings: list[BlueprintWarning], code: str, node_id: str | None = None
) -> bool:
    """Check whether a specific warning code exists, optionally for a node."""
    for w in warnings:
        if w.code == code and (node_id is None or w.node_id == node_id):
            return True
    return False


# ===========================================================================
# TestDisconnectedNodes
# ===========================================================================


class TestDisconnectedNodes:
    """Warnings for nodes with missing incoming/outgoing connections."""

    def test_start_no_outgoing(self) -> None:
        """Start node with no outgoing edges produces start_no_outgoing."""
        bp = _make_blueprint(
            nodes=[_start(), _end()],
            edges=[],  # no edges at all
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "start_no_outgoing", "start")

    def test_end_no_incoming(self) -> None:
        """End node with no incoming edges produces end_no_incoming."""
        bp = _make_blueprint(
            nodes=[_start(), _end()],
            edges=[],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "end_no_incoming", "end")

    def test_middle_node_disconnected(self) -> None:
        """A non-start/non-end node with zero connections is disconnected."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm_1", "LLM", prompt_template="hello"),
                _end(),
            ],
            edges=[_edge("start", "end")],  # llm_1 has no edges
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "disconnected_node", "llm_1")

    def test_properly_connected_no_disconnection_warnings(self) -> None:
        """A fully connected graph produces no disconnection warnings."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm_1", "LLM", prompt_template="hello"),
                _end(),
            ],
            edges=[
                _edge("start", "llm_1"),
                _edge("llm_1", "end"),
            ],
        )
        warnings = validate_blueprint(bp)
        disconnection_codes = {"start_no_outgoing", "end_no_incoming", "disconnected_node"}
        assert not any(w.code in disconnection_codes for w in warnings)

    def test_multiple_disconnected_nodes(self) -> None:
        """Multiple disconnected middle nodes each get their own warning."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("orphan_a", "LLM", prompt_template="a"),
                _node("orphan_b", "CODE_EXECUTION", code="x=1"),
                _end(),
            ],
            edges=[_edge("start", "end")],
        )
        warnings = validate_blueprint(bp)
        orphan_warnings = [
            w for w in warnings if w.code == "disconnected_node"
        ]
        orphan_ids = {w.node_id for w in orphan_warnings}
        assert orphan_ids == {"orphan_a", "orphan_b"}


# ===========================================================================
# TestReachability
# ===========================================================================


class TestReachability:
    """Warnings when End nodes are not reachable from Start via BFS."""

    def test_end_unreachable_from_start(self) -> None:
        """An End node with no path from Start is flagged as unreachable."""
        # Two separate islands: start -> llm, end is alone
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm_1", "LLM", prompt_template="hi"),
                _end(),
            ],
            edges=[_edge("start", "llm_1")],  # no path to end
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "end_unreachable", "end")

    def test_all_ends_reachable(self) -> None:
        """No unreachable warning when all End nodes are reachable."""
        bp = _make_blueprint(
            nodes=[_start(), _end()],
            edges=[_edge("start", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "end_unreachable")

    def test_multiple_ends_one_unreachable(self) -> None:
        """Only the unreachable End node gets the warning, not the reachable one."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _end("end_ok"),
                _end("end_orphan"),
            ],
            edges=[_edge("start", "end_ok")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "end_unreachable", "end_orphan")
        assert not _has_warning(warnings, "end_unreachable", "end_ok")

    def test_parallel_paths_reaching_end(self) -> None:
        """Two parallel paths both reaching End produce no warning."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("a", "LLM", prompt_template="hi"),
                _node("b", "LLM", prompt_template="hi"),
                _end(),
            ],
            edges=[
                _edge("start", "a"),
                _edge("start", "b"),
                _edge("a", "end"),
                _edge("b", "end"),
            ],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "end_unreachable")

    def test_island_not_connected_to_start(self) -> None:
        """A connected sub-graph not reachable from Start leads to
        end_unreachable for any End node in that island."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _end("end_main"),
                # Island: llm -> end_island (not connected to start)
                _node("llm_island", "LLM", prompt_template="island"),
                _end("end_island"),
            ],
            edges=[
                _edge("start", "end_main"),
                _edge("llm_island", "end_island"),
            ],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "end_unreachable", "end_island")
        assert not _has_warning(warnings, "end_unreachable", "end_main")


# ===========================================================================
# TestNodeSpecificWarnings
# ===========================================================================


class TestNodeSpecificWarnings:
    """Per-node-type field checks that emit specific warning codes."""

    # --- CONDITION_BRANCH ---------------------------------------------------

    def test_condition_branch_no_conditions(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("cb", "CONDITION_BRANCH"),  # no conditions key
                _end(),
            ],
            edges=[_edge("start", "cb"), _edge("cb", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_conditions", "cb")

    def test_condition_branch_empty_list(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("cb", "CONDITION_BRANCH", conditions=[]),
                _end(),
            ],
            edges=[_edge("start", "cb"), _edge("cb", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_conditions", "cb")

    def test_condition_branch_with_conditions(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "cb",
                    "CONDITION_BRANCH",
                    conditions=[{"handle": "yes", "expression": "x > 0"}],
                ),
                _end(),
            ],
            edges=[_edge("start", "cb"), _edge("cb", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_conditions", "cb")

    # --- QUESTION_CLASSIFIER -----------------------------------------------

    def test_question_classifier_no_classes(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("qc", "QUESTION_CLASSIFIER"),
                _end(),
            ],
            edges=[_edge("start", "qc"), _edge("qc", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_classes", "qc")

    def test_question_classifier_with_classes(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("qc", "QUESTION_CLASSIFIER", classes=["billing", "support"]),
                _end(),
            ],
            edges=[_edge("start", "qc"), _edge("qc", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_classes", "qc")

    def test_question_classifier_with_categories(self) -> None:
        """The alt field 'categories' is also accepted."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("qc", "QUESTION_CLASSIFIER", categories=["a", "b"]),
                _end(),
            ],
            edges=[_edge("start", "qc"), _edge("qc", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_classes", "qc")

    # --- LLM ---------------------------------------------------------------

    def test_llm_no_prompt(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm", "LLM"),  # no prompt or prompt_template
                _end(),
            ],
            edges=[_edge("start", "llm"), _edge("llm", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_prompt", "llm")

    def test_llm_with_prompt_template(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm", "LLM", prompt_template="Hello {{name}}"),
                _end(),
            ],
            edges=[_edge("start", "llm"), _edge("llm", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_prompt", "llm")

    def test_llm_with_prompt_field(self) -> None:
        """The alt field 'prompt' is also accepted."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm", "LLM", prompt="Summarize this"),
                _end(),
            ],
            edges=[_edge("start", "llm"), _edge("llm", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_prompt", "llm")

    # --- CODE_EXECUTION ----------------------------------------------------

    def test_code_execution_no_code(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("code", "CODE_EXECUTION"),
                _end(),
            ],
            edges=[_edge("start", "code"), _edge("code", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_code", "code")

    def test_code_execution_with_code(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("code", "CODE_EXECUTION", code="print('hi')"),
                _end(),
            ],
            edges=[_edge("start", "code"), _edge("code", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_code", "code")

    # --- LIST_OPERATION ----------------------------------------------------

    def test_list_operation_no_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("lo", "LIST_OPERATION", operation="filter"),
                _end(),
            ],
            edges=[_edge("start", "lo"), _edge("lo", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_input_variable", "lo")

    def test_list_operation_filter_no_expression(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "lo",
                    "LIST_OPERATION",
                    input_variable="items",
                    operation="filter",
                ),
                _end(),
            ],
            edges=[_edge("start", "lo"), _edge("lo", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_expression", "lo")

    def test_list_operation_map_no_expression(self) -> None:
        """The 'map' operation also requires an expression."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "lo",
                    "LIST_OPERATION",
                    input_variable="items",
                    operation="map",
                ),
                _end(),
            ],
            edges=[_edge("start", "lo"), _edge("lo", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_expression", "lo")

    def test_list_operation_sort_no_expression_needed(self) -> None:
        """The 'sort' operation does NOT require an expression."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "lo",
                    "LIST_OPERATION",
                    input_variable="items",
                    operation="sort",
                ),
                _end(),
            ],
            edges=[_edge("start", "lo"), _edge("lo", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_expression", "lo")

    # --- TRANSFORM ---------------------------------------------------------

    def test_transform_no_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("tf", "TRANSFORM", operations=["upper"]),
                _end(),
            ],
            edges=[_edge("start", "tf"), _edge("tf", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_input_variable", "tf")

    def test_transform_no_operations(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("tf", "TRANSFORM", input_variable="x"),
                _end(),
            ],
            edges=[_edge("start", "tf"), _edge("tf", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_operations", "tf")

    def test_transform_complete(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "tf",
                    "TRANSFORM",
                    input_variable="x",
                    operations=["upper"],
                ),
                _end(),
            ],
            edges=[_edge("start", "tf"), _edge("tf", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_input_variable", "tf")
        assert not _has_warning(warnings, "empty_operations", "tf")

    # --- ITERATOR ----------------------------------------------------------

    def test_iterator_no_list_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("it", "ITERATOR"),
                _end(),
            ],
            edges=[_edge("start", "it"), _edge("it", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_list_variable", "it")

    def test_iterator_with_list_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("it", "ITERATOR", list_variable="items"),
                _end(),
            ],
            edges=[_edge("start", "it"), _edge("it", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_list_variable", "it")

    # --- LOOP --------------------------------------------------------------

    def test_loop_no_condition(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("loop", "LOOP"),
                _end(),
            ],
            edges=[_edge("start", "loop"), _edge("loop", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_condition", "loop")

    def test_loop_with_condition(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("loop", "LOOP", condition="count < 10"),
                _end(),
            ],
            edges=[_edge("start", "loop"), _edge("loop", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_condition", "loop")

    # --- DOCUMENT_EXTRACTOR ------------------------------------------------

    def test_document_extractor_no_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("de", "DOCUMENT_EXTRACTOR"),
                _end(),
            ],
            edges=[_edge("start", "de"), _edge("de", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_input_variable", "de")

    def test_document_extractor_with_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("de", "DOCUMENT_EXTRACTOR", input_variable="file"),
                _end(),
            ],
            edges=[_edge("start", "de"), _edge("de", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_input_variable", "de")

    # --- QUESTION_UNDERSTANDING --------------------------------------------

    def test_question_understanding_no_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("qu", "QUESTION_UNDERSTANDING"),
                _end(),
            ],
            edges=[_edge("start", "qu"), _edge("qu", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_input_variable", "qu")

    def test_question_understanding_with_input_variable(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("qu", "QUESTION_UNDERSTANDING", input_variable="query"),
                _end(),
            ],
            edges=[_edge("start", "qu"), _edge("qu", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_input_variable", "qu")

    # --- HUMAN_INTERVENTION ------------------------------------------------

    def test_human_intervention_no_prompt_message(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("hi", "HUMAN_INTERVENTION"),
                _end(),
            ],
            edges=[_edge("start", "hi"), _edge("hi", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_prompt_message", "hi")

    def test_human_intervention_with_prompt_message(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("hi", "HUMAN_INTERVENTION", prompt_message="Review this"),
                _end(),
            ],
            edges=[_edge("start", "hi"), _edge("hi", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "empty_prompt_message", "hi")

    # --- PARAMETER_EXTRACTOR -----------------------------------------------

    def test_parameter_extractor_no_input_text(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("pe", "PARAMETER_EXTRACTOR"),
                _end(),
            ],
            edges=[_edge("start", "pe"), _edge("pe", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_input_text", "pe")

    def test_parameter_extractor_no_parameters(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("pe", "PARAMETER_EXTRACTOR", input_text="some text"),
                _end(),
            ],
            edges=[_edge("start", "pe"), _edge("pe", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "empty_parameters", "pe")

    def test_parameter_extractor_complete(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node(
                    "pe",
                    "PARAMETER_EXTRACTOR",
                    input_text="extract from here",
                    parameters=[{"name": "email", "type": "string"}],
                ),
                _end(),
            ],
            edges=[_edge("start", "pe"), _edge("pe", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_input_text", "pe")
        assert not _has_warning(warnings, "empty_parameters", "pe")

    # --- MCP ---------------------------------------------------------------

    def test_mcp_no_server_id(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("mcp", "MCP", tool_name="search"),
                _end(),
            ],
            edges=[_edge("start", "mcp"), _edge("mcp", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_server_id", "mcp")

    def test_mcp_no_tool_name(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("mcp", "MCP", server_id="srv-1"),
                _end(),
            ],
            edges=[_edge("start", "mcp"), _edge("mcp", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_tool_name", "mcp")

    def test_mcp_complete(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("mcp", "MCP", server_id="srv-1", tool_name="search"),
                _end(),
            ],
            edges=[_edge("start", "mcp"), _edge("mcp", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_server_id", "mcp")
        assert not _has_warning(warnings, "missing_tool_name", "mcp")

    # --- BUILTIN_TOOL ------------------------------------------------------

    def test_builtin_tool_no_tool_id(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("bt", "BUILTIN_TOOL"),
                _end(),
            ],
            edges=[_edge("start", "bt"), _edge("bt", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_tool_id", "bt")

    def test_builtin_tool_with_tool_id(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("bt", "BUILTIN_TOOL", tool_id="calculator"),
                _end(),
            ],
            edges=[_edge("start", "bt"), _edge("bt", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_tool_id", "bt")

    # --- SUB_WORKFLOW ------------------------------------------------------

    def test_sub_workflow_no_workflow_id(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("sw", "SUB_WORKFLOW"),
                _end(),
            ],
            edges=[_edge("start", "sw"), _edge("sw", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_workflow_id", "sw")

    def test_sub_workflow_with_workflow_id(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("sw", "SUB_WORKFLOW", workflow_id="wf-abc"),
                _end(),
            ],
            edges=[_edge("start", "sw"), _edge("sw", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_workflow_id", "sw")

    # --- ENV ---------------------------------------------------------------

    def test_env_no_env_keys(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("env", "ENV"),
                _end(),
            ],
            edges=[_edge("start", "env"), _edge("env", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_env_keys", "env")

    def test_env_empty_list(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("env", "ENV", env_keys=[]),
                _end(),
            ],
            edges=[_edge("start", "env"), _edge("env", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_env_keys", "env")

    def test_env_non_list(self) -> None:
        """env_keys that is not a list (e.g. a string) triggers the warning."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("env", "ENV", env_keys="API_KEY"),
                _end(),
            ],
            edges=[_edge("start", "env"), _edge("env", "end")],
        )
        warnings = validate_blueprint(bp)
        assert _has_warning(warnings, "missing_env_keys", "env")

    def test_env_with_valid_keys(self) -> None:
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("env", "ENV", env_keys=["API_KEY", "SECRET"]),
                _end(),
            ],
            edges=[_edge("start", "env"), _edge("env", "end")],
        )
        warnings = validate_blueprint(bp)
        assert not _has_warning(warnings, "missing_env_keys", "env")


# ===========================================================================
# TestMultipleWarnings
# ===========================================================================


class TestMultipleWarnings:
    """Tests for blueprints that produce a combination of warnings."""

    def test_several_issues_at_once(self) -> None:
        """A blueprint with multiple problems returns all relevant warnings."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm", "LLM"),  # no prompt
                _node("code", "CODE_EXECUTION"),  # no code
                _node("orphan", "ITERATOR"),  # disconnected + no list_variable
                _end(),
            ],
            edges=[
                _edge("start", "llm"),
                _edge("llm", "code"),
                _edge("code", "end"),
                # orphan has no edges
            ],
        )
        warnings = validate_blueprint(bp)
        codes = _warning_codes(warnings)

        assert "empty_prompt" in codes
        assert "empty_code" in codes
        assert "disconnected_node" in codes
        assert "missing_list_variable" in codes

    def test_clean_blueprint_no_warnings(self) -> None:
        """A properly configured blueprint returns an empty list."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm", "LLM", prompt_template="Hello"),
                _end(),
            ],
            edges=[
                _edge("start", "llm"),
                _edge("llm", "end"),
            ],
        )
        warnings = validate_blueprint(bp)
        assert warnings == []

    def test_complex_graph_mixed_warnings(self) -> None:
        """Complex graph combining disconnection, reachability, and field warnings."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                # Reachable path: start -> cond (empty) -> end_ok
                _node("cond", "CONDITION_BRANCH"),  # empty_conditions
                _end("end_ok"),
                # Disconnected island: mcp (missing fields) -> end_island
                _node("mcp", "MCP"),  # missing server_id + tool_name
                _end("end_island"),
            ],
            edges=[
                _edge("start", "cond"),
                _edge("cond", "end_ok"),
                _edge("mcp", "end_island"),
            ],
        )
        warnings = validate_blueprint(bp)
        codes = _warning_codes(warnings)

        # Structural warnings
        assert "end_unreachable" in codes  # end_island unreachable from start
        # The mcp node has incoming=False, outgoing=True -- NOT disconnected
        # (disconnected requires BOTH missing). But it IS an island node.

        # Node-specific warnings
        assert "empty_conditions" in codes
        assert "missing_server_id" in codes
        assert "missing_tool_name" in codes

        # Verify end_island is the unreachable one, not end_ok
        assert _has_warning(warnings, "end_unreachable", "end_island")
        assert not _has_warning(warnings, "end_unreachable", "end_ok")

    def test_warning_object_fields(self) -> None:
        """BlueprintWarning objects have correct node_id, code, and message."""
        bp = _make_blueprint(
            nodes=[
                _start(),
                _node("llm_x", "LLM"),
                _end(),
            ],
            edges=[_edge("start", "llm_x"), _edge("llm_x", "end")],
        )
        warnings = validate_blueprint(bp)
        w = next(w for w in warnings if w.code == "empty_prompt")
        assert w.node_id == "llm_x"
        assert w.code == "empty_prompt"
        assert isinstance(w.message, str)
        assert len(w.message) > 0
