"""Niyantrak: fail-closed permission checks for local system actions.

Only explicitly registered actions may run. Desktop-affecting actions require
an explicit confirmation from the active conversation. This module is a
policy gate only: it never executes commands or evaluates generated code.
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
    """Allowlist-based policy gate for known desktop operations.

    The allowlist is deliberately static in G4.4. New system capabilities
    must be reviewed and added in code; AI output cannot register permissions.
    """

    _CONFIRMATION_REQUIRED = frozenset({
        "open_app",
        "open_url",
        "sleep_display",
    })

    @property
    def registered_actions(self) -> frozenset[str]:
        """Return the immutable set of action identifiers known to policy."""
        return self._CONFIRMATION_REQUIRED

    def requires_confirmation(self, action_id: str | None) -> bool:
        """Return whether a known action requires explicit user approval."""
        if not isinstance(action_id, str):
            return False
        return action_id.strip().lower() in self._CONFIRMATION_REQUIRED

    def evaluate(
        self,
        action_id: str | None,
        *,
        confirmed: bool = False,
    ) -> PermissionDecision:
        """Evaluate an action; unknown, malformed, or unconfirmed IDs fail closed."""
        if not isinstance(action_id, str):
            return PermissionDecision(
                PermissionStatus.DENIED,
                "The action must have a string permission identifier.",
            )

        normalized = action_id.strip().lower()

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

        # Require the literal boolean True. Truthy values such as "yes", 1,
        # or arbitrary objects must never count as user confirmation.
        if confirmed is not True:
            return PermissionDecision(
                PermissionStatus.CONFIRMATION_REQUIRED,
                f"Action '{normalized}' requires explicit user confirmation.",
            )

        return PermissionDecision(
            PermissionStatus.ALLOWED,
            f"Action '{normalized}' was explicitly confirmed.",
        )
