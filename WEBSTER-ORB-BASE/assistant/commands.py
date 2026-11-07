"""Controlled command system.

Safety model: the assistant never executes free text. Every action is a named
Python handler behind an explicit pattern match, arguments are validated, and
subprocesses are launched with argument lists (never `shell=True`). Anything
with a visible side effect is marked `requires_confirmation` and only runs after
the user explicitly confirms — AI-generated text can never trigger it directly.
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
from system.system_info import format_duration, host_info


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
    ) -> None:
        self._stats = stats_provider or (lambda: None)
        self._engine_name = engine_name or (lambda: "unknown")
        self._memory = memory_provider

    # -----------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------

    def set_memory_provider(self, memory_provider: object | None) -> None:
        """Attach or replace the persistent memory provider."""
        self._memory = memory_provider

    def route(self, text: str) -> CommandResult:
        raw_query = (text or "").strip().rstrip("?!.")
        if not raw_query:
            return NOT_HANDLED

        # Smriti commands are checked before system metrics.
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
            "Anything else is sent to the AI engine."
        )

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