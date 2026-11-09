"""Offline intent routing for reviewed WEBSTER extension actions.

This is deliberately dependency-free: it ranks action metadata and common
language equivalents locally. It never imports or executes an action. The
caller must still obtain Niyantrak confirmation before execution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_STOP = {
    "a", "an", "the", "my", "your", "please", "could", "would", "you",
    "can", "will", "me", "i", "want", "need", "to", "for", "on", "in",
    "at", "with", "from", "of", "it", "this", "that", "is", "are",
    "webster", "jarvis", "hey", "now", "just", "some",
}
_EQUIV = {
    "make": "create", "build": "create", "new": "create",
    "launch": "open", "start": "open", "run": "open",
    "show": "display", "view": "display", "find": "search",
    "look": "search", "locate": "search", "remove": "delete",
    "erase": "delete", "rename": "rename", "move": "move",
    "copy": "copy", "duplicate": "copy", "calculate": "calculate",
    "compute": "calculate", "work": "calculate",
    "analyse": "analyze", "analyse": "analyze",
    "capture": "record", "film": "record", "snapshot": "record",
    "screenshot": "screen", "display": "screen",
    "folder": "folder", "directory": "folder",
    "application": "app", "program": "app", "software": "app",
    "picture": "image", "photo": "image", "photograph": "image",
    "movie": "video", "clip": "video",
    "pc": "computer", "machine": "computer",
}
# These add ordinary user vocabulary to the action's own ID/description.
_INTENT_TERMS = {
    "create_folder": {"make", "build", "directory", "folder", "desktop"},
    "create_text_file": {"make", "write", "new", "document", "file", "txt"},
    "read_text_file": {"read", "open", "contents", "text", "file"},
    "append_text_file": {"add", "append", "write", "text", "file"},
    "calculate": {"math", "solve", "compute", "work", "sum", "equation"},
    "open_app": {"launch", "start", "open", "application", "program"},
    "open_file": {"open", "launch", "view", "document"},
    "open_folder": {"open", "browse", "directory", "folder"},
    "search_files": {"find", "locate", "search", "filename", "file"},
    "search_text_in_folder": {"find", "search", "inside", "text", "folder"},
    "find_text_in_file": {"find", "search", "inside", "text", "file"},
    "read_screen": {"read", "screen", "display", "ocr", "visible", "text"},
    "analyse_image": {"analyze", "image", "picture", "photo", "inspect"},
    "generate_image": {"generate", "create", "draw", "image", "picture"},
    "generate_video": {"generate", "create", "video", "movie", "clip"},
    "camera_record": {"record", "camera", "video", "capture", "film"},
    "top_processes": {"process", "running", "tasks", "applications"},
    "system_status": {"system", "status", "health", "overview"},
    "battery_status": {"battery", "charge", "power"},
    "network_status": {"network", "internet", "connection", "wifi"},
    "disk_volumes": {"disk", "drive", "storage", "volume"},
    "python_environment": {"python", "environment", "packages", "interpreter"},
    "check_code": {"check", "review", "inspect", "debug", "code", "source"},
    "create_zip_archive": {"zip", "compress", "archive", "folder", "files"},
    "extract_zip_archive": {"extract", "unzip", "archive", "zip"},
    "copy_file": {"copy", "duplicate", "file"},
    "move_file": {"move", "relocate", "file"},
    "rename_file": {"rename", "change", "filename", "file"},
    "delete_file": {"delete", "remove", "file"},
    "open_website": {"website", "webpage", "browser", "url"},
}


@dataclass(frozen=True)
class ActionIntent:
    action_id: str
    arguments: str
    score: float
    alternatives: tuple[tuple[str, float], ...] = ()


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    normalized = {_EQUIV.get(word, word) for word in words}
    return {word for word in normalized if word not in _STOP and len(word) > 1}


def _argument_tail(query: str, action_id: str) -> str:
    """Remove the natural-language intent prefix, preserving the user's data."""
    # Convert common folder-creation language into an explicit path. This is
    # still only a proposal: the action is shown to the user before execution.
    if action_id == "create_folder":
        match = re.search(
            r"(?:folder|directory)(?:\s+(?:called|named))?\s+(.+?)(?:\s+(?:on|in)\s+(?:my\s+)?(desktop|documents|downloads))?$",
            query,
            re.IGNORECASE,
        )
        if match:
            name = match.group(1).strip(" \t:,-'\"")
            location = (match.group(2) or "").lower()
            if name:
                if location:
                    return f"~/{location.title()}/{name}"
                if re.search(r"\b(?:called|named)\b", query, re.I):
                    return name
    words = action_id.replace("_", " ")
    patterns = [
        rf"\b{re.escape(words)}\b",
        rf"\b{re.escape(action_id)}\b",
    ]
    synonyms = {
        "create_folder": r"(?:make|build|create)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)",
        "calculate": r"(?:calculate|compute|solve|what\s+is)\b",
        "open_app": r"(?:open|launch|start|run)\s+",
        "read_screen": r"(?:read|show|inspect)\s+(?:my\s+)?screen",
        "camera_record": r"(?:record|film|capture)\s+(?:a\s+)?(?:video|clip)?\s*(?:from\s+)?(?:my\s+)?camera",
        "check_code": r"(?:check|review|debug|inspect)\s+(?:my\s+)?code",
        "analyse_image": r"(?:analy[sz]e|inspect|describe)\s+(?:this\s+)?(?:image|picture|photo)",
        "generate_image": r"(?:generate|create|draw)\s+(?:an?\s+)?(?:image|picture)",
        "generate_video": r"(?:generate|create)\s+(?:a\s+)?video",
    }
    if action_id in synonyms:
        patterns.insert(0, synonyms[action_id])
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return query[match.end():].strip(" \t:,-")
    # Some natural phrasings put the request before the object ("please create
    # a folder called X"). Strip polite lead-in and intent verbs as a fallback.
    tail = re.sub(r"^(?:hey\s+webster[, ]*|please\s+|can you\s+|could you\s+|would you\s+)+", "", query, flags=re.I)
    tail = re.sub(r"^(?:make|build|create|open|launch|start|run|read|show|find|search|check|review|calculate|compute|delete|remove|copy|move|rename)\s+", "", tail, flags=re.I)
    return tail.strip(" \t:,-")


class OfflineActionRouter:
    """Rank installed action metadata against natural-language requests."""

    def __init__(self, minimum_score: float = 0.28, ambiguity_gap: float = 0.10):
        self.minimum_score = minimum_score
        self.ambiguity_gap = ambiguity_gap

    def route(self, query: str, actions: Iterable[object]) -> ActionIntent | None:
        request = _tokens(query)
        if not request:
            return None
        ranked: list[tuple[float, object]] = []
        intent_verbs = {
            "create", "open", "display", "read", "search", "delete",
            "rename", "move", "copy", "calculate", "record", "analyze",
            "generate", "check", "review", "extract", "compress", "play",
            "pause", "mute", "lock", "switch", "maximize", "minimize",
            "convert", "validate", "inspect", "get", "where",
        }
        for action in actions:
            action_id = str(getattr(action, "action_id", ""))
            description = str(getattr(action, "description", ""))
            if not action_id:
                continue
            id_words = set(action_id.replace("_", " ").split())
            metadata = _tokens(description) | _tokens(action_id.replace("_", " "))
            metadata |= _INTENT_TERMS.get(action_id, set())
            # Intent/action words matter more than incidental description words.
            overlap = request & metadata
            if not overlap:
                continue
            # A lone noun ("screen", "battery", "folder") is not enough to
            # infer an action. Require an intent verb or a two-term match.
            if len(overlap) < 2 and not (request & intent_verbs):
                continue
            precision = len(overlap) / max(1, len(request))
            recall = len(overlap) / max(1, len(metadata))
            score = (0.72 * precision) + (0.28 * recall)
            if request & id_words:
                score += 0.18
            # Reward a direct intent+object pair, not just a generic verb.
            if len(overlap) >= 2:
                score += 0.08
            ranked.append((min(score, 1.0), action))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked or ranked[0][0] < self.minimum_score:
            return None
        best_score, best = ranked[0]
        alternatives = tuple(
            (str(getattr(item, "action_id", "")), round(score, 3))
            for score, item in ranked[1:4]
        )
        if alternatives and best_score - alternatives[0][1] < self.ambiguity_gap:
            return ActionIntent("", "", best_score, alternatives=((str(best.action_id), round(best_score, 3)),) + alternatives)
        action_id = str(getattr(best, "action_id", ""))
        arguments = _argument_tail(query, action_id)
        return ActionIntent(action_id, arguments, round(best_score, 3), alternatives)
