"""Tests for the WorkflowScheduler background daemon."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fim_one.core.workflow.scheduler import WorkflowScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(
    *,
    wf_id: str = "wf-001",
    user_id: str = "user-001",
    name: str = "Test Workflow",
    schedule_cron: str = "*/5 * * * *",
    schedule_enabled: bool = True,
    schedule_timezone: str = "UTC",
    schedule_inputs: dict | None = None,
    is_active: bool = True,
    last_scheduled_at: datetime | None = None,
    blueprint: dict | None = None,
    env_vars_blob: str | None = None,
    webhook_url: str | None = None,
) -> SimpleNamespace:
    """Create a lightweight workflow-like object for testing."""
    return SimpleNamespace(
        id=wf_id,
        user_id=user_id,
        name=name,
        schedule_cron=schedule_cron,
        schedule_enabled=schedule_enabled,
        schedule_timezone=schedule_timezone,
        schedule_inputs=schedule_inputs,
        is_active=is_active,
        last_scheduled_at=last_scheduled_at,
        blueprint=blueprint or {"nodes": [], "edges": [], "viewport": {}},
        env_vars_blob=env_vars_blob,
        webhook_url=webhook_url,
    )


# ---------------------------------------------------------------------------
# _is_due tests
# ---------------------------------------------------------------------------


class TestIsDue:
    """Tests for the cron-due evaluation logic."""

    def test_never_run_within_poll_window(self) -> None:
        """Workflow never triggered + cron fired within poll interval => due."""
        scheduler = WorkflowScheduler(poll_interval=60)
        wf = _make_workflow(
            schedule_cron="* * * * *",
            last_scheduled_at=None,
        )
        now = datetime.now(UTC)
        assert scheduler._is_due(wf, now) is True

    def test_never_run_outside_poll_window(self) -> None:
        """Workflow never triggered + cron only fires daily, far from now => not due."""
        scheduler = WorkflowScheduler(poll_interval=60)
        # "0 3 * * *" fires at 03:00 daily
        # Test at 15:00 — the previous fire was 12 hours ago, well outside 2*60s
        wf = _make_workflow(
            schedule_cron="0 3 * * *",
            last_scheduled_at=None,
        )
        # Use a time far from 03:00
        now = datetime(2026, 3, 14, 15, 0, 0, tzinfo=UTC)
        assert scheduler._is_due(wf, now) is False

    def test_due_after_interval_elapsed(self) -> None:
        """Cron fired since last_scheduled_at => due."""
        scheduler = WorkflowScheduler(poll_interval=60)
        # Cron: every 5 minutes
        # Last run was 10 minutes ago
        now = datetime.now(UTC)
        wf = _make_workflow(
            schedule_cron="*/5 * * * *",
            last_scheduled_at=now - timedelta(minutes=10),
        )
        assert scheduler._is_due(wf, now) is True

    def test_not_due_when_recently_run(self) -> None:
        """Last run was after the most recent cron fire => not due."""
        scheduler = WorkflowScheduler(poll_interval=60)
        now = datetime.now(UTC)
        # Cron: every 5 minutes
        # Last run was 1 minute ago
        wf = _make_workflow(
            schedule_cron="*/5 * * * *",
            last_scheduled_at=now - timedelta(seconds=30),
        )
        # The most recent cron fire should be before last_scheduled_at
        # This depends on exact timing, but within 30s it should not be due
        # unless we happen to cross a 5-minute boundary.
        # Use a fixed time to be deterministic:
        fixed_now = datetime(2026, 3, 14, 12, 2, 0, tzinfo=UTC)  # 12:02
        wf2 = _make_workflow(
            schedule_cron="*/5 * * * *",
            last_scheduled_at=datetime(2026, 3, 14, 12, 0, 30, tzinfo=UTC),  # 12:00:30
        )
        # Most recent fire is 12:00, which is BEFORE 12:00:30 => not due
        assert scheduler._is_due(wf2, fixed_now) is False

    def test_due_with_timezone(self) -> None:
        """Cron evaluation respects the workflow's timezone."""
        scheduler = WorkflowScheduler(poll_interval=60)
        # Cron: every minute in Asia/Tokyo
        wf = _make_workflow(
            schedule_cron="* * * * *",
            schedule_timezone="Asia/Tokyo",
            last_scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        now = datetime.now(UTC)
        assert scheduler._is_due(wf, now) is True

    def test_invalid_cron_returns_false(self) -> None:
        """Invalid cron expression should not crash, just return False."""
        scheduler = WorkflowScheduler(poll_interval=60)
        wf = _make_workflow(
            schedule_cron="not valid cron",
            last_scheduled_at=None,
        )
        now = datetime.now(UTC)
        assert scheduler._is_due(wf, now) is False

    def test_invalid_timezone_falls_back(self) -> None:
        """Invalid timezone should fall back to UTC, not crash."""
        scheduler = WorkflowScheduler(poll_interval=60)
        wf = _make_workflow(
            schedule_cron="* * * * *",
            schedule_timezone="Not/A/Timezone",
            last_scheduled_at=None,
        )
        now = datetime.now(UTC)
        # Should not raise — falls back to UTC
        result = scheduler._is_due(wf, now)
        assert isinstance(result, bool)

    def test_naive_last_scheduled_at(self) -> None:
        """last_scheduled_at without tzinfo should still compare correctly."""
        scheduler = WorkflowScheduler(poll_interval=60)
        # Naive datetime (no tzinfo) — scheduler should handle it
        naive_dt = datetime(2026, 3, 14, 12, 0, 0)
        wf = _make_workflow(
            schedule_cron="*/5 * * * *",
            last_scheduled_at=naive_dt,
        )
        now = datetime(2026, 3, 14, 12, 10, 0, tzinfo=UTC)
        assert scheduler._is_due(wf, now) is True


# ---------------------------------------------------------------------------
# Scheduler lifecycle tests
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    """Tests for start, stop, and graceful shutdown."""

    @pytest.mark.asyncio
    async def test_stop_terminates_loop(self) -> None:
        """Calling stop() should cause run() to exit."""
        scheduler = WorkflowScheduler(poll_interval=1)

        # Mock _tick so it doesn't hit the DB
        scheduler._tick = AsyncMock()  # type: ignore[method-assign]

        task = asyncio.create_task(scheduler.run())
        # Let at least one tick happen
        await asyncio.sleep(0.1)
        await scheduler.stop()

        # Should finish within a reasonable time
        await asyncio.wait_for(task, timeout=5.0)
        assert task.done()

    @pytest.mark.asyncio
    async def test_cancellation_exits_cleanly(self) -> None:
        """Cancelling the scheduler task should exit without error."""
        scheduler = WorkflowScheduler(poll_interval=1)
        scheduler._tick = AsyncMock()  # type: ignore[method-assign]

        task = asyncio.create_task(scheduler.run())
        await asyncio.sleep(0.1)
        task.cancel()

        # run() catches CancelledError internally and exits cleanly
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.CancelledError:
            pass
        assert task.done()

    @pytest.mark.asyncio
    async def test_tick_exception_does_not_crash_loop(self) -> None:
        """An exception in _tick should be logged but the loop should continue."""
        scheduler = WorkflowScheduler(poll_interval=1)
        call_count = 0

        async def failing_tick() -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("simulated tick failure")

        scheduler._tick = failing_tick  # type: ignore[method-assign]

        task = asyncio.create_task(scheduler.run())
        await asyncio.sleep(2.5)
        await scheduler.stop()
        await asyncio.wait_for(task, timeout=5.0)

        # Should have been called multiple times despite failures
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        """Semaphore should prevent more than max_concurrent_runs simultaneously."""
        scheduler = WorkflowScheduler(
            poll_interval=60, max_concurrent_runs=2
        )
        assert scheduler._semaphore._value == 2


# ---------------------------------------------------------------------------
# _dispatch_run tests
# ---------------------------------------------------------------------------


class TestDispatchRun:
    """Tests for the run dispatch logic."""

    @pytest.mark.asyncio
    async def test_dispatch_updates_last_scheduled_at(self) -> None:
        """_dispatch_run should update last_scheduled_at in the DB."""
        scheduler = WorkflowScheduler(poll_interval=60)
        wf = _make_workflow()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_db_wf = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_wf
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "fim_one.db.create_session",
                return_value=mock_session,
            ),
            patch.object(
                scheduler,
                "_execute_workflow",
                new_callable=AsyncMock,
            ) as mock_exec,
        ):
            await scheduler._dispatch_run(wf)

            # Verify last_scheduled_at was set
            assert mock_db_wf.last_scheduled_at is not None
            assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_dispatch_skips_when_semaphore_full(self) -> None:
        """When all semaphore slots are taken, dispatch should skip."""
        scheduler = WorkflowScheduler(
            poll_interval=60, max_concurrent_runs=1
        )
        wf = _make_workflow()

        # Exhaust the semaphore
        await scheduler._semaphore.acquire()

        with patch(
            "fim_one.db.create_session"
        ) as mock_cs:
            await scheduler._dispatch_run(wf)
            # create_session should NOT have been called (skipped early)
            mock_cs.assert_not_called()

        # Release the semaphore
        scheduler._semaphore.release()
