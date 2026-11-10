"""Dependency-free natural-language intent routing for WEBSTER actions.

The router only classifies requests and extracts a proposed argument string.
It never imports or executes an action. CommandRouter/Niyantrak remain
responsible for clarification, validation, and explicit execution approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ActionIntent:
    action_id: str
    arguments: str
    score: float
    alternatives: tuple[tuple[str, float], ...] = ()


_STOP = {
    "a", "an", "the", "my", "your", "our", "their", "please", "could",
    "would", "you", "can", "will", "me", "i", "want", "need", "to",
    "for", "on", "in", "at", "with", "from", "of", "it", "this",
    "that", "is", "are", "am", "was", "were", "be", "been", "being",
    "webster", "jarvis", "hey", "now", "just", "some", "something",
    "kindly", "hey", "there", "do", "does", "did",
}

# Canonical words make common spoken variants comparable without an API.
_SYNONYMS = {
    "make": "create", "build": "create", "construct": "create",
    "generate": "create", "launch": "open", "start": "open",
    "fire": "open", "bring": "open", "show": "display",
    "view": "display", "see": "display", "find": "search",
    "locate": "search", "look": "search", "hunt": "search",
    "remove": "delete", "erase": "delete", "trash": "delete",
    "duplicate": "copy", "replicate": "copy", "relocate": "move",
    "rename": "rename", "compute": "calculate", "solve": "calculate",
    "work": "calculate", "times": "multiply", "multiplied": "multiply",
    "plus": "add", "minus": "subtract", "divided": "divide",
    "analyse": "analyze", "inspect": "analyze", "examine": "analyze",
    "capture": "record", "film": "record", "snapshot": "screenshot",
    "directory": "folder", "directories": "folder", "dirs": "folder",
    "applications": "app", "application": "app", "program": "app",
    "programs": "app", "software": "app", "picture": "image",
    "photo": "image", "photograph": "image", "pictures": "image",
    "movie": "video", "clip": "video", "films": "video",
    "wifi": "network", "wi-fi": "network", "pc": "computer",
    "machine": "computer", "laptop": "computer", "desktop": "computer",
    "battery": "battery", "charge": "battery", "charging": "battery",
    "contents": "content", "documents": "document", "docs": "document",
    "files": "file", "folders": "folder", "drives": "drive",
    "volumes": "drive", "storage": "drive", "internet": "network",
    "website": "web", "webpage": "web", "browser": "web",
    "sourcecode": "code", "scripts": "code", "script": "code",
    "debugging": "debug", "errors": "error", "bugs": "error",
    "muted": "mute", "silence": "mute", "unmute": "volume",
    "louder": "volume", "quieter": "volume", "sound": "volume",
    "cursor": "pointer", "mouse": "pointer",
    "screenshot": "screenshot", "screen": "screen", "display": "screen",
}

# Intent vocabulary is deliberately separated from object vocabulary.
# This prevents a request such as "folder" from selecting a random action.
_ACTION_TERMS: dict[str, set[str]] = {
    "create_folder": {"create", "folder", "directory"},
    "create_text_file": {"create", "write", "file", "text", "document"},
    "append_text_file": {"append", "add", "write", "file", "text"},
    "read_text_file": {"read", "open", "file", "text", "content"},
    "open_file": {"open", "display", "file", "document"},
    "open_folder": {"open", "display", "folder", "directory"},
    "open_app": {"open", "launch", "app", "program"},
    "open_website": {"open", "visit", "web", "url"},
    "search_files": {"search", "find", "file"},
    "search_text_in_folder": {"search", "find", "text", "folder"},
    "find_text_in_file": {"search", "find", "text", "file"},
    "copy_file": {"copy", "duplicate", "file"},
    "move_file": {"move", "relocate", "file"},
    "rename_file": {"rename", "change", "file", "name"},
    "delete_file": {"delete", "remove", "file"},
    "create_zip_archive": {"create", "compress", "zip", "archive"},
    "extract_zip_archive": {"extract", "unzip", "zip", "archive"},
    "inspect_zip_archive": {"inspect", "list", "zip", "archive"},
    "calculate": {"calculate", "math", "solve", "expression", "multiply", "add", "subtract", "divide"},
    "convert_units": {"convert", "unit", "measurement"},
    "word_count": {"count", "word", "words", "text"},
    "text_statistics": {"analyze", "statistics", "text"},
    "compare_text_files": {"compare", "diff", "file", "text"},
    "hash_file": {"hash", "checksum", "file"},
    "file_info": {"inspect", "information", "details", "file"},
    "list_folder": {"list", "show", "folder", "directory", "files"},
    "read_screen": {"read", "screen", "display", "text", "ocr"},
    "analyse_image": {"analyze", "image", "photo", "picture"},
    "generate_image": {"create", "generate", "draw", "image"},
    "generate_video": {"create", "generate", "video"},
    "camera_record": {"record", "camera", "video"},
    "desktop_overview": {"show", "overview", "desktop", "windows"},
    "cursor_position": {"get", "where", "pointer", "position"},
    "move_cursor": {"move", "pointer", "cursor"},
    "system_status": {"show", "system", "status", "overview"},
    "battery_status": {"show", "battery", "status", "power"},
    "network_status": {"show", "network", "status", "connection"},
    "disk_volumes": {"show", "disk", "drive", "storage"},
    "uptime_status": {"show", "uptime", "running", "time"},
    "top_processes": {"show", "list", "process", "running", "app"},
    "process_summary": {"show", "summarize", "process", "running"},
    "python_environment": {"inspect", "python", "environment", "packages"},
    "check_code": {"check", "review", "debug", "code"},
    "validate_json_file": {"validate", "check", "json", "file"},
    "dns_lookup": {"lookup", "resolve", "dns", "domain"},
    "generate_uuid": {"generate", "create", "uuid", "identifier"},
    "current_datetime": {"show", "current", "date", "time"},
    "hello_webster": {"hello", "greet", "webster"},
    "clipboard_copy": {"copy", "clipboard", "text"},
    "volume_up": {"increase", "raise", "volume", "sound"},
    "volume_down": {"decrease", "lower", "volume", "sound"},
    "volume_mute": {"mute", "silence", "volume", "sound"},
    "media_play_pause": {"play", "pause", "media", "music"},
    "media_next": {"next", "skip", "media", "track"},
    "media_previous": {"previous", "back", "media", "track"},
    "lock_screen": {"lock", "screen", "computer"},
    "close_app": {"close", "quit", "exit", "app", "window"},
    "minimize_window": {"minimize", "window"},
    "maximize_window": {"maximize", "window"},
    "switch_window": {"switch", "change", "window"},
    "open_settings": {"open", "settings", "configuration"},
    "home_assistant": {"control", "home", "assistant", "device"},
    "create_code_project": {"create", "project", "code", "programming"},
    "analyse_image": {"describe", "analyze", "image", "photo"},
}

_INTENT_WORDS = {
    "create", "open", "display", "read", "search", "delete", "rename",
    "move", "copy", "calculate", "multiply", "add", "subtract", "divide",
    "record", "analyze", "generate", "check", "review", "extract",
    "compress", "play", "pause", "mute", "lock", "switch", "maximize",
    "minimize", "convert", "validate", "inspect", "list", "increase",
    "decrease", "close", "visit", "lookup", "resolve", "count", "compare",
    "append", "write", "control", "describe", "greet", "debug",
}

_PHRASE_REWRITES = (
    (r"\bhow much time has .*? been running\b", "show uptime"),
    (r"\bwhat(?:'s| is) on my screen\b", "read screen"),
    (r"\bread what(?:'s| is) on my screen\b", "read screen"),
    (r"\bopen up\b", "open"),
    (r"\bfire up\b", "open"),
    (r"\bturn (?:the )?volume up\b", "increase volume"),
    (r"\bturn (?:the )?volume down\b", "decrease volume"),
    (r"\bturn (?:the )?sound off\b", "mute volume"),
    (r"\bmake me a\b", "create a"),
    (r"\bwhat is\b", "calculate"),
)


def _canonical_words(value: str) -> list[str]:
    text = (value or "").lower().replace("’", "'")
    for pattern, replacement in _PHRASE_REWRITES:
        text = re.sub(pattern, replacement, text)
    raw = re.findall(r"[a-z][a-z0-9_'-]*|[0-9]+(?:\.[0-9]+)?", text)
    words: list[str] = []
    for word in raw:
        word = word.strip("'-")
        if not word or word in _STOP or word.isdigit():
            continue
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("ing") and len(word) > 5:
            word = word[:-3]
        elif word.endswith("ed") and len(word) > 4:
            word = word[:-2]
        elif word.endswith("s") and len(word) > 4 and not word.endswith("ss"):
            word = word[:-1]
        word = {
            "creat": "create", "writ": "write", "mak": "make",
            "delet": "delete", "calculat": "calculate",
            "generat": "generate", "debugg": "debug",
            "runn": "run", "copi": "copy", "movi": "move",
        }.get(word, word)
        words.append(_SYNONYMS.get(word, word))
    return words


def _unique(words: Iterable[str]) -> set[str]:
    return set(words)


def _argument_tail(query: str, action_id: str) -> str:
    """Extract a conservative argument tail; never invent missing values."""
    if action_id == "calculate":
        expression = query.strip()
        expression = re.sub(
            r"^(?:please\s+)?(?:calculate|compute|solve|what\s+is)\s+",
            "", expression, flags=re.I,
        )
        for pattern, symbol in (
            (r"\bmultiplied\s+by\b|\btimes\b", "*"),
            (r"\bdivided\s+by\b|\bover\b", "/"),
            (r"\bplus\b", "+"),
            (r"\bminus\b", "-"),
            (r"\bmod(?:ulo)?\b", "%"),
        ):
            expression = re.sub(pattern, symbol, expression, flags=re.I)
        return expression.strip(" ?")

    if action_id == "create_folder":
        match = re.search(
            r"\b(?:folder|directory)\b(?:\s+(?:called|named|for))?\s+(.+?)"
            r"(?:\s+(?:on|in)\s+(?:my\s+)?(desktop|documents|downloads))?$",
            query, re.I,
        )
        if match:
            name = match.group(1).strip(" \t:,-'\"")
            location = (match.group(2) or "").lower()
            name = re.sub(r"^(?:(?:called|named|for)\s+|my\s+)+", "", name, flags=re.I)
            if name:
                return f"~/{location.title()}/{name}" if location else name

    patterns = {
        "open_app": r"\b(?:open|launch|start|run|fire\s+up|bring\s+up)\s+(.+)$",
        "open_website": r"\b(?:open|visit|go\s+to)\s+(.+)$",
        "search_files": r"\b(?:find|search|locate)\s+(.+)$",
        "read_text_file": r"\b(?:read|show|open)\s+(.+)$",
        "check_code": r"\b(?:check|review|debug|inspect)\s+(?:my\s+)?code\s*(.*)$",
        "generate_image": r"\b(?:generate|create|draw)\s+(?:an?\s+)?image\s*(.*)$",
        "generate_video": r"\b(?:generate|create)\s+(?:an?\s+)?video\s*(.*)$",
        "camera_record": r"\b(?:record|film|capture)\s+(?:a\s+)?(?:video|clip)?\s*(?:from\s+)?(?:my\s+)?camera\s*(.*)$",
        "analyse_image": r"\b(?:analy[sz]e|describe|inspect)\s+(?:this\s+)?(?:image|picture|photo)\s*(.*)$",
        "create_text_file": r"\b(?:create|make|write)\s+(?:a\s+)?(?:text\s+)?file\s*(.*)$",
        "delete_file": r"\b(?:delete|remove)\s+(?:the\s+)?file\s*(.*)$",
    }
    pattern = patterns.get(action_id)
    if pattern:
        match = re.search(pattern, query, re.I)
        if match:
            return match.group(1).strip(" \t:,-'\"")
    return ""


class OfflineActionRouter:
    """Rank action metadata with weighted intent/object matching and abstention."""

    def __init__(
        self,
        minimum_score: float = 0.34,
        ambiguity_gap: float = 0.09,
        semantic_matcher: object | None = None,
    ) -> None:
        self.minimum_score = minimum_score
        self.ambiguity_gap = ambiguity_gap
        # Lazy and optional: absence of FastEmbed never breaks offline commands.
        self.semantic_matcher = semantic_matcher

    def extract_arguments(self, query: str, action_id: str) -> str:
        """Expose the same conservative extractor for multi-turn clarification."""
        return _argument_tail(query, action_id)

    def _semantic_route(self, query: str, actions: list[object]) -> ActionIntent | None:
        matcher = self.semantic_matcher
        if matcher is None:
            try:
                from assistant.local_semantic import LocalSemanticMatcher
                matcher = LocalSemanticMatcher()
                self.semantic_matcher = matcher
            except Exception:
                return None
        try:
            result = matcher.match(query, actions)
        except Exception:
            return None
        if not result:
            return None
        action_id, score, alternatives = result
        return ActionIntent(
            action_id=action_id,
            arguments=_argument_tail(query, action_id) if action_id else "",
            score=score,
            alternatives=alternatives,
        )

    def route(self, query: str, actions: Iterable[object]) -> ActionIntent | None:
        query_words = _canonical_words(query)
        request = _unique(query_words)
        if not request:
            return None

        ranked: list[tuple[float, object]] = []
        for action in actions:
            action_id = str(getattr(action, "action_id", "")).strip().lower()
            description = str(getattr(action, "description", "")).strip()
            if not action_id:
                continue

            id_terms = _unique(_canonical_words(action_id.replace("_", " ")))
            desc_terms = _unique(_canonical_words(description))
            curated = _ACTION_TERMS.get(action_id, set())
            metadata = id_terms | desc_terms | curated
            matched = request & metadata
            if not matched:
                continue

            # A generic verb or noun alone is not enough to select an action.
            intent_hits = matched & _INTENT_WORDS
            object_hits = matched - _INTENT_WORDS
            if not intent_hits or not object_hits:
                # An exact action-name phrase is a valid exception.
                exact_id = action_id.replace("_", " ")
                if exact_id not in query.lower():
                    continue

            # Prefer distinctive action-ID and curated terms over generic
            # words buried in long descriptions.
            id_hits = matched & id_terms
            curated_hits = matched & curated
            intent_score = min(len(intent_hits), 2) * 0.19
            object_score = min(len(object_hits), 3) * 0.16
            id_bonus = min(len(id_hits), 2) * 0.12
            curated_bonus = min(len(curated_hits), 3) * 0.08
            coverage = len(matched) / max(1, len(request))
            score = intent_score + object_score + id_bonus + curated_bonus
            score += min(coverage, 1.0) * 0.16

            # Penalize a match that only comes from generic description words.
            if not id_hits and not curated_hits:
                score *= 0.72
            # A request containing a distinctive action ID should win cleanly.
            if exact_id := (action_id.replace("_", " ") in query.lower()):
                score += 0.20
            ranked.append((min(score, 1.0), action))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        if not ranked or ranked[0][0] < self.minimum_score:
            # Semantic understanding is a fallback, never a prerequisite.
            # If the optional local model is unavailable, abstain safely.
            return self._semantic_route(query, list(actions))

        best_score, best = ranked[0]
        alternatives = tuple(
            (str(item.action_id), round(score, 3))
            for score, item in ranked[1:4]
            if score >= self.minimum_score
        )
        if alternatives and best_score - alternatives[0][1] < self.ambiguity_gap:
            return ActionIntent(
                "",
                "",
                round(best_score, 3),
                alternatives=((str(best.action_id), round(best_score, 3)),) + alternatives,
            )

        action_id = str(best.action_id)
        return ActionIntent(
            action_id=action_id,
            arguments=_argument_tail(query, action_id),
            score=round(best_score, 3),
            alternatives=alternatives,
        )
