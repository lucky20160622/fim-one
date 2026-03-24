"""Tests for prebuilt Solution Template seeding.

Covers:
1. ensure_solution_templates creates 8 agents + 8 skills in the Market org.
2. Idempotency — calling twice does not duplicate records.
3. Each agent references exactly one skill via skill_ids.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fim_one.db.base import Base
from fim_one.web.models.agent import Agent
from fim_one.web.models.skill import Skill
from fim_one.web.platform import MARKET_ORG_ID, ensure_market_org
from fim_one.web.solution_seeds import SOLUTION_TEMPLATES, ensure_solution_templates


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite async database
# ---------------------------------------------------------------------------


@pytest.fixture()
async def async_session():
    """Create an in-memory SQLite database with all required tables."""
    import fim_one.web.models  # noqa: F401 — register all models

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
def owner_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_8_agents_and_8_skills(
    async_session: AsyncSession, owner_id: str
) -> None:
    """ensure_solution_templates should create exactly 8 agents and 8 skills."""
    # First create the Market org (required FK)
    await ensure_market_org(async_session, owner_id=owner_id)
    await async_session.flush()

    await ensure_solution_templates(
        async_session, market_org_id=MARKET_ORG_ID, owner_id=owner_id
    )
    await async_session.flush()

    # Count agents in Market org
    agent_count_result = await async_session.execute(
        select(func.count(Agent.id)).where(Agent.org_id == MARKET_ORG_ID)
    )
    agent_count = agent_count_result.scalar_one()
    assert agent_count == len(SOLUTION_TEMPLATES), (
        f"Expected {len(SOLUTION_TEMPLATES)} agents, got {agent_count}"
    )

    # Count skills in Market org
    skill_count_result = await async_session.execute(
        select(func.count(Skill.id)).where(Skill.org_id == MARKET_ORG_ID)
    )
    skill_count = skill_count_result.scalar_one()
    assert skill_count == len(SOLUTION_TEMPLATES), (
        f"Expected {len(SOLUTION_TEMPLATES)} skills, got {skill_count}"
    )


@pytest.mark.asyncio
async def test_idempotency(async_session: AsyncSession, owner_id: str) -> None:
    """Calling ensure_solution_templates twice should not create duplicates."""
    await ensure_market_org(async_session, owner_id=owner_id)
    await async_session.flush()

    # First call
    await ensure_solution_templates(
        async_session, market_org_id=MARKET_ORG_ID, owner_id=owner_id
    )
    await async_session.flush()

    # Second call
    await ensure_solution_templates(
        async_session, market_org_id=MARKET_ORG_ID, owner_id=owner_id
    )
    await async_session.flush()

    # Should still have exactly 8 agents
    agent_count_result = await async_session.execute(
        select(func.count(Agent.id)).where(Agent.org_id == MARKET_ORG_ID)
    )
    agent_count = agent_count_result.scalar_one()
    assert agent_count == len(SOLUTION_TEMPLATES)

    # Should still have exactly 8 skills
    skill_count_result = await async_session.execute(
        select(func.count(Skill.id)).where(Skill.org_id == MARKET_ORG_ID)
    )
    skill_count = skill_count_result.scalar_one()
    assert skill_count == len(SOLUTION_TEMPLATES)


@pytest.mark.asyncio
async def test_agent_skill_linkage(async_session: AsyncSession, owner_id: str) -> None:
    """Each agent should have exactly one skill linked via skill_ids."""
    await ensure_market_org(async_session, owner_id=owner_id)
    await async_session.flush()

    await ensure_solution_templates(
        async_session, market_org_id=MARKET_ORG_ID, owner_id=owner_id
    )
    await async_session.flush()

    agents_result = await async_session.execute(
        select(Agent).where(Agent.org_id == MARKET_ORG_ID)
    )
    agents = agents_result.scalars().all()

    for agent in agents:
        assert agent.skill_ids is not None, f"Agent '{agent.name}' has no skill_ids"
        assert len(agent.skill_ids) == 1, (
            f"Agent '{agent.name}' should have exactly 1 skill, got {len(agent.skill_ids)}"
        )
        # Verify the referenced skill actually exists
        skill_result = await async_session.execute(
            select(Skill).where(Skill.id == agent.skill_ids[0])
        )
        skill = skill_result.scalar_one_or_none()
        assert skill is not None, (
            f"Agent '{agent.name}' references non-existent skill {agent.skill_ids[0]}"
        )


@pytest.mark.asyncio
async def test_correct_field_values(
    async_session: AsyncSession, owner_id: str
) -> None:
    """Verify that agents and skills have correct visibility, status, and publish fields."""
    await ensure_market_org(async_session, owner_id=owner_id)
    await async_session.flush()

    await ensure_solution_templates(
        async_session, market_org_id=MARKET_ORG_ID, owner_id=owner_id
    )
    await async_session.flush()

    # Check agents
    agents_result = await async_session.execute(
        select(Agent).where(Agent.org_id == MARKET_ORG_ID)
    )
    for agent in agents_result.scalars().all():
        assert agent.visibility == "org"
        assert agent.org_id == MARKET_ORG_ID
        assert agent.user_id == owner_id
        assert agent.is_active is True
        assert agent.status == "published"
        assert agent.publish_status == "approved"
        assert agent.published_at is not None
        assert agent.execution_mode == "auto"

    # Check skills
    skills_result = await async_session.execute(
        select(Skill).where(Skill.org_id == MARKET_ORG_ID)
    )
    for skill in skills_result.scalars().all():
        assert skill.visibility == "org"
        assert skill.org_id == MARKET_ORG_ID
        assert skill.user_id == owner_id
        assert skill.is_active is True
        assert skill.status == "published"
        assert skill.publish_status == "approved"
        assert skill.published_at is not None
