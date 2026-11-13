"""Controlled command system.

Safety model: the assistant never executes free text. Deterministic matching or
an optional local model may propose a catalogued action ID and plain-text
arguments. The router validates the proposal; Niyantrak gates execution. Model
output is never treated as code, and subprocesses use argument lists (never
`shell=True`). Side-effecting extension actions retain their approval gate.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import webbrowser

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, NamedTuple

import config
from memory import SmritiError
from knowledge import GyaanError
from system.system_info import format_duration, host_info
from assistant.offline_action_router import OfflineActionRouter


@dataclass
class CommandResult:
    handled: bool
    text: str = ""
    level: str = "assistant"
    requires_confirmation: bool = False
    action: Callable[[], str] | None = None
    speak: bool = True
    ui_action: str | None = None
    action_id: str | None = None


NOT_HANDLED = CommandResult(handled=False)


class AppTarget(NamedTuple):
    """One launchable app and every name a user might call it."""

    label: str
    macos: str | None
    windows: str | None
    linux: str | None
    aliases: tuple[str, ...]


# ---------------------------------------------------------------------
# ALLOWED APPLICATIONS
# ---------------------------------------------------------------------

_APPS: tuple[AppTarget, ...] = (
    AppTarget("the browser", None, None, None,
              ("browser", "web browser", "default browser", "internet")),
    AppTarget("Google Chrome", "Google Chrome", "chrome", "google-chrome",
              ("chrome", "google chrome", "chrome browser", "google")),
    AppTarget("Brave Browser", "Brave Browser", "brave", "brave-browser",
              ("brave", "brave browser")),
    AppTarget("Safari", "Safari", None, None, ("safari",)),
    AppTarget("Visual Studio Code", "Visual Studio Code", "code", "code",
              ("vscode", "vs code", "visual studio code", "visual studio",
               "code", "vs", "vsc", "v s code", "microsoft vs code")),
    AppTarget("Cursor", "Cursor", "cursor", "cursor",
              ("cursor", "cursor ide", "cursor editor")),
    AppTarget("Antigravity IDE", "Antigravity IDE", "antigravity", "antigravity",
              ("antigravity", "antigravity ide", "anti gravity")),
    AppTarget("Terminal", "Terminal", "wt", "x-terminal-emulator",
              ("terminal", "console", "shell", "command line")),
    AppTarget("Finder", "Finder", "explorer", "nautilus",
              ("finder", "files", "file manager", "explorer")),
    AppTarget("Spotify", "Spotify", "spotify", "spotify",
              ("spotify", "music", "spotify app")),
    AppTarget("Notion", "Notion", "notion", "notion",
              ("notion", "notion app")),
    AppTarget("Obsidian", "Obsidian", "obsidian", "obsidian",
              ("obsidian", "obsidian app", "my notes", "notes")),
    AppTarget("Claude", "Claude", "claude", "claude",
              ("claude", "claude app", "claude desktop")),
    AppTarget("Perplexity", "Perplexity", "perplexity", "perplexity",
              ("perplexity", "perplexity app")),
    AppTarget("Telegram", "Telegram", "telegram", "telegram-desktop",
              ("telegram", "telegram app")),
    AppTarget("WhatsApp", "WhatsApp", "whatsapp", "whatsapp",
              ("whatsapp", "whats app", "what's app", "whatsapp app")),
    AppTarget("Todoist", "Todoist", "todoist", "todoist",
              ("todoist", "to doist", "todo list", "tasks")),
    AppTarget("Zoom", "zoom.us", "zoom", "zoom",
              ("zoom", "zoom us", "zoom app", "zoom meeting")),
    AppTarget("VLC", "VLC", "vlc", "vlc",
              ("vlc", "vlc player", "video player")),
    AppTarget("Microsoft Excel", "Microsoft Excel", "excel", "libreoffice",
              ("excel", "microsoft excel", "ms excel", "spreadsheet")),
    AppTarget("Android Studio", "Android Studio", "studio64", "android-studio",
              ("android studio", "androidstudio")),
)


_ACTION_REQUEST_RE = re.compile(
    r"\b(?:please|can you|could you|would you|help me|i need|i want|"
    r"make|create|build|write|append|read|open|launch|start|run|find|search|"
    r"locate|move|copy|rename|delete|remove|organize|tidy|sort|arrange|"
    r"calculate|compute|convert|check|review|debug|inspect|analy[sz]e|"
    r"generate|draw|record|capture|play|pause|mute|increase|decrease|"
    r"close|minimize|maximize|switch|show|list|extract|compress|validate|"
    r"lookup|resolve|control|compare|count)\b",
    re.IGNORECASE,
)


def _squash(text: str) -> str:
    """Normalize spoken or typed application names."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _build_alias_index() -> dict[str, AppTarget]:
    index: dict[str, AppTarget] = {}

    for app in _APPS:
        for alias in (*app.aliases, app.label):
            key = _squash(alias)
            if key:
                index.setdefault(key, app)

    return index


_ALIAS_INDEX = _build_alias_index()


_OPEN_RE = re.compile(
    r"\b(?:open|launch|start|run|fire\s+up|bring\s+up|pull\s+up)\s+(.+)$",
    re.IGNORECASE,
)

_OPEN_FILLER = re.compile(
    r"^(?:up\s+|the\s+|my\s+|an?\s+)+|"
    r"\s+(?:app|application|please|for me|now|window)\s*$",
    re.IGNORECASE,
)

_URL_RE = re.compile(
    r"^https?://[\w.-]+(?::\d+)?(?:/[^\s]*)?$",
    re.IGNORECASE,
)


# =====================================================================
# COMMAND ROUTER
# =====================================================================

class CommandRouter:
    """Matches user text against the supported command set."""

    def __init__(
        self,
        stats_provider: Callable[[], object] | None = None,
        engine_name: Callable[[], str] | None = None,
        memory_provider: object | None = None,
        gyaan_provider: object | None = None,
        action_provider: object | None = None,
        action_planner: Callable[[str, list[object]], object | None] | None = None,
    ) -> None:
        self._stats = stats_provider or (lambda: None)
        self._engine_name = engine_name or (lambda: "unknown")
        self._memory = memory_provider
        self._gyaan = gyaan_provider
        self._actions = action_provider
        self._action_planner = action_planner
        self._pending_action_context: tuple[str, str] | None = None

    # -----------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------

    def set_memory_provider(self, memory_provider: object | None) -> None:
        """Attach or replace the persistent memory provider."""
        self._memory = memory_provider

    def set_gyaan_provider(self, gyaan_provider: object | None) -> None:
        """Attach or replace the local knowledge provider."""
        self._gyaan = gyaan_provider

    def set_action_provider(self, action_provider: object | None) -> None:
        """Attach or replace the reviewed action provider."""
        self._actions = action_provider

    def set_action_planner(
        self,
        action_planner: Callable[[str, list[object]], object | None] | None,
    ) -> None:
        """Attach a local model planner; its output is always validated here."""
        self._action_planner = action_planner

    def route(self, text: str) -> CommandResult:
        raw_query = (text or "").strip().rstrip("?!.")
        if not raw_query:
            return NOT_HANDLED

        # Actions are explicit commands; no AI-generated text can invoke them.
        action_result = self._route_actions(raw_query)
        if action_result is not None:
            return action_result

        # Explicit knowledge and memory commands are handled locally.
        gyaan_result = self._route_gyaan(raw_query)
        if gyaan_result is not None:
            return gyaan_result

        memory_result = self._route_memory(raw_query)
        if memory_result is not None:
            return memory_result

        query = raw_query.lower()

        for matcher, handler in self._table():
            if matcher(query):
                return handler(query)

        return NOT_HANDLED

    def help_text(self) -> str:
        return (
            "Supported commands: "
            "status · cpu · memory · disk · battery · network · "
            "time · date · uptime · sysinfo · engine · "
            "open <app or https URL> · sleep display · "
            "clear · quit · help.\n\n"
            "Smriti memory commands:\n"
            "remember <key> = <value> · "
            "recall <key> · "
            "list memories · "
            "forget <key>.\n\n"
            "Gyaan knowledge commands:\n"
            "knowledge add <title> = <content> · "
            "knowledge search <query> · list knowledge · "
            "knowledge delete <title>.\n\n"
            "Actions: describe what you want in everyday language; I will match it locally.\n"
            "For example: 'make a folder for my project', 'calculate 18 times 24', "
            "or 'read the text on my screen'.\n\n"
            "If a request is ambiguous, I will ask. Actions require confirmation before running.\n\n"
            "You can also use: actions · run action <action_id> [arguments]."
        )

    # -----------------------------------------------------------------
    # G4.6 ACTIONS FOLDER COMMANDS
    # -----------------------------------------------------------------

    def _route_actions(self, raw_query: str) -> CommandResult | None:
        """Resolve natural language to an installed action without cloud AI."""
        query = raw_query.strip()
        if query.casefold() in {"cancel", "never mind", "nevermind"} and self._pending_action_context:
            self._pending_action_context = None
            return CommandResult(True, "Action request cancelled.")

        if query.casefold() in {"actions", "list actions", "show actions"}:
            return self._cmd_list_actions()

        # Keep the explicit form for diagnostics and power users.
        match = re.fullmatch(
            r"run action\s+([a-z][a-z0-9_]{1,47})(?:\s+(.+))?",
            query,
            re.IGNORECASE,
        )
        if match:
            arguments = (match.group(2) or "").strip()
            if len(arguments) > 2048 or any(ch in arguments for ch in "\r\n\x00"):
                return CommandResult(
                    True,
                    "Action arguments must be a single line of at most 2048 characters.",
                    level="warn",
                )
            return self._cmd_run_action(match.group(1).lower(), arguments)

        if self._actions is None:
            return None

        reserved = {
            "action_manager", "battery_status", "current_datetime",
            "disk_volumes", "network_status", "open_app",
            "system_status", "uptime_status",
        }
        available = [
            item for item in self._actions.discover()
            if item.action_id not in reserved
        ]
        if not available:
            return None

        # Continue a clarification turn before trying to classify it as a new request.
        if self._pending_action_context is not None:
            pending_id, original_query = self._pending_action_context
            combined_query = f"{original_query} {query}".strip()
            pending_router = OfflineActionRouter()
            arguments = pending_router.extract_arguments(combined_query, pending_id)
            if not arguments:
                return CommandResult(
                    True,
                    f"I still need the details for '{pending_id}'. "
                    "Please provide the missing name, path, file, app, or description.",
                    level="warn",
                    speak=False,
                )
            self._pending_action_context = None
            if len(arguments) > 2048 or any(ch in arguments for ch in "\r\n\x00"):
                return CommandResult(True, "The extracted action details are invalid or too long.", level="warn")
            return self._cmd_run_action(pending_id, arguments)

        # Deterministic routing remains first. If it abstains, an optional
        # local LLM may propose a structured intent for natural paraphrases.
        intent = OfflineActionRouter().route(query, available)
        if intent is None and self._action_planner is not None and _ACTION_REQUEST_RE.search(query):
            try:
                proposal = self._action_planner(query, available)
            except Exception:
                proposal = None
            allowed_ids = {item.action_id for item in available}
            if (
                proposal is not None
                and getattr(proposal, "action_id", None) in allowed_ids
                and isinstance(getattr(proposal, "arguments", None), str)
                and len(proposal.arguments) <= 2048
                and not any(ch in proposal.arguments for ch in "\r\n\x00")
            ):
                intent = proposal

        if intent is None:
            return None

        # A close score means the request could refer to more than one action.
        # Never choose silently: show the candidates and ask for clarification.
        if not intent.action_id:
            choices = ", ".join(
                f"{action_id} ({score:.2f})"
                for action_id, score in intent.alternatives
            )
            return CommandResult(
                True,
                "I found more than one possible action. Which one did you mean? "
                + choices,
                level="warn",
                speak=False,
            )

        arguments = intent.arguments
        if len(arguments) > 2048 or any(ch in arguments for ch in "\r\n\x00"):
            return CommandResult(
                True,
                "The extracted action details must be a single line of at most 2048 characters.",
                level="warn",
            )
        required_arguments = {
            "create_folder", "create_text_file", "open_app", "open_website",
            "search_files", "read_text_file", "check_code", "generate_image",
            "generate_video", "camera_record", "analyse_image", "delete_file",
        }
        if intent.action_id in required_arguments and not arguments:
            self._pending_action_context = (intent.action_id, query)
            prompts = {
                "create_folder": "What should I name the folder, and where should I put it?",
                "create_text_file": "What should the text file be called or contain?",
                "open_app": "Which application should I open?",
                "open_website": "Which website should I open?",
                "search_files": "What file or filename should I search for?",
                "read_text_file": "Which text file should I read?",
                "check_code": "Please provide the code or its file path.",
                "generate_image": "Describe the image you want to create.",
                "generate_video": "Describe the video you want to create.",
                "camera_record": "How long should the camera recording be?",
                "analyse_image": "Which image should I analyse?",
                "delete_file": "Which file do you want to delete?",
            }
            return CommandResult(
                True,
                prompts.get(intent.action_id, "Please provide the missing details."),
                level="assistant",
                speak=False,
            )
        return self._cmd_run_action(intent.action_id, arguments)

    def _cmd_list_actions(self) -> CommandResult:
        if self._actions is None:
            return CommandResult(True, "The actions folder is unavailable.", level="warn")
        items = self._actions.discover()
        if not items:
            return CommandResult(True, "No valid actions are installed in the actions folder.")
        lines = [f"{item.action_id} — {item.description}" for item in items]
        return CommandResult(True, "Available reviewed actions:\n" + "\n".join(lines), speak=False)

    def _cmd_run_action(self, action_id: str, arguments: str = "") -> CommandResult:
        if self._actions is None:
            return CommandResult(True, "The actions folder is unavailable.", level="warn")
        item = self._actions.get(action_id)
        if item is None:
            return CommandResult(True, f"No valid action named '{action_id}' was found.", level="warn")
        argument_note = f"\nArguments: {arguments}" if arguments else ""
        return CommandResult(
            True,
            f"Run action '{item.action_id}'?\n{item.description}{argument_note}\n\nThis action runs as your current user after confirmation.",
            requires_confirmation=True,
            action=lambda: self._actions.execute(item.action_id, expected_hash=item.content_hash, arguments=arguments),
            action_id=item.permission_id,
        )

    # -----------------------------------------------------------------
    # GYAAN KNOWLEDGE COMMANDS
    # -----------------------------------------------------------------

    def _route_gyaan(self, raw_query: str) -> CommandResult | None:
        query = raw_query.strip()
        if re.fullmatch(r"list knowledge", query, re.IGNORECASE):
            return self._cmd_list_knowledge()
        match = re.fullmatch(r"knowledge\s+add\s+(.+?)\s*=\s*(.+)", query, re.IGNORECASE)
        if match:
            return self._cmd_add_knowledge(match.group(1).strip(), match.group(2).strip())
        match = re.fullmatch(r"knowledge\s+search\s+(.+)", query, re.IGNORECASE)
        if match:
            return self._cmd_search_knowledge(match.group(1).strip())
        match = re.fullmatch(r"knowledge\s+delete\s+(.+)", query, re.IGNORECASE)
        if match:
            return self._cmd_delete_knowledge(match.group(1).strip())
        return None

    def _require_gyaan(self):
        if self._gyaan is None:
            raise GyaanError("Gyaan knowledge storage is unavailable.")
        return self._gyaan

    def _cmd_add_knowledge(self, title: str, content: str) -> CommandResult:
        try:
            self._require_gyaan().add(title, content, source="User-provided")
            return CommandResult(True, f"Saved '{title}' to Gyaan.")
        except (GyaanError, ValueError) as exc:
            return CommandResult(True, f"Could not save knowledge: {exc}", level="warn")

    def _cmd_search_knowledge(self, query: str) -> CommandResult:
        try:
            items = self._require_gyaan().search(query, limit=5)
            if not items:
                return CommandResult(True, f"Gyaan found no matches for '{query}'.")
            lines = [f"{item['title']} [Source: {item['source']}]\n{item['content'][:500]}" for item in items]
            return CommandResult(True, "Gyaan results (sources shown per item):\n\n" + "\n\n".join(lines), speak=False)
        except (GyaanError, ValueError) as exc:
            return CommandResult(True, f"Could not search Gyaan: {exc}", level="warn")

    def _cmd_list_knowledge(self) -> CommandResult:
        try:
            items = self._require_gyaan().list_items(limit=30)
            if not items:
                return CommandResult(True, "Gyaan has no saved knowledge yet.")
            lines = [f"{item['title']} [Source: {item['source']}]" for item in items]
            return CommandResult(True, "Gyaan library:\n" + "\n".join(lines), speak=False)
        except GyaanError as exc:
            return CommandResult(True, f"Could not list Gyaan: {exc}", level="warn")

    def _cmd_delete_knowledge(self, title: str) -> CommandResult:
        try:
            deleted = self._require_gyaan().delete(title)
            message = f"Deleted '{title}' from Gyaan." if deleted else f"No Gyaan item named '{title}'."
            return CommandResult(True, message)
        except (GyaanError, ValueError) as exc:
            return CommandResult(True, f"Could not delete knowledge: {exc}", level="warn")

    # -----------------------------------------------------------------
    # SMRITI MEMORY COMMANDS
    # -----------------------------------------------------------------

    def _route_memory(self, raw_query: str) -> CommandResult | None:
        """Handle explicit persistent-memory commands."""

        query = raw_query.strip()

        if re.fullmatch(
            r"(?:list|show) memories",
            query,
            re.IGNORECASE,
        ):
            return self._cmd_list_memories()

        match = re.fullmatch(
            r"remember\s+(.+?)\s*(?:=|\s+as\s+)\s*(.+)",
            query,
            re.IGNORECASE,
        )

        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()

            return self._cmd_remember(key, value)

        match = re.fullmatch(
            r"recall\s+(.+)",
            query,
            re.IGNORECASE,
        )

        if match:
            return self._cmd_recall(match.group(1).strip())

        match = re.fullmatch(
            r"forget\s+(.+)",
            query,
            re.IGNORECASE,
        )

        if match:
            return self._cmd_forget(match.group(1).strip())

        return None

    def _require_memory(self):
        """Return the memory provider or raise a controlled error."""

        if self._memory is None:
            raise SmritiError("Smriti memory is unavailable.")

        return self._memory

    def _cmd_remember(self, key: str, value: str) -> CommandResult:
        try:
            memory = self._require_memory()
            memory.save(key, value, "general")

            return CommandResult(
                True,
                f"I've saved '{key}' to Smriti.",
            )

        except (SmritiError, ValueError) as exc:
            return CommandResult(
                True,
                f"Could not save that memory: {exc}",
                level="warn",
            )

    def _cmd_recall(self, key: str) -> CommandResult:
        try:
            memory = self._require_memory()
            item = memory.get(key)

            if item is None:
                return CommandResult(
                    True,
                    f"I couldn't find a memory called '{key}'.",
                )

            return CommandResult(
                True,
                f"{item['memory_key']}: {item['memory_value']}",
            )

        except (SmritiError, ValueError) as exc:
            return CommandResult(
                True,
                f"Could not retrieve that memory: {exc}",
                level="warn",
            )

    def _cmd_list_memories(self) -> CommandResult:
        try:
            memory = self._require_memory()
            items = memory.list_memories(limit=50)

            if not items:
                return CommandResult(
                    True,
                    "Smriti has no saved memories yet.",
                )

            lines = [
                f"{item['memory_key']}: {item['memory_value']}"
                for item in items
            ]

            return CommandResult(
                True,
                "Here are your saved memories:\n" + "\n".join(lines),
                speak=False,
            )

        except (SmritiError, ValueError) as exc:
            return CommandResult(
                True,
                f"Could not list memories: {exc}",
                level="warn",
            )

    def _cmd_forget(self, key: str) -> CommandResult:
        try:
            memory = self._require_memory()
            deleted = memory.delete(key)

            if deleted:
                return CommandResult(
                    True,
                    f"I've deleted the memory '{key}'.",
                )

            return CommandResult(
                True,
                f"I couldn't find a memory called '{key}'.",
            )

        except (SmritiError, ValueError) as exc:
            return CommandResult(
                True,
                f"Could not delete that memory: {exc}",
                level="warn",
            )

    # -----------------------------------------------------------------
    # COMMAND MATCHING TABLE
    # -----------------------------------------------------------------

    def _table(
        self,
    ) -> list[tuple[Callable[[str], bool], Callable[[str], CommandResult]]]:

        def has(*words: str) -> Callable[[str], bool]:
            return lambda q: any(word in q for word in words)

        def exact(*words: str) -> Callable[[str], bool]:
            return lambda q: q in words

        return [
            (exact("help", "commands", "what can you do"), self._cmd_help),
            (exact("clear", "clear log", "cls"), self._cmd_clear),
            (
                exact(
                    "quit", "exit", "shut down", "shutdown",
                    "close", "goodbye", "power down",
                ),
                self._cmd_quit,
            ),

            # Explicit app-opening commands take priority.
            (
                lambda q: _OPEN_RE.search(q) is not None,
                self._cmd_open,
            ),

            (has("system status", "status report", "all systems"), self._cmd_status),
            (exact("status"), self._cmd_status),
            (has("cpu"), self._cmd_cpu),

            # "memory" and "ram" remain system RAM commands.
            # Smriti has already handled its explicit commands above.
            (has("memory", "ram"), self._cmd_memory),

            (has("disk", "storage"), self._cmd_disk),
            (has("battery", "power level"), self._cmd_battery),
            (has("network", "internet", "online"), self._cmd_network),
            (has("uptime"), self._cmd_uptime),
            (has("what time", "the time", "current time"), self._cmd_time),
            (exact("time"), self._cmd_time),
            (has("what date", "the date", "today's date"), self._cmd_date),
            (exact("date"), self._cmd_date),
            (
                has("sysinfo", "system info", "what machine", "host info"),
                self._cmd_sysinfo,
            ),
            (
                has("which engine", "what engine", "ai status"),
                self._cmd_engine,
            ),
            (exact("engine"), self._cmd_engine),
            (
                has("sleep display", "sleep the display", "lock screen"),
                self._cmd_sleep_display,
            ),
        ]

    # -----------------------------------------------------------------
    # EXISTING COMMAND HANDLERS
    # -----------------------------------------------------------------

    def _cmd_help(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            self.help_text(),
            speak=False,
        )

    def _cmd_clear(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            "Log cleared.",
            ui_action="clear_log",
            speak=False,
        )

    def _cmd_quit(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            f"Goodbye, {config.USER_NAME}.",
            requires_confirmation=True,
            ui_action="quit",
        )

    def _cmd_status(self, _query: str) -> CommandResult:
        stats = self._stats()

        if stats is None:
            return CommandResult(
                True,
                "System metrics are not available yet.",
            )

        return CommandResult(
            True,
            stats.summary_for_assistant(),
        )

    def _metric(
        self,
        attr: str,
        label: str,
        fmt: str = "{:.0f} percent",
    ) -> CommandResult:

        stats = self._stats()
        value = getattr(stats, attr, None) if stats is not None else None

        if value is None:
            return CommandResult(
                True,
                f"{label} is not available on this machine.",
            )

        return CommandResult(
            True,
            f"{label} is at {fmt.format(value)}.",
        )

    def _cmd_cpu(self, _query: str) -> CommandResult:
        return self._metric("cpu_percent", "CPU load")

    def _cmd_memory(self, _query: str) -> CommandResult:
        return self._metric("memory_percent", "Memory usage")

    def _cmd_disk(self, _query: str) -> CommandResult:
        return self._metric("disk_percent", "Disk usage")

    def _cmd_battery(self, _query: str) -> CommandResult:
        stats = self._stats()

        if stats is None or stats.battery_percent is None:
            return CommandResult(
                True,
                "No battery is present — running on AC power.",
            )

        state = "charging" if stats.battery_plugged else "discharging"

        return CommandResult(
            True,
            f"Battery at {stats.battery_percent:.0f} percent and {state}.",
        )

    def _cmd_network(self, _query: str) -> CommandResult:
        stats = self._stats()

        if stats is None or stats.net_online is None:
            return CommandResult(
                True,
                "Network state is unknown.",
            )

        return CommandResult(
            True,
            "Network interfaces are up."
            if stats.net_online
            else "No network interface is up.",
        )

    def _cmd_uptime(self, _query: str) -> CommandResult:
        stats = self._stats()

        uptime = (
            getattr(stats, "app_uptime", 0.0)
            if stats is not None
            else 0.0
        )

        return CommandResult(
            True,
            f"Interface uptime is {format_duration(uptime)}.",
        )

    def _cmd_time(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            f"The time is {datetime.now().strftime('%H:%M')}.",
        )

    def _cmd_date(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            f"Today is {datetime.now().strftime('%A, %d %B %Y')}.",
        )

    def _cmd_sysinfo(self, _query: str) -> CommandResult:
        info = host_info()

        cores = (
            f"{info.cpu_cores} logical cores"
            if info.cpu_cores
            else "unknown core count"
        )

        return CommandResult(
            True,
            f"Running on {info.hostname}: {info.summary}, "
            f"{cores}, Python {info.python}.",
        )

    def _cmd_engine(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            f"The active AI engine is {self._engine_name()}.",
        )

    def _cmd_open(self, query: str) -> CommandResult:
        match = _OPEN_RE.search(query)
        target = (match.group(1) if match else "").strip()

        if not target:
            return CommandResult(
                True,
                "Tell me what to open.",
                level="warn",
            )

        if _URL_RE.match(target):
            url = target

            return CommandResult(
                True,
                f"Open {url} in the browser?",
                requires_confirmation=True,
                action=lambda: _open_url(url),
                action_id="open_url",
            )

        cleaned = _OPEN_FILLER.sub("", target).strip()

        app = (
            _ALIAS_INDEX.get(_squash(cleaned))
            or _ALIAS_INDEX.get(_squash(target))
        )

        if app is None:
            names = ", ".join(sorted({app.label for app in _APPS}))

            return CommandResult(
                True,
                f"'{target}' is not on the allowed list. "
                f"I can open: {names} — or any https URL.",
                level="warn",
            )

        return CommandResult(
            True,
            f"Open {app.label}?",
            requires_confirmation=True,
            action=lambda: _open_app(app),
            action_id="open_app",
        )

    def _cmd_sleep_display(self, _query: str) -> CommandResult:
        return CommandResult(
            True,
            "Put the display to sleep?",
            requires_confirmation=True,
            action=_sleep_display,
            action_id="sleep_display",
        )


# =====================================================================
# SIDE-EFFECTING HELPERS
# =====================================================================

def _open_url(url: str) -> str:
    try:
        webbrowser.open(url)

    except Exception as exc:
        return f"Could not open the browser: {exc}"

    return f"Opened {url}."


def _open_app(app: AppTarget) -> str:
    quiet = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }

    try:
        if sys.platform == "darwin":
            if app.macos is None:
                webbrowser.open("about:blank")
                return "Opened the browser."

            result = subprocess.run(
                ["open", "-a", app.macos],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                return f"{app.label} does not appear to be installed."

        elif sys.platform == "win32":
            if app.windows is None:
                webbrowser.open("about:blank")
                return "Opened the browser."

            subprocess.Popen(
                ["cmd", "/c", "start", "", app.windows],
                **quiet,
            )

        else:
            if app.linux is None:
                webbrowser.open("about:blank")
                return "Opened the browser."

            exe = shutil.which(app.linux)

            if not exe:
                return f"{app.label} was not found on this system."

            subprocess.Popen([exe], **quiet)

    except OSError as exc:
        return f"Could not launch {app.label}: {exc}"

    return f"Opened {app.label}."


def _sleep_display() -> str:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["pmset", "displaysleepnow"],
                stderr=subprocess.DEVNULL,
            )

        elif sys.platform == "win32":
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Add-Type '[DllImport(\"user32.dll\")]"
                    "public static extern int SendMessage(int hWnd, int hMsg, int wParam,"
                    " int lParam);' -Name W -PassThru)::SendMessage(-1,0x0112,0xF170,2)",
                ],
                stderr=subprocess.DEVNULL,
            )

        else:
            exe = shutil.which("xset")

            if not exe:
                return "No display control tool is available."

            subprocess.Popen(
                [exe, "dpms", "force", "off"],
                stderr=subprocess.DEVNULL,
            )

    except OSError as exc:
        return f"Could not sleep the display: {exc}"

    return "Display going to sleep."


def platform_label() -> str:
    return f"{platform.system()} {platform.release()}".strip()