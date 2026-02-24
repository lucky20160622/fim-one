"""Built-in tool for safe file operations within a sandboxed workspace."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..base import BaseTool

_MAX_READ_BYTES: int = 50 * 1024  # 50 KB

# Workspace directory — all file operations are confined here.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_WORKSPACE_DIR = _PROJECT_ROOT / "tmp" / "workspace"
_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


class FileOpsTool(BaseTool):
    """Perform file operations (read, write, list, mkdir) in a sandboxed workspace.

    All paths are resolved relative to a workspace directory under the
    project root (``tmp/workspace/``).  Path traversal outside the
    workspace is rejected.
    """

    # ------------------------------------------------------------------
    # Tool protocol properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "file_ops"

    @property
    def category(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Perform file operations inside a sandboxed workspace directory. "
            "Supported operations: "
            '"read" — read file content (max 50 KB); '
            '"write" — write content to a file (creates parent dirs); '
            '"list" — list directory contents with sizes; '
            '"mkdir" — create a directory (with parents). '
            "All paths are relative to the workspace root."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "list", "mkdir"],
                    "description": "The file operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Target file or directory path, relative to the workspace root."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Content to write. Only used with the 'write' operation."
                    ),
                },
            },
            "required": ["operation", "path"],
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self, **kwargs: Any) -> str:
        """Dispatch to the appropriate file operation.

        Args:
            **kwargs: Must contain ``operation`` and ``path``.
                      ``content`` is required for the ``write`` operation.

        Returns:
            A human-readable result string, or an error message prefixed
            with ``[Error]``.
        """
        operation: str = kwargs.get("operation", "").strip()
        raw_path: str = kwargs.get("path", "").strip()
        content: str = kwargs.get("content", "")

        if not operation:
            return "[Error] No operation specified."
        if not raw_path:
            return "[Error] No path specified."

        # Resolve and validate the target path.
        resolved = self._resolve_safe_path(raw_path)
        if resolved is None:
            return "[Error] Path traversal detected — access denied."

        try:
            if operation == "read":
                return await asyncio.to_thread(self._read, resolved)
            elif operation == "write":
                return await asyncio.to_thread(self._write, resolved, content)
            elif operation == "list":
                return await asyncio.to_thread(self._list, resolved)
            elif operation == "mkdir":
                return await asyncio.to_thread(self._mkdir, resolved)
            else:
                return f"[Error] Unknown operation: {operation}"
        except Exception as exc:
            return f"[Error] {type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_safe_path(raw_path: str) -> Path | None:
        """Resolve *raw_path* within the workspace and validate containment.

        Returns the resolved :class:`Path` if it is safely inside the
        workspace directory, or ``None`` if path traversal is detected.
        """
        target = (_WORKSPACE_DIR / raw_path).resolve()
        # Ensure the resolved path is still under the workspace.
        if not (
            target == _WORKSPACE_DIR
            or str(target).startswith(str(_WORKSPACE_DIR) + "/")
        ):
            return None
        return target

    # ------------------------------------------------------------------
    # Operation implementations (synchronous — run via to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _read(path: Path) -> str:
        """Read file contents, truncating at ``_MAX_READ_BYTES``."""
        if not path.exists():
            return f"[Error] File not found: {path.relative_to(_WORKSPACE_DIR)}"
        if not path.is_file():
            return f"[Error] Not a file: {path.relative_to(_WORKSPACE_DIR)}"

        size = path.stat().st_size
        if size > _MAX_READ_BYTES:
            with open(path, "rb") as f:
                data = f.read(_MAX_READ_BYTES)
        else:
            data = path.read_bytes()

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return "[Error] File is not valid UTF-8 text."

        if size > _MAX_READ_BYTES:
            text += (
                f"\n\n[Truncated — showing first {_MAX_READ_BYTES // 1024} KB "
                f"of {size:,} bytes total]"
            )
        return text

    @staticmethod
    def _write(path: Path, content: str) -> str:
        """Write *content* to file, creating parent directories as needed."""
        # Ensure parent directories exist.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path.relative_to(_WORKSPACE_DIR)}"

    @staticmethod
    def _list(path: Path) -> str:
        """List directory contents with file sizes."""
        if not path.exists():
            return f"[Error] Directory not found: {path.relative_to(_WORKSPACE_DIR)}"
        if not path.is_dir():
            return f"[Error] Not a directory: {path.relative_to(_WORKSPACE_DIR)}"

        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        if not entries:
            return "(empty directory)"

        lines: list[str] = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  {entry.name}  ({_human_size(size)})")
        return "\n".join(lines)

    @staticmethod
    def _mkdir(path: Path) -> str:
        """Create directory with parents."""
        path.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {path.relative_to(_WORKSPACE_DIR)}"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _human_size(nbytes: int) -> str:
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"
