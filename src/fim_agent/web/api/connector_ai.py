"""AI-powered action generation and refinement for connectors."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fim_agent.core.model.types import ChatMessage
from fim_agent.db import get_session
from fim_agent.web.auth import get_current_user
from fim_agent.web.deps import get_fast_llm
from fim_agent.web.models.connector import Connector, ConnectorAction
from fim_agent.web.models.user import User
from fim_agent.web.schemas.common import ApiResponse
from fim_agent.web.schemas.connector import (
    AIActionResult,
    AIGenerateActionsRequest,
    AIRefineActionRequest,
    ActionResponse,
)
from fim_agent.web.api.connectors import _get_owned_connector, _action_to_response, _connector_to_response

router = APIRouter(prefix="/api/connectors", tags=["connector-ai"])

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM Helpers
# ---------------------------------------------------------------------------

_GENERATE_SYSTEM_PROMPT = """\
You are an API action designer. Given a connector description and a user instruction, \
generate a JSON array of API action definitions.

Each action object MUST have these fields:
- "name": string — unique action name (snake_case, e.g. "list_users")
- "description": string — what the action does
- "method": string — HTTP method (GET, POST, PUT, PATCH, DELETE)
- "path": string — relative API path (e.g. "/users/{user_id}")
- "parameters_schema": object|null — JSON Schema describing path/query parameters
- "requires_confirmation": boolean — true for destructive actions (DELETE, mutations)

Optional fields:
- "request_body_template": object|null — template for request body
- "response_extract": string|null — JMESPath expression to extract response data

Output ONLY a valid JSON array. No markdown, no commentary."""

_REFINE_SYSTEM_PROMPT = """\
You are an API connector and action editor. Given the current connector configuration, \
its existing actions, and a user instruction, output a JSON array of operations to apply.

Each operation object MUST have:
- "op": "create" | "update" | "delete" | "update_connector"

For "create" (create a new action):
- "data": object with action fields (name, description, method, path, parameters_schema, \
requires_confirmation, and optionally request_body_template, response_extract)

For "update" (update an existing action):
- "action_id": string — the ID of the action to update
- "data": object with fields to change (partial update)

For "delete" (delete an existing action):
- "action_id": string — the ID of the action to delete

For "update_connector" (update connector settings):
- "data": object with connector fields to change. Allowed fields: \
name, description, base_url, auth_type, auth_config
- auth_type must be one of: "none", "bearer", "api_key", "basic"
- auth_config is a JSON object whose shape depends on auth_type:
  - bearer: {"token": "..."}
  - api_key: {"key": "...", "header": "X-API-Key"} (header is optional, defaults to X-API-Key)
  - basic: {"username": "...", "password": "..."}
  - none: null or omit

Output ONLY a valid JSON array of operations. No markdown, no commentary."""


def _build_connector_context(connector: Connector) -> str:
    """Build a context string describing the connector and its existing actions."""
    lines = [
        f"Connector: {connector.name}",
        f"Description: {connector.description or 'N/A'}",
        f"Base URL: {connector.base_url}",
        f"Auth: {connector.auth_type}",
    ]
    if connector.auth_config:
        lines.append(f"Auth Config: {json.dumps(connector.auth_config)}")
    if connector.actions:
        lines.append(f"\nExisting actions ({len(connector.actions)}):")
        for a in connector.actions:
            lines.append(
                f"  - [{a.id}] {a.name} ({a.method} {a.path}): "
                f"{a.description or 'no description'}"
            )
    else:
        lines.append("\nNo existing actions.")
    return "\n".join(lines)


def _extract_json(text: str) -> Any:
    """Extract JSON array from LLM response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (possibly with language tag)
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return json.loads(text)


async def _llm_call(system: str, user_msg: str, retry_context: str | None = None) -> Any:
    """Call the fast LLM and parse JSON from response. Auto-retries once on parse failure."""
    llm = get_fast_llm()
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user_msg),
    ]
    if retry_context:
        messages.append(ChatMessage(role="user", content=retry_context))

    result = await llm.chat(messages=messages)
    content = result.message.content or ""
    if not content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned empty response",
        )

    try:
        return _extract_json(content)
    except (json.JSONDecodeError, ValueError) as exc:
        if retry_context is not None:
            # Already retried once — give up
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM returned invalid JSON after retry: {exc}",
            ) from exc
        # Auto-retry with error feedback
        logger.warning("LLM JSON parse failed, retrying: %s", exc)
        feedback = (
            f"Your previous response was not valid JSON. Error: {exc}\n"
            "Please output ONLY a valid JSON array, no markdown or commentary."
        )
        return await _llm_call(system, user_msg, retry_context=feedback)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{connector_id}/ai/generate-actions", response_model=ApiResponse)
async def ai_generate_actions(
    connector_id: str,
    body: AIGenerateActionsRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> ApiResponse:
    """Generate new actions for a connector using AI."""
    connector = await _get_owned_connector(connector_id, current_user.id, db)

    connector_ctx = _build_connector_context(connector)
    user_msg = f"{connector_ctx}\n\nUser instruction: {body.instruction}"
    if body.context:
        user_msg += f"\n\nAPI documentation context:\n{body.context}"

    raw_actions = await _llm_call(_GENERATE_SYSTEM_PROMPT, user_msg)
    if not isinstance(raw_actions, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM did not return a JSON array",
        )

    created: list[ActionResponse] = []
    failed: list[str] = []

    for i, item in enumerate(raw_actions):
        try:
            # Validate required fields
            name = str(item["name"])
            method = str(item.get("method", "GET")).upper()
            path = str(item["path"])

            action = ConnectorAction(
                connector_id=connector_id,
                name=name,
                description=item.get("description"),
                method=method,
                path=path,
                parameters_schema=item.get("parameters_schema"),
                request_body_template=item.get("request_body_template"),
                response_extract=item.get("response_extract"),
                requires_confirmation=bool(item.get("requires_confirmation", False)),
            )
            db.add(action)
            await db.flush()
            await db.refresh(action)
            created.append(_action_to_response(action))
        except Exception as exc:
            failed.append(f"Action #{i}: {exc}")
            logger.warning("Failed to create action #%d: %s", i, exc)

    await db.commit()

    parts = [f"Created {len(created)} action(s)."]
    if failed:
        parts.append(f"{len(failed)} action(s) failed validation.")

    result = AIActionResult(
        created=created,
        failed=failed,
        message=" ".join(parts),
    )
    return ApiResponse(data=result.model_dump())


@router.post("/{connector_id}/ai/refine-action", response_model=ApiResponse)
async def ai_refine_action(
    connector_id: str,
    body: AIRefineActionRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> ApiResponse:
    """Refine connector actions using AI instructions."""
    connector = await _get_owned_connector(connector_id, current_user.id, db)

    connector_ctx = _build_connector_context(connector)
    user_msg = f"{connector_ctx}\n\nUser instruction: {body.instruction}"
    if body.action_id:
        # Find the target action for extra context
        target = next(
            (a for a in connector.actions if a.id == body.action_id), None
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target action not found",
            )
        user_msg += (
            f"\n\nTarget action: [{target.id}] {target.name} "
            f"({target.method} {target.path})"
        )

    operations = await _llm_call(_REFINE_SYSTEM_PROMPT, user_msg)
    if not isinstance(operations, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM did not return a JSON array",
        )

    created: list[ActionResponse] = []
    updated: list[ActionResponse] = []
    deleted: list[str] = []
    failed: list[str] = []
    connector_changed = False

    for i, op_item in enumerate(operations):
        try:
            op = str(op_item.get("op", "")).lower()

            if op == "create":
                data = op_item["data"]
                action = ConnectorAction(
                    connector_id=connector_id,
                    name=str(data["name"]),
                    description=data.get("description"),
                    method=str(data.get("method", "GET")).upper(),
                    path=str(data["path"]),
                    parameters_schema=data.get("parameters_schema"),
                    request_body_template=data.get("request_body_template"),
                    response_extract=data.get("response_extract"),
                    requires_confirmation=bool(data.get("requires_confirmation", False)),
                )
                db.add(action)
                await db.flush()
                await db.refresh(action)
                created.append(_action_to_response(action))

            elif op == "update":
                action_id = str(op_item["action_id"])
                result = await db.execute(
                    select(ConnectorAction).where(
                        ConnectorAction.id == action_id,
                        ConnectorAction.connector_id == connector_id,
                    )
                )
                action = result.scalar_one_or_none()
                if action is None:
                    failed.append(f"Op #{i}: action {action_id} not found for update")
                    continue

                data = op_item.get("data", {})
                updatable = {
                    "name", "description", "method", "path",
                    "parameters_schema", "request_body_template",
                    "response_extract", "requires_confirmation",
                }
                for field, value in data.items():
                    if field in updatable:
                        if field == "method":
                            value = str(value).upper()
                        setattr(action, field, value)

                await db.flush()
                await db.refresh(action)
                updated.append(_action_to_response(action))

            elif op == "delete":
                action_id = str(op_item["action_id"])
                result = await db.execute(
                    select(ConnectorAction).where(
                        ConnectorAction.id == action_id,
                        ConnectorAction.connector_id == connector_id,
                    )
                )
                action = result.scalar_one_or_none()
                if action is None:
                    failed.append(f"Op #{i}: action {action_id} not found for delete")
                    continue
                await db.delete(action)
                deleted.append(action_id)

            elif op == "update_connector":
                data = op_item.get("data", {})
                connector_updatable = {
                    "name", "description", "base_url",
                    "auth_type", "auth_config",
                }
                for field, value in data.items():
                    if field in connector_updatable:
                        setattr(connector, field, value)
                await db.flush()
                connector_changed = True

            else:
                failed.append(f"Op #{i}: unknown operation '{op}'")
        except Exception as exc:
            failed.append(f"Op #{i}: {exc}")
            logger.warning("Failed to execute operation #%d: %s", i, exc)

    await db.commit()

    # Build connector_updated response if connector settings were changed
    connector_updated_resp = None
    if connector_changed:
        await db.refresh(connector, attribute_names=["actions"])
        connector_updated_resp = _connector_to_response(connector)

    parts: list[str] = []
    if connector_changed:
        parts.append("Updated connector settings.")
    if created:
        parts.append(f"Created {len(created)} action(s).")
    if updated:
        parts.append(f"Updated {len(updated)} action(s).")
    if deleted:
        parts.append(f"Deleted {len(deleted)} action(s).")
    if failed:
        parts.append(f"{len(failed)} operation(s) failed.")
    if not parts:
        parts.append("No operations were performed.")

    ai_result = AIActionResult(
        created=created,
        updated=updated,
        deleted=deleted,
        failed=failed,
        connector_updated=connector_updated_resp,
        message=" ".join(parts),
    )
    return ApiResponse(data=ai_result.model_dump())
