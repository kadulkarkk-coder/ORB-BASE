"""Flat, reviewed Python action folder for WEBSTER (G4.6).

Each direct child .py file (except underscore-prefixed files) may define:
    ACTION_ID = "example"
    DESCRIPTION = "What the action does"
    def run() -> str: ...

Discovery reads metadata with AST and never imports action files. A module is
imported only when its action is explicitly requested and confirmed through
Niyantrak. Python actions run with the same permissions as WEBSTER; this is
not a sandbox. Only place code you have reviewed and trust in this folder.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
import sys
from types import ModuleType
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
_ACTION_ID = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


class ActionError(Exception):
    """Raised for invalid, missing, or failed action modules."""


@dataclass(frozen=True)
class ActionInfo:
    action_id: str
    description: str
    path: Path
    content_hash: str

    @property
    def permission_id(self) -> str:
        return f"extension:{self.action_id}"


class ActionManager:
    """Discover flat action files without importing them until execution."""

    def __init__(self, folder: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.folder = Path(folder) if folder is not None else project_root / "actions"
        self.folder.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _literal_string(tree: ast.Module, name: str) -> str | None:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        return None
                    return value if isinstance(value, str) else None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                try:
                    value = ast.literal_eval(node.value) if node.value is not None else None
                except (ValueError, TypeError):
                    return None
                return value if isinstance(value, str) else None
        return None

    def discover(self) -> list[ActionInfo]:
        """Read metadata from direct .py children; do not execute their code."""
        found: list[ActionInfo] = []
        if not self.folder.is_dir():
            return found
        for path in sorted(self.folder.glob("*.py")):
            if path.name.startswith("_") or path.is_symlink():
                continue
            try:
                # Hash the exact bytes that execution will later verify. Using
                # read_text() here normalizes CRLF to LF on Windows, causing a
                # false integrity mismatch when execute() reads raw bytes.
                source_bytes = path.read_bytes()
                source = source_bytes.decode("utf-8")
                tree = ast.parse(source, filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                logger.warning("Skipping invalid action file %s: %s", path.name, exc)
                continue
            action_id = self._literal_string(tree, "ACTION_ID")
            description = self._literal_string(tree, "DESCRIPTION")
            has_run = any(
                isinstance(node, ast.FunctionDef) and node.name == "run"
                for node in tree.body
            )
            if not action_id or not _ACTION_ID.fullmatch(action_id):
                logger.warning("Skipping action with invalid ACTION_ID: %s", path.name)
                continue
            if not description or len(description) > 300 or not has_run:
                logger.warning("Skipping incomplete action file: %s", path.name)
                continue
            found.append(ActionInfo(action_id, description, path.resolve(), hashlib.sha256(source_bytes).hexdigest()))
        # Duplicate IDs are ambiguous: fail closed and exclude every duplicate.
        counts: dict[str, int] = {}
        for item in found:
            counts[item.action_id] = counts.get(item.action_id, 0) + 1
        return [item for item in found if counts[item.action_id] == 1]

    def get(self, action_id: str) -> ActionInfo | None:
        if not isinstance(action_id, str):
            return None
        return next((item for item in self.discover() if item.action_id == action_id), None)

    def execute(
        self,
        action_id: str,
        *,
        expected_hash: str | None = None,
        arguments: str = "",
    ) -> str:
        """Import and run a reviewed action with its confirmed text arguments."""
        if not isinstance(arguments, str) or len(arguments) > 2048 or any(ch in arguments for ch in "\r\n\x00"):
            raise ActionError("Action arguments must be a single line of at most 2048 characters.")
        info = self.get(action_id)
        if info is None:
            raise ActionError("That action is missing, invalid, or ambiguous.")
        if info.path.parent != self.folder.resolve():
            raise ActionError("Action file is outside the approved actions folder.")
        if expected_hash is not None and info.content_hash != expected_hash:
            raise ActionError("The action file changed after approval. Review it and request the action again.")

        module_name = f"_webster_action_{info.action_id}"
        try:
            source_bytes = info.path.read_bytes()
            actual_hash = hashlib.sha256(source_bytes).hexdigest()
            if actual_hash != info.content_hash:
                raise ActionError("The action file changed during loading. Request it again.")
            if expected_hash is not None and actual_hash != expected_hash:
                raise ActionError("The action file changed after approval. Review it and request the action again.")
            source = source_bytes.decode("utf-8")
            module = ModuleType(module_name)
            module.__file__ = str(info.path)
            # Supplied only after the caller has obtained explicit confirmation.
            module.ACTION_ARGUMENTS = arguments
            sys.modules[module_name] = module
            exec(compile(source, str(info.path), "exec"), module.__dict__)
            run = getattr(module, "run", None)
            if not callable(run):
                raise ActionError("Action does not expose a callable run().")
            result = run()
            if result is None:
                return f"Action '{action_id}' completed."
            if not isinstance(result, str):
                raise ActionError("Action run() must return text or None.")
            return result[:4000]
        except ActionError:
            raise
        except Exception as exc:
            logger.exception("Action '%s' failed.", action_id)
            raise ActionError(f"Action '{action_id}' failed: {exc}") from exc
        finally:
            sys.modules.pop(module_name, None)
