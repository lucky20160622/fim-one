"""Tests for WorkCard — structured compact summary (I.15)."""

from __future__ import annotations

from fim_one.core.memory.work_card import WorkCard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FULL_MARKDOWN = """\
## 1. Primary Request
Refactor the auth module to support OAuth2 PKCE flow.

## 2. Key Concepts
- OAuth2 PKCE
- JWT refresh tokens
- Rate limiting per IP

## 3. Files and Code
- src/fim_one/web/routers/auth.py
- src/fim_one/core/auth/oauth.py

## 4. Errors
- TypeError: missing required argument 'code_verifier'
- 401 Unauthorized on /token endpoint

## 5. Problem Solving
Diagnosed the token endpoint 401 as a missing header.
Added PKCE verifier generation helper.

## 6. User Messages
- Use SHA256 for challenge hashing
- Keep refresh token TTL at 30 days

## 7. Pending Tasks
- Wire PKCE into mobile client
- Add e2e test for refresh rotation

## 8. Current Work
Implementing the token exchange handler with PKCE verification.

## 9. Next Step
Run the new e2e test against the local dev server.
"""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestFromMarkdown:
    def test_from_markdown_parses_9_sections(self) -> None:
        card = WorkCard.from_markdown(_FULL_MARKDOWN)

        assert card.primary_request.startswith("Refactor the auth module")
        assert card.key_concepts == [
            "OAuth2 PKCE",
            "JWT refresh tokens",
            "Rate limiting per IP",
        ]
        assert card.files_and_code == [
            "src/fim_one/web/routers/auth.py",
            "src/fim_one/core/auth/oauth.py",
        ]
        assert len(card.errors) == 2
        assert "TypeError" in card.errors[0]
        assert "401 Unauthorized" in card.errors[1]
        assert "Diagnosed the token endpoint" in card.problem_solving
        assert "Added PKCE verifier" in card.problem_solving
        assert card.user_messages == [
            "Use SHA256 for challenge hashing",
            "Keep refresh token TTL at 30 days",
        ]
        assert card.pending_tasks == [
            "Wire PKCE into mobile client",
            "Add e2e test for refresh rotation",
        ]
        assert card.current_work.startswith("Implementing the token exchange")
        assert card.next_step.startswith("Run the new e2e test")

    def test_from_markdown_tolerates_missing_sections(self) -> None:
        partial = """\
## 1. Primary Request
Fix the login bug.

## 7. Pending Tasks
- Investigate session race condition
"""
        card = WorkCard.from_markdown(partial)

        assert card.primary_request == "Fix the login bug."
        assert card.pending_tasks == ["Investigate session race condition"]
        # Untouched fields stay at defaults.
        assert card.key_concepts == []
        assert card.errors == []
        assert card.current_work == ""
        assert card.next_step == ""

    def test_from_markdown_handles_empty_input(self) -> None:
        card = WorkCard.from_markdown("")
        assert card == WorkCard()
        card2 = WorkCard.from_markdown("   \n\n  ")
        assert card2 == WorkCard()

    def test_from_markdown_ignores_unknown_sections(self) -> None:
        text = """\
## 1. Primary Request
The goal.

## 99. Ephemeral Notes
- should be dropped

## 8. Current Work
Active sub-goal.
"""
        card = WorkCard.from_markdown(text)
        assert card.primary_request == "The goal."
        assert card.current_work == "Active sub-goal."

    def test_from_markdown_tolerates_single_hash_headings(self) -> None:
        text = """\
# Primary Request
Port the CLI to Go.

# Key Concepts
- goroutines
- channels
"""
        card = WorkCard.from_markdown(text)
        assert card.primary_request == "Port the CLI to Go."
        assert card.key_concepts == ["goroutines", "channels"]

    def test_from_markdown_tolerates_star_bullets(self) -> None:
        text = """\
## 2. Key Concepts
* alpha
* beta
* gamma
"""
        card = WorkCard.from_markdown(text)
        assert card.key_concepts == ["alpha", "beta", "gamma"]

    def test_from_markdown_preserves_code_fences_in_sections(self) -> None:
        # Headings inside code fences must not split the section.
        text = """\
## 3. Files and Code
- main.py:
```
## fake heading inside code
def foo(): pass
```
- helper.py
"""
        card = WorkCard.from_markdown(text)
        # Two top-level bullets; the fake heading is ignored.
        assert len(card.files_and_code) == 2
        assert card.files_and_code[1] == "helper.py"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_to_markdown_roundtrip(self) -> None:
        card = WorkCard.from_markdown(_FULL_MARKDOWN)
        rendered = card.to_markdown()
        reparsed = WorkCard.from_markdown(rendered)
        assert reparsed == card

    def test_to_markdown_omits_empty_sections(self) -> None:
        card = WorkCard(
            primary_request="Only this matters.",
            pending_tasks=["one", "two"],
        )
        rendered = card.to_markdown()
        assert "Primary Request" in rendered
        assert "Pending Tasks" in rendered
        assert "Key Concepts" not in rendered
        assert "Errors" not in rendered
        assert "Current Work" not in rendered

    def test_to_markdown_empty_card_is_empty(self) -> None:
        assert WorkCard().to_markdown() == ""


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


class TestMerge:
    def test_merge_string_fields_prefer_newer(self) -> None:
        older = WorkCard(
            primary_request="Original goal",
            problem_solving="Older analysis",
            current_work="Doing X",
            next_step="Step A",
        )
        newer = WorkCard(
            primary_request="Updated goal",
            problem_solving="",  # empty → keep older
            current_work="Doing Y",
            next_step="Step B",
        )
        merged = older.merge(newer)
        assert merged.primary_request == "Updated goal"
        assert merged.problem_solving == "Older analysis"  # preserved
        assert merged.current_work == "Doing Y"
        assert merged.next_step == "Step B"

    def test_merge_list_fields_union_dedup(self) -> None:
        older = WorkCard(
            key_concepts=["alpha", "beta"],
            files_and_code=["a.py", "b.py"],
            user_messages=["hi"],
            pending_tasks=["task1", "task2"],
        )
        newer = WorkCard(
            key_concepts=["beta", "gamma"],  # beta duplicates
            files_and_code=["b.py", "c.py"],
            user_messages=["hi", "there"],
            pending_tasks=["task3"],
        )
        merged = older.merge(newer)
        # Order preserved: older items first, then newer unique items.
        assert merged.key_concepts == ["alpha", "beta", "gamma"]
        assert merged.files_and_code == ["a.py", "b.py", "c.py"]
        assert merged.user_messages == ["hi", "there"]
        assert merged.pending_tasks == ["task1", "task2", "task3"]

    def test_merge_caps_pending_tasks_at_10(self) -> None:
        older = WorkCard(
            pending_tasks=[f"old-{i}" for i in range(8)],
        )
        newer = WorkCard(
            pending_tasks=[f"new-{i}" for i in range(8)],
        )
        merged = older.merge(newer)
        assert len(merged.pending_tasks) == 10
        # Freshest items must survive (tail-preserving cap).
        assert merged.pending_tasks[-1] == "new-7"
        # Oldest items should have been dropped.
        assert "old-0" not in merged.pending_tasks
        assert "old-1" not in merged.pending_tasks

    def test_merge_caps_all_list_fields_at_10(self) -> None:
        older = WorkCard(
            key_concepts=[f"k{i}" for i in range(8)],
            files_and_code=[f"f{i}.py" for i in range(8)],
            user_messages=[f"u{i}" for i in range(8)],
        )
        newer = WorkCard(
            key_concepts=[f"k-new-{i}" for i in range(5)],
            files_and_code=[f"f-new-{i}.py" for i in range(5)],
            user_messages=[f"u-new-{i}" for i in range(5)],
        )
        merged = older.merge(newer)
        assert len(merged.key_concepts) == 10
        assert len(merged.files_and_code) == 10
        assert len(merged.user_messages) == 10

    def test_merge_errors_keeps_recent_5(self) -> None:
        older = WorkCard(
            errors=[f"old-err-{i}" for i in range(4)],
        )
        newer = WorkCard(
            errors=[f"new-err-{i}" for i in range(4)],
        )
        merged = older.merge(newer)
        assert len(merged.errors) == 5
        # The most recent errors should survive.
        assert merged.errors[-1] == "new-err-3"
        assert "old-err-0" not in merged.errors
        assert "new-err-0" in merged.errors

    def test_merge_is_immutable(self) -> None:
        older = WorkCard(pending_tasks=["a"])
        newer = WorkCard(pending_tasks=["b"])
        merged = older.merge(newer)
        assert older.pending_tasks == ["a"]
        assert newer.pending_tasks == ["b"]
        assert merged.pending_tasks == ["a", "b"]

    def test_merge_empty_newer_preserves_older(self) -> None:
        older = WorkCard(
            primary_request="Goal",
            pending_tasks=["task1"],
            errors=["err1"],
        )
        merged = older.merge(WorkCard())
        assert merged.primary_request == "Goal"
        assert merged.pending_tasks == ["task1"]
        assert merged.errors == ["err1"]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestTokenEstimate:
    def test_token_estimate_is_reasonable(self) -> None:
        card = WorkCard.from_markdown(_FULL_MARKDOWN)
        est = card.token_estimate()
        # Non-zero and in a sane range for ~800 characters of markdown.
        assert est > 50
        assert est < 1000

    def test_token_estimate_empty_card_is_zero(self) -> None:
        assert WorkCard().token_estimate() == 0

    def test_token_estimate_scales_with_content(self) -> None:
        small = WorkCard(primary_request="x")
        large = WorkCard(primary_request="x" * 400)
        assert large.token_estimate() > small.token_estimate()
