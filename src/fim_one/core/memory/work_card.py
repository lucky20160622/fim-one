"""Structured work card for ReAct compact summaries.

The :class:`WorkCard` is a typed representation of the 9-section markdown
summary produced by ``_COMPACT_PROMPTS["react_iteration"]`` in
:mod:`fim_one.core.memory.context_guard`.

Parsing the flat markdown into a dataclass lets subsequent compactions
*merge* structured fields across rounds instead of summarising from
scratch every time — older pending tasks, errors, and decisions persist
even when the underlying history has been rolled up.

The rendered markdown shape is byte-compatible with the existing compact
system message format, so downstream consumers remain unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Cap any unbounded list field at this many items so merges cannot blow
#: up the context budget over many rounds.
_LIST_CAP: int = 10

#: Errors are the most volatile field — keep only the most recent few so
#: long debugging sessions don't accumulate stale stack traces.
_ERRORS_CAP: int = 5

#: Section header → dataclass field name.  The parser accepts both
#: ``## N. Title`` (numbered, as produced by the prompt) and a bare
#: ``# Title`` / ``## Title`` variant for robustness.
_SECTION_MAP: dict[str, str] = {
    "primary request": "primary_request",
    "key concepts": "key_concepts",
    "files and code": "files_and_code",
    "errors": "errors",
    "problem solving": "problem_solving",
    "user messages": "user_messages",
    "pending tasks": "pending_tasks",
    "current work": "current_work",
    "next step": "next_step",
}

#: Fields that are rendered and parsed as bullet lists.
_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "key_concepts",
        "files_and_code",
        "errors",
        "user_messages",
        "pending_tasks",
    },
)

#: Ordered display titles for :meth:`WorkCard.to_markdown`.
_SECTION_ORDER: list[tuple[str, str]] = [
    ("primary_request", "1. Primary Request"),
    ("key_concepts", "2. Key Concepts"),
    ("files_and_code", "3. Files and Code"),
    ("errors", "4. Errors"),
    ("problem_solving", "5. Problem Solving"),
    ("user_messages", "6. User Messages"),
    ("pending_tasks", "7. Pending Tasks"),
    ("current_work", "8. Current Work"),
    ("next_step", "9. Next Step"),
]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class WorkCard:
    """Structured representation of a ReAct compact summary.

    The 9 fields mirror the sections produced by the ``react_iteration``
    compact prompt.  String fields hold free-form paragraph content;
    list fields hold bullet items.

    Use :meth:`from_markdown` to parse the LLM output, :meth:`to_markdown`
    to render it back, and :meth:`merge` to blend a newer card into this
    one while preserving historical context.
    """

    primary_request: str = ""
    key_concepts: list[str] = field(default_factory=list)
    files_and_code: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    problem_solving: str = ""
    user_messages: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    current_work: str = ""
    next_step: str = ""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def from_markdown(cls, text: str) -> WorkCard:
        """Parse a 9-section markdown summary into a :class:`WorkCard`.

        The parser is tolerant of minor formatting variations:

        - headings may be ``#`` or ``##``
        - section numbers (``1.``/``2.``/...) are optional
        - unknown sections are silently ignored
        - missing sections leave the corresponding field at its default
        - list fields consume ``- `` / ``* `` / numbered bullets; lines
          that aren't bullets are joined onto the previous bullet as
          continuation text
        - string fields concatenate paragraph text

        Args:
            text: Raw markdown output from the compact LLM.

        Returns:
            A new :class:`WorkCard`.  All fields default to empty when
            the input is blank or unparseable.
        """
        card = cls()
        if not text or not text.strip():
            return card

        # Split into sections keyed by normalised title.
        raw_sections = _split_sections(text)

        for title, body in raw_sections.items():
            field_name = _SECTION_MAP.get(title)
            if field_name is None:
                continue  # Unknown section — skip.
            if field_name in _LIST_FIELDS:
                setattr(card, field_name, _parse_bullets(body))
            else:
                setattr(card, field_name, _parse_paragraph(body))

        return card

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the card back to the 9-section markdown format.

        Empty sections are omitted so the output stays compact.  The
        shape is byte-compatible with the prompt's expected format,
        letting downstream consumers keep treating the compact system
        message as opaque text.
        """
        parts: list[str] = []
        for field_name, title in _SECTION_ORDER:
            value = getattr(self, field_name)
            if field_name in _LIST_FIELDS:
                items: list[str] = value
                if not items:
                    continue
                parts.append(f"## {title}")
                for item in items:
                    parts.append(f"- {item}")
                parts.append("")
            else:
                text: str = value
                if not text.strip():
                    continue
                parts.append(f"## {title}")
                parts.append(text.strip())
                parts.append("")

        return "\n".join(parts).rstrip()

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    def merge(self, other: WorkCard) -> WorkCard:
        """Merge *other* (newer) into ``self`` (older) and return the result.

        Semantics:

        - **String fields** (``primary_request``, ``problem_solving``,
          ``current_work``, ``next_step``): the newer non-empty value
          wins; if *other* left the field empty, the older value is
          preserved.  This keeps the root goal stable while letting
          the active sub-goal advance.
        - **List fields** (``key_concepts``, ``files_and_code``,
          ``user_messages``, ``pending_tasks``): order-preserving
          dedup union of ``self`` followed by ``other``.  Capped at
          ``_LIST_CAP`` (10) items to prevent unbounded growth.
        - **Errors**: order-preserving union but only the most recent
          ``_ERRORS_CAP`` (5) entries are retained, favouring *other*'s
          tail since those are the freshest failures.

        The returned :class:`WorkCard` is a brand-new instance; neither
        input is mutated.
        """
        merged = WorkCard()

        # String fields: newer wins when non-empty.
        merged.primary_request = _pick_newer(
            self.primary_request, other.primary_request,
        )
        merged.problem_solving = _pick_newer(
            self.problem_solving, other.problem_solving,
        )
        merged.current_work = _pick_newer(
            self.current_work, other.current_work,
        )
        merged.next_step = _pick_newer(self.next_step, other.next_step)

        # Capped list fields.
        merged.key_concepts = _union_capped(
            self.key_concepts, other.key_concepts, _LIST_CAP,
        )
        merged.files_and_code = _union_capped(
            self.files_and_code, other.files_and_code, _LIST_CAP,
        )
        merged.user_messages = _union_capped(
            self.user_messages, other.user_messages, _LIST_CAP,
        )
        merged.pending_tasks = _union_capped(
            self.pending_tasks, other.pending_tasks, _LIST_CAP,
        )

        # Errors: keep only the most recent few across both cards.
        merged.errors = _union_tail(
            self.errors, other.errors, _ERRORS_CAP,
        )

        return merged

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def token_estimate(self) -> int:
        """Return a rough token count for the rendered card.

        Uses the same ``chars // 4`` heuristic as
        :meth:`CompactUtils.estimate_tokens`, which is good enough for
        guarding against runaway merge growth without pulling in a
        real tokeniser.
        """
        return len(self.to_markdown()) // 4


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_LEADING_NUM_RE = re.compile(r"^\d+\s*[.)]\s*")


def _normalise_title(raw: str) -> str:
    """Strip leading numbering and punctuation, lowercase for matching."""
    cleaned = raw.strip()
    cleaned = _LEADING_NUM_RE.sub("", cleaned)
    # Strip trailing punctuation (commas, colons, periods).
    cleaned = cleaned.rstrip(".:,;!? ").strip()
    return cleaned.lower()


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown into ``{normalised_title: body}``.

    Tracks fenced code blocks so headings inside ``` fences are not
    treated as section breaks.  Later occurrences of the same title
    overwrite earlier ones.
    """
    sections: dict[str, str] = {}
    current_title: str | None = None
    current_body: list[str] = []
    in_code_fence = False

    def _flush() -> None:
        if current_title is not None:
            sections[current_title] = "\n".join(current_body).strip()

    for line in text.splitlines():
        stripped = line.strip()

        # Track fenced code blocks (``` or ~~~).
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            if current_title is not None:
                current_body.append(line)
            continue

        if in_code_fence:
            if current_title is not None:
                current_body.append(line)
            continue

        match = _HEADING_RE.match(line)
        if match is not None:
            # New section → flush the previous one.
            _flush()
            current_title = _normalise_title(match.group(1))
            current_body = []
            continue

        if current_title is not None:
            current_body.append(line)

    _flush()
    return sections


def _parse_bullets(body: str) -> list[str]:
    """Extract bullet items from *body*.

    Lines starting with ``-``/``*``/``+`` or ``N.``/``N)`` become new
    items; plain continuation lines are appended to the most recent
    item (joined with a space).  Blank lines are ignored.  If no
    bullets are found but the body has content, the entire body is
    returned as a single item so information is not silently dropped.
    """
    items: list[str] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _BULLET_RE.match(line)
        if match is not None:
            items.append(match.group(1).strip())
        elif items:
            # Continuation of the previous bullet.
            items[-1] = f"{items[-1]} {line.strip()}".strip()
        else:
            # No bullet yet — treat as first implicit item.
            items.append(line.strip())

    # Deduplicate while preserving order (some prompts repeat items).
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _parse_paragraph(body: str) -> str:
    """Collapse *body* to trimmed paragraph text.

    Bullet markers are stripped so a string field receiving list-style
    content still reads cleanly.  Multiple blank lines collapse to one.
    """
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        match = _BULLET_RE.match(line)
        if match is not None:
            lines.append(match.group(1).strip())
        else:
            lines.append(stripped)
    # Drop trailing blank lines and join.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _pick_newer(older: str, newer: str) -> str:
    """Return *newer* if non-empty, otherwise *older*."""
    if newer and newer.strip():
        return newer
    return older


def _union_capped(
    older: list[str], newer: list[str], cap: int,
) -> list[str]:
    """Order-preserving dedup union, truncated to *cap* items.

    Older items come first so historical context persists; newer items
    are appended only if not already present.  When the combined list
    exceeds *cap*, the oldest items are dropped (FIFO) — the freshest
    information always survives.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*older, *newer]:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    if len(merged) > cap:
        merged = merged[-cap:]
    return merged


def _union_tail(
    older: list[str], newer: list[str], cap: int,
) -> list[str]:
    """Like :func:`_union_capped` but always retains only the tail.

    Used for the ``errors`` field where only the most recent failures
    carry diagnostic value.
    """
    return _union_capped(older, newer, cap)
