"""Niyantrak: fail-closed permission checks for local system actions.

Only explicitly registered actions may run. Actions that affect the desktop
must receive a fresh, explicit user confirmation in the active conversation.
This module does not execute commands or inspect AI-generated code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PermissionStatus(str, Enum):
    ALLOWED = "allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    DENIED = "denied"


@dataclass(frozen=True)
class PermissionDecision:
    status: PermissionStatus
    reason: str

    @property
    def allowed(self) -> bool:
        return self.status is PermissionStatus.ALLOWED


class Niyantrak:
    """Small policy gate for known, user-facing desktop operations."""

    _CONFIRMATION_REQUIRED = frozenset({
        "open_app",
        "open_url",
        "sleep_display",
    })

    def evaluate(
        self,
        action_id: str | None,
        *,
        confirmed: bool = False,
    ) -> PermissionDecision:
        """Evaluate an action; unknown or missing IDs are denied by default."""
        normalized = (action_id or "").strip().lower()

        if not normalized:
            return PermissionDecision(
                PermissionStatus.DENIED,
                "The action has no registered permission identifier.",
            )

        if normalized not in self._CONFIRMATION_REQUIRED:
            return PermissionDecision(
                PermissionStatus.DENIED,
                f"Action '{normalized}' is not in Niyantrak's allowlist.",
            )

        if not confirmed:
            return PermissionDecision(
                PermissionStatus.CONFIRMATION_REQUIRED,
                f"Action '{normalized}' requires explicit user confirmation.",
            )

        return PermissionDecision(
            PermissionStatus.ALLOWED,
            f"Action '{normalized}' was explicitly confirmed.",
        )
