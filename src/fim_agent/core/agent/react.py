"""ReAct (Reasoning + Acting) agent implementation.

This module provides a ``ReActAgent`` that uses structured JSON output from an
LLM to drive an iterative tool-use loop.  Unlike OpenAI's native function
calling, the agent prompts the model to produce a JSON object describing the
next action, parses it, executes the corresponding tool, and feeds the
observation back into the conversation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fim_agent.core.model import BaseLLM, ChatMessage, LLMResult
from fim_agent.core.tool import ToolRegistry

from .types import Action, AgentResult, StepResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """\
You are an intelligent assistant that solves tasks by reasoning step-by-step \
and using tools when necessary.

You MUST respond with a single JSON object (no markdown, no extra text) in \
one of the following two formats:

1. To call a tool:
{{
  "type": "tool_call",
  "reasoning": "<your step-by-step reasoning>",
  "tool_name": "<name of the tool>",
  "tool_args": {{<arguments as key-value pairs>}}
}}

2. To give the final answer:
{{
  "type": "final_answer",
  "reasoning": "<your step-by-step reasoning>",
  "answer": "<your final answer>"
}}

Available tools:
{tool_descriptions}

Guidelines:
- Always explain your reasoning before acting.
- Use tools only when the task requires external information or computation.
- When you have enough information, produce a final_answer immediately.
- If a tool call fails, analyse the error and decide whether to retry with \
different arguments or produce a final answer with the information you have.
"""


class ReActAgent:
    """A ReAct agent that reasons and acts through structured JSON output.

    The agent maintains a growing conversation history.  At each iteration it
    asks the LLM for a JSON action, executes any requested tool call, appends
    the observation, and continues until a ``final_answer`` is produced or the
    maximum iteration count is reached.

    Args:
        llm: The language model backend to use for reasoning.
        tools: A registry of tools the agent may invoke.
        system_prompt: An optional override for the default system prompt.
            When provided the default ReAct instructions are *replaced*
            entirely -- make sure to include tool descriptions yourself.
        max_iterations: Safety limit on reasoning iterations.
    """

    def __init__(
        self,
        llm: BaseLLM,
        tools: ToolRegistry,
        system_prompt: str | None = None,
        max_iterations: int = 50,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._system_prompt_override = system_prompt
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, query: str) -> AgentResult:
        """Execute the ReAct loop for a given user query.

        Args:
            query: The user question or task description.

        Returns:
            An ``AgentResult`` containing the final answer and full step trace.
        """
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._build_system_prompt()),
            ChatMessage(role="user", content=query),
        ]

        steps: list[StepResult] = []
        response_format = self._json_response_format()

        for iteration in range(1, self._max_iterations + 1):
            logger.debug("ReAct iteration %d", iteration)

            result: LLMResult = await self._llm.chat(
                messages,
                response_format=response_format,
            )

            assistant_content = result.message.content or ""
            action = self._parse_action(assistant_content)

            # Append the raw assistant reply to the conversation.
            messages.append(
                ChatMessage(role="assistant", content=assistant_content),
            )

            # -- Final answer path --
            if action.type == "final_answer":
                steps.append(StepResult(action=action))
                return AgentResult(
                    answer=action.answer or "",
                    steps=steps,
                    iterations=iteration,
                )

            # -- Tool call path --
            step = await self._execute_tool_call(action)
            steps.append(step)

            # Feed the observation (or error) back as a user message so the
            # LLM can reason about the result in the next iteration.
            if step.error is not None:
                observation_text = (
                    f"Tool `{action.tool_name}` raised an error:\n{step.error}"
                )
            else:
                observation_text = (
                    f"Tool `{action.tool_name}` returned:\n{step.observation}"
                )

            messages.append(
                ChatMessage(role="user", content=observation_text),
            )

        # Max iterations exceeded -- synthesise a timeout answer.
        logger.warning(
            "ReAct loop exhausted after %d iterations", self._max_iterations,
        )
        return AgentResult(
            answer=(
                f"I was unable to complete the task within {self._max_iterations} "
                "iterations.  Here is what I gathered so far:\n"
                + self._summarise_steps(steps)
            ),
            steps=steps,
            iterations=self._max_iterations,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the system prompt, including descriptions of available tools.

        Returns:
            The full system prompt string.
        """
        if self._system_prompt_override is not None:
            return self._system_prompt_override

        tool_descriptions = self._format_tool_descriptions()
        return _SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_descriptions)

    def _format_tool_descriptions(self) -> str:
        """Format tool descriptions for inclusion in the system prompt.

        Returns:
            A human-readable listing of every registered tool with its
            name, description, and parameter schema.
        """
        tools = self._tools.list_tools()
        if not tools:
            return "(no tools available)"

        lines: list[str] = []
        for tool in tools:
            schema_str = json.dumps(tool.parameters_schema, indent=2)
            lines.append(
                f"- **{tool.name}**: {tool.description}\n"
                f"  Parameters: {schema_str}"
            )
        return "\n".join(lines)

    def _json_response_format(self) -> dict[str, Any] | None:
        """Return a JSON-mode response format dict if the LLM supports it.

        Returns:
            ``{{"type": "json_object"}}`` when the model advertises
            ``json_mode`` support, otherwise ``None``.
        """
        if self._llm.abilities.get("json_mode", False):
            return {"type": "json_object"}
        return None

    def _parse_action(self, content: str) -> Action:
        """Parse an LLM response into an ``Action``.

        Handles malformed JSON gracefully by wrapping the raw content in a
        ``final_answer`` action so the agent never crashes on unexpected
        output.

        Args:
            content: The raw string content from the assistant message.

        Returns:
            A parsed ``Action`` instance.
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("LLM returned non-JSON content, treating as final answer")
            return Action(
                type="final_answer",
                reasoning="(could not parse LLM output as JSON)",
                answer=content,
            )

        action_type = data.get("type", "final_answer")
        reasoning = data.get("reasoning", "")

        if action_type == "tool_call":
            return Action(
                type="tool_call",
                reasoning=reasoning,
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args") or {},
            )

        # Default to final_answer for any unrecognised type.
        return Action(
            type="final_answer",
            reasoning=reasoning,
            answer=data.get("answer", content),
        )

    async def _execute_tool_call(self, action: Action) -> StepResult:
        """Look up and execute a tool, returning a ``StepResult``.

        Args:
            action: A ``tool_call`` action specifying the tool name and args.

        Returns:
            A ``StepResult`` with either an observation or an error.
        """
        tool_name = action.tool_name or ""
        tool = self._tools.get(tool_name)

        if tool is None:
            error_msg = (
                f"Unknown tool '{tool_name}'. "
                f"Available tools: {[t.name for t in self._tools.list_tools()]}"
            )
            logger.warning(error_msg)
            return StepResult(action=action, error=error_msg)

        try:
            observation = await tool.run(**(action.tool_args or {}))
            return StepResult(action=action, observation=observation)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Tool '%s' raised an exception", tool_name)
            return StepResult(action=action, error=error_msg)

    @staticmethod
    def _summarise_steps(steps: list[StepResult]) -> str:
        """Produce a short textual summary of the steps taken so far.

        Args:
            steps: The list of completed steps.

        Returns:
            A newline-separated summary string.
        """
        lines: list[str] = []
        for i, step in enumerate(steps, 1):
            if step.action.type == "tool_call":
                status = "OK" if step.error is None else f"ERROR: {step.error}"
                lines.append(
                    f"  Step {i}: called {step.action.tool_name} -> {status}"
                )
            else:
                lines.append(f"  Step {i}: final answer")
        return "\n".join(lines) if lines else "(no steps taken)"
