"""Tests for the request_tools on-demand tool loading mechanism."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fim_one.core.agent import ReActAgent
from fim_one.core.agent.react import TOOL_SELECTION_THRESHOLD
from fim_one.core.model import ChatMessage, LLMResult
from fim_one.core.tool import BaseTool, ToolRegistry
from fim_one.core.tool.builtin.request_tools import RequestToolsTool

from .conftest import FakeLLM


# ======================================================================
# Helpers
# ======================================================================


class _StubTool(BaseTool):
    """A configurable stub tool for testing."""

    def __init__(self, name: str, description: str = "A stub tool.") -> None:
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "The input value."},
            },
            "required": ["input"],
        }

    async def run(self, **kwargs: Any) -> str:
        return f"stub:{self._name}"


def _make_large_registry(n: int = 15) -> ToolRegistry:
    """Create a registry with *n* stub tools."""
    reg = ToolRegistry()
    for i in range(n):
        reg.register(_StubTool(f"tool_{i}", f"Description for tool {i}."))
    return reg


def _selection_response(tool_names: list[str]) -> LLMResult:
    """Create an LLMResult that returns a tool selection JSON."""
    return LLMResult(
        message=ChatMessage(
            role="assistant",
            content=json.dumps({"tools": tool_names}),
        ),
    )


def _final_answer_response(answer: str) -> LLMResult:
    return LLMResult(
        message=ChatMessage(
            role="assistant",
            content=json.dumps(
                {
                    "type": "final_answer",
                    "reasoning": "done",
                    "answer": answer,
                }
            ),
        ),
    )


def _tool_call_response(tool_name: str, tool_args: dict) -> LLMResult:
    return LLMResult(
        message=ChatMessage(
            role="assistant",
            content=json.dumps(
                {
                    "type": "tool_call",
                    "reasoning": f"calling {tool_name}",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                }
            ),
        ),
    )


# ======================================================================
# RequestToolsTool unit tests
# ======================================================================


class TestRequestToolsTool:
    """Unit tests for RequestToolsTool in isolation."""

    def _make_registries(self) -> tuple[ToolRegistry, ToolRegistry]:
        """Create full and active registries for testing."""
        full = ToolRegistry()
        for i in range(5):
            full.register(_StubTool(f"tool_{i}", f"Tool {i} description."))

        active = ToolRegistry()
        active.register(full.get("tool_0"))
        active.register(full.get("tool_1"))
        return full, active

    def test_name_and_category(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        assert tool.name == "request_tools"
        assert tool.category == "system"
        assert tool.cacheable is False

    def test_description_lists_unloaded_tools(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        desc = tool.description
        # tool_0 and tool_1 are loaded, so should NOT appear
        assert "tool_0" not in desc
        assert "tool_1" not in desc
        # tool_2, tool_3, tool_4 are unloaded, so should appear
        assert "tool_2" in desc
        assert "tool_3" in desc
        assert "tool_4" in desc

    def test_description_all_loaded(self) -> None:
        full = ToolRegistry()
        full.register(_StubTool("tool_0", "Desc."))
        active = ToolRegistry()
        active.register(full.get("tool_0"))
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        desc = tool.description
        assert "All tools are currently loaded" in desc

    async def test_load_tools(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(tool_names=["tool_2", "tool_3"])
        assert "Loaded: tool_2, tool_3" in result
        # Verify they are now in active registry
        assert "tool_2" in active
        assert "tool_3" in active

    async def test_already_loaded(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(tool_names=["tool_0"])
        assert "Already loaded: tool_0" in result

    async def test_not_found(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(tool_names=["nonexistent"])
        assert "Not found: nonexistent" in result

    async def test_mixed_results(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(
            tool_names=["tool_2", "tool_0", "nonexistent"]
        )
        assert "Loaded: tool_2" in result
        assert "Already loaded: tool_0" in result
        assert "Not found: nonexistent" in result

    async def test_empty_names(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(tool_names=[])
        assert "No tool names provided" in result

    async def test_no_names_kwarg(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run()
        assert "No tool names provided" in result

    async def test_cannot_request_self(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        result = await tool.run(tool_names=["request_tools"])
        assert "Already loaded: request_tools" in result

    def test_description_updates_after_load(self) -> None:
        """After loading tools, the description should no longer list them."""
        import asyncio

        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        # Before: tool_2 is in the unloaded list
        assert "tool_2" in tool.description
        # Load tool_2
        asyncio.get_event_loop().run_until_complete(
            tool.run(tool_names=["tool_2"])
        )
        # After: tool_2 should no longer be in the description
        assert "tool_2" not in tool.description

    def test_parameters_schema(self) -> None:
        full, active = self._make_registries()
        tool = RequestToolsTool(all_tools=full, active_tools=active)
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "tool_names" in schema["properties"]
        assert schema["properties"]["tool_names"]["type"] == "array"
        assert "tool_names" in schema["required"]


# ======================================================================
# Integration: request_tools in ReActAgent (JSON mode)
# ======================================================================


class TestRequestToolsIntegrationJSON:
    """Integration tests for request_tools in the JSON-mode ReAct loop."""

    async def test_request_tools_registered_when_selection_active(self) -> None:
        """request_tools should be auto-registered when tool selection filters."""
        reg = _make_large_registry(TOOL_SELECTION_THRESHOLD + 1)

        # Selection returns a subset (tool_0, tool_1)
        llm = FakeLLM(
            responses=[
                _selection_response(["tool_0", "tool_1"]),
                _final_answer_response("done"),
            ]
        )
        agent = ReActAgent(llm=llm, tools=reg)

        # Verify request_tools appears in the system prompt (which lists
        # the effective tool set).
        result = await agent.run("test")
        assert result.answer == "done"

        # request_tools should be registered in the full registry too
        assert "request_tools" in agent.tools

    async def test_request_tools_not_registered_below_threshold(self) -> None:
        """request_tools should NOT be registered when all tools fit."""
        reg = ToolRegistry()
        reg.register(_StubTool("tool_0", "Desc."))

        llm = FakeLLM(
            responses=[_final_answer_response("done")]
        )
        agent = ReActAgent(llm=llm, tools=reg)
        result = await agent.run("test")
        assert result.answer == "done"
        # request_tools should NOT be in the registry
        assert "request_tools" not in agent.tools

    async def test_request_tools_loads_tool_and_uses_it(self) -> None:
        """Full flow: select tools -> request_tools -> use loaded tool."""
        reg = _make_large_registry(TOOL_SELECTION_THRESHOLD + 1)

        # Flow:
        # 1. Tool selection: pick tool_0
        # 2. LLM calls request_tools to load tool_5
        # 3. LLM calls tool_5
        # 4. LLM gives final answer
        llm = FakeLLM(
            responses=[
                _selection_response(["tool_0"]),
                _tool_call_response(
                    "request_tools", {"tool_names": ["tool_5"]}
                ),
                _tool_call_response("tool_5", {"input": "hello"}),
                _final_answer_response("used tool_5"),
            ]
        )
        agent = ReActAgent(llm=llm, tools=reg)

        result = await agent.run("test")
        assert result.answer == "used tool_5"

        # Verify tool_5 was actually called (check steps)
        tool_names_called = [
            s.action.tool_name for s in result.steps
            if s.action.type == "tool_call"
        ]
        assert "request_tools" in tool_names_called
        assert "tool_5" in tool_names_called

    async def test_request_tools_not_found_graceful(self) -> None:
        """Requesting a nonexistent tool should not crash."""
        reg = _make_large_registry(TOOL_SELECTION_THRESHOLD + 1)

        llm = FakeLLM(
            responses=[
                _selection_response(["tool_0"]),
                _tool_call_response(
                    "request_tools", {"tool_names": ["nonexistent"]}
                ),
                _final_answer_response("done"),
            ]
        )
        agent = ReActAgent(llm=llm, tools=reg)

        result = await agent.run("test")
        assert result.answer == "done"
        # The request_tools step should have an observation (not error)
        request_step = [
            s for s in result.steps
            if s.action.tool_name == "request_tools"
        ]
        assert len(request_step) == 1
        assert request_step[0].observation is not None
        assert "Not found: nonexistent" in request_step[0].observation

    async def test_request_tools_not_registered_when_fallback(self) -> None:
        """When selection falls back to all tools, request_tools not needed."""
        reg = _make_large_registry(TOOL_SELECTION_THRESHOLD + 1)

        # Selection returns bogus names -> fallback to all tools.
        # In this case effective_tools is self._tools, so request_tools
        # should NOT be registered.
        llm = FakeLLM(
            responses=[
                _selection_response(["nonexistent_a", "nonexistent_b"]),
                _final_answer_response("ok"),
            ]
        )
        agent = ReActAgent(llm=llm, tools=reg)
        result = await agent.run("test")
        assert result.answer == "ok"
        # All selection names were bogus -> fallback -> effective_tools is self._tools
        # request_tools should NOT be in the registry
        assert "request_tools" not in reg
