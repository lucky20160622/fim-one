"""Plan analyzer that reflects on execution results.

The ``PlanAnalyzer`` evaluates whether an executed plan has achieved its
original goal, providing a confidence score and an optional synthesised
final answer.
"""

from __future__ import annotations

import logging
from typing import Any

from fim_agent.core.model import BaseLLM, ChatMessage
from fim_agent.core.utils import extract_json

from .types import AnalysisResult, ExecutionPlan

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT = """\
You are a plan evaluator.  Given a goal and the results of an execution \
plan that was designed to achieve that goal, you must assess whether the \
goal has been achieved.

Respond with a single JSON object:
{{
  "achieved": true or false,
  "confidence": <float between 0.0 and 1.0>,
  "final_answer": "<synthesised answer based on all step results, or null if not achieved>",
  "reasoning": "<explain your assessment>"
}}

Guidelines:
- Set "achieved" to true only if the goal has been fully accomplished.
- "confidence" should reflect how certain you are (1.0 = absolutely certain, \
0.0 = no confidence at all).
- If achieved, provide a clear "final_answer" that synthesises the step \
results into a coherent response to the original goal.
- If not achieved, set "final_answer" to null and explain in "reasoning" \
what is missing or went wrong.
"""


class PlanAnalyzer:
    """Evaluates whether an executed plan achieved its goal.

    Uses an LLM to reflect on the original goal and the collected step
    results, producing a structured assessment.

    Args:
        llm: The language model to use for analysis.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def analyze(
        self,
        goal: str,
        plan: ExecutionPlan,
    ) -> AnalysisResult:
        """Analyze whether the executed plan achieved the goal.

        Args:
            goal: The original high-level objective.
            plan: The execution plan with populated step results.

        Returns:
            An ``AnalysisResult`` with the LLM's assessment.
        """
        messages = self._build_messages(goal, plan)
        response_format = self._json_response_format()

        result = await self._llm.chat(
            messages,
            response_format=response_format,
        )

        content = result.message.content or ""
        return self._parse_result(content)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        goal: str,
        plan: ExecutionPlan,
    ) -> list[ChatMessage]:
        """Construct the message list for the analysis LLM call.

        Args:
            goal: The original objective.
            plan: The executed plan with step results.

        Returns:
            A list of ``ChatMessage`` objects.
        """
        step_summaries = self._format_step_results(plan)

        user_content = (
            f"Goal: {goal}\n\n"
            f"Execution plan (round {plan.current_round}):\n{step_summaries}"
        )

        return [
            ChatMessage(role="system", content=_ANALYSIS_PROMPT),
            ChatMessage(role="user", content=user_content),
        ]

    def _json_response_format(self) -> dict[str, Any] | None:
        """Return a JSON-mode response format if supported by the LLM.

        Returns:
            ``{{"type": "json_object"}}`` or ``None``.
        """
        if self._llm.abilities.get("json_mode", False):
            return {"type": "json_object"}
        return None

    @staticmethod
    def _format_step_results(plan: ExecutionPlan) -> str:
        """Format all step results into a readable summary.

        Args:
            plan: The execution plan with populated step results.

        Returns:
            A multi-line summary of each step's status and result.
        """
        if not plan.steps:
            return "(no steps in plan)"

        lines: list[str] = []
        for step in plan.steps:
            deps = ", ".join(step.dependencies) if step.dependencies else "none"
            result_text = step.result or "(no result)"
            lines.append(
                f"[{step.id}] (status: {step.status}, deps: {deps})\n"
                f"  Task: {step.task}\n"
                f"  Result: {result_text}"
            )

        return "\n\n".join(lines)

    @staticmethod
    def _parse_result(content: str) -> AnalysisResult:
        """Parse the LLM response into an ``AnalysisResult``.

        Handles malformed JSON gracefully by returning a low-confidence
        negative result.

        Args:
            content: Raw JSON string from the LLM.

        Returns:
            A parsed ``AnalysisResult`` instance.
        """
        data = extract_json(content)
        if data is None:
            logger.warning(
                "Analyzer LLM returned non-JSON content, "
                "treating as inconclusive",
            )
            return AnalysisResult(
                achieved=False,
                confidence=0.0,
                reasoning=f"Could not parse analysis response: {content}",
            )

        achieved = bool(data.get("achieved", False))

        raw_confidence = data.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        final_answer = data.get("final_answer")
        if final_answer is not None:
            final_answer = str(final_answer)

        reasoning = str(data.get("reasoning", ""))

        return AnalysisResult(
            achieved=achieved,
            confidence=confidence,
            final_answer=final_answer,
            reasoning=reasoning,
        )
