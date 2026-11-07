"""Shared, bounded helpers for WEBSTER's first desktop actions."""
from __future__ import annotations
import ctypes
import os
import platform
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

def require_argument(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Please provide {label}.")
    value=value.strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in {"'", '"'}:
        value=value[1:-1].strip()
    if not value:
        raise ValueError(f"Please provide {label}.")
    if len(value)>2048 or any(ord(ch)<32 for ch in value):
        raise ValueError(f"{label.capitalize()} must be a single line of at most 2048 characters.")
    return value

def open_application(name: str) -> str:
    from assistant.commands import _ALIAS_INDEX, _squash, _open_app
    target=_ALIAS_INDEX.get(_squash(name))
    if target is None:
        allowed=", ".join(sorted({item.label for item in _ALIAS_INDEX.values()}))
        raise ValueError(f"'{name}' is not an approved application. Available: {allowed}")
    return _open_app(target)

def open_website(url: str) -> str:
    url=require_argument(url,"a website URL")
    parsed=urlsplit(url)
    if parsed.scheme.lower() not in {"http","https"} or not parsed.hostname:
        raise ValueError("Use a complete http:// or https:// website URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Website URLs containing embedded credentials are not allowed.")
    if any(ch.isspace() for ch in url):
        raise ValueError("The website URL cannot contain spaces.")
    opened=webbrowser.open(url,new=2)
    return f"Sent {url} to your default browser." if opened else "The browser did not confirm that it opened the website."

def open_folder(raw_path: str) -> str:
    raw_path=require_argument(raw_path,"a folder path")
    folder=Path(raw_path).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError(f"'{folder}' is not a folder.")
    system=platform.system()
    if system=="Windows":
        os.startfile(str(folder))
    elif system=="Darwin":
        subprocess.Popen(["open",str(folder)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    elif system=="Linux":
        subprocess.Popen(["xdg-open",str(folder)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        raise RuntimeError(f"Opening folders is not supported on {system}.")
    return f"Opened folder: {folder}"

_SETTINGS_PAGES={
    "system":"ms-settings:about","display":"ms-settings:display","sound":"ms-settings:sound",
    "bluetooth":"ms-settings:bluetooth","network":"ms-settings:network-status",
    "wifi":"ms-settings:network-wifi","apps":"ms-settings:appsfeatures",
    "updates":"ms-settings:windowsupdate","windows update":"ms-settings:windowsupdate",
    "personalization":"ms-settings:personalization","notifications":"ms-settings:notifications",
}
def open_settings(page: str) -> str:
    page=require_argument(page,"a settings page").casefold()
    uri=_SETTINGS_PAGES.get(page)
    if uri is None:
        raise ValueError("Choose one of: "+", ".join(sorted(_SETTINGS_PAGES)))
    if platform.system()!="Windows":
        raise RuntimeError("This settings-page action currently supports Windows only.")
    os.startfile(uri)
    return f"Opened Windows Settings: {page}."

def _windows_user32():
    if platform.system()!="Windows":
        raise RuntimeError("This desktop-control action currently supports Windows only.")
    return ctypes.windll.user32

def _window_title(user32, hwnd) -> str:
    length=user32.GetWindowTextLengthW(hwnd)
    if length<=0: return ""
    buffer=ctypes.create_unicode_buffer(length+1)
    user32.GetWindowTextW(hwnd,buffer,length+1)
    return buffer.value

def switch_window(title_query: str) -> str:
    title_query=require_argument(title_query,"part of a window title").casefold()
    user32=_windows_user32()
    matches=[]
    callback_type=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def visit(hwnd,_lparam):
        if user32.IsWindowVisible(hwnd):
            title=_window_title(user32,hwnd)
            if title and title_query in title.casefold(): matches.append((hwnd,title))
        return True
    callback=callback_type(visit)
    user32.EnumWindows(callback,0)
    if not matches: return f"No visible window title contains '{title_query}'."
    hwnd,title=matches[0]
    user32.ShowWindow(hwnd,9)
    user32.SetForegroundWindow(hwnd)
    return f"Switched to: {title}"

def minimize_active_window() -> str:
    user32=_windows_user32()
    hwnd=user32.GetForegroundWindow()
    if not hwnd: return "There is no active window to minimize."
    user32.ShowWindow(hwnd,6)
    return "Minimized the active window."

def toggle_maximize_active_window() -> str:
    user32=_windows_user32()
    hwnd=user32.GetForegroundWindow()
    if not hwnd: return "There is no active window to maximize or restore."
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd,9)
        return "Restored the active window."
    user32.ShowWindow(hwnd,3)
    return "Maximized the active window."

_CLOSE_PROCESS_NAMES={
    "Google Chrome":{"chrome.exe"},"Brave Browser":{"brave.exe"},
    "Visual Studio Code":{"code.exe"},"Cursor":{"cursor.exe"},
    "Antigravity IDE":{"antigravity.exe"},"Spotify":{"spotify.exe"},
    "Notion":{"notion.exe"},"Obsidian":{"obsidian.exe"},"Claude":{"claude.exe"},
    "Perplexity":{"perplexity.exe"},"Telegram":{"telegram.exe"},
    "WhatsApp":{"whatsapp.exe"},"Todoist":{"todoist.exe"},"Zoom":{"zoom.exe"},
    "VLC":{"vlc.exe"},"Microsoft Excel":{"excel.exe"},"Android Studio":{"studio64.exe"},
}
def close_application(name: str) -> str:
    from assistant.commands import _ALIAS_INDEX,_squash
    name=require_argument(name,"an application name")
    target=_ALIAS_INDEX.get(_squash(name))
    if target is None or target.label not in _CLOSE_PROCESS_NAMES:
        raise ValueError("That application is not on the safe-close list.")
    if platform.system()!="Windows":
        raise RuntimeError("Graceful app closing currently supports Windows only.")
    try: import psutil
    except ImportError as exc: raise RuntimeError("Install psutil to use graceful application closing.") from exc
    pids=set()
    for process in psutil.process_iter(["pid","name"]):
        try:
            if (process.info.get("name") or "").casefold() in _CLOSE_PROCESS_NAMES[target.label]:
                pids.add(int(process.info["pid"]))
        except (psutil.NoSuchProcess,psutil.AccessDenied,KeyError,TypeError,ValueError):
            continue
    if not pids: return f"{target.label} is not running."
    user32=_windows_user32()
    posted=[]
    callback_type=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def visit(hwnd,_lparam):
        if user32.IsWindowVisible(hwnd):
            pid=ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value in pids and user32.PostMessageW(hwnd,0x0010,0,0): posted.append(hwnd)
        return True
    callback=callback_type(visit)
    user32.EnumWindows(callback,0)
    if not posted: return f"{target.label} is running but has no visible window to close."
    return f"Sent a normal close request to {len(posted)} {target.label} window(s). Unsaved-work prompts are left to the application."

def lock_screen() -> str:
    if platform.system()!="Windows":
        raise RuntimeError("Lock screen currently supports Windows only.")
    if not ctypes.windll.user32.LockWorkStation():
        raise RuntimeError("Windows did not accept the lock request.")
    return "Locking the Windows session."

def show_desktop_overview() -> str:
    user32=_windows_user32()
    vk_lwin,vk_tab,keyup=0x5B,0x09,0x0002
    user32.keybd_event(vk_lwin,0,0,0)
    try:
        user32.keybd_event(vk_tab,0,0,0)
        user32.keybd_event(vk_tab,0,keyup,0)
    finally:
        user32.keybd_event(vk_lwin,0,keyup,0)
    return "Opened Windows Task View."


# ---------------------------------------------------------------------------
# G5.11–G5.16: Windows audio and media-key controls
# ---------------------------------------------------------------------------

def _send_windows_media_key(virtual_key: int, label: str) -> str:
    if platform.system() != "Windows":
        raise RuntimeError(f"{label} currently supports Windows only.")
    user32 = ctypes.windll.user32
    KEYUP = 0x0002
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, KEYUP, 0)
    return f"Sent {label} media key."

def volume_up() -> str:
    return _send_windows_media_key(0xAF, "volume up")

def volume_down() -> str:
    return _send_windows_media_key(0xAE, "volume down")

def volume_mute() -> str:
    return _send_windows_media_key(0xAD, "volume mute toggle")

def media_play_pause() -> str:
    return _send_windows_media_key(0xB3, "play/pause")

def media_next() -> str:
    return _send_windows_media_key(0xB0, "next track")

def media_previous() -> str:
    return _send_windows_media_key(0xB1, "previous track")


# ---------------------------------------------------------------------------
# G5.17–G5.19: Read-only system diagnostics
# ---------------------------------------------------------------------------

def system_status() -> str:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Install project requirements to use system_status (psutil).") from exc

    cpu = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()
    root = Path.home().anchor or str(Path.cwd().anchor)
    try:
        disk = psutil.disk_usage(root)
    except (OSError, ValueError):
        disk = psutil.disk_usage(str(Path.cwd().anchor or Path.cwd()))

    gib = 1024 ** 3
    return (
        "System status\n"
        f"CPU usage: {cpu:.1f}%\n"
        f"RAM usage: {memory.percent:.1f}% "
        f"({memory.used / gib:.1f} / {memory.total / gib:.1f} GiB)\n"
        f"Disk usage ({root or 'current drive'}): {disk.percent:.1f}% "
        f"({disk.used / gib:.1f} / {disk.total / gib:.1f} GiB)"
    )

def battery_status() -> str:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Install project requirements to use battery_status (psutil).") from exc

    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery information is available (this device may not have a battery)."
    state = "charging" if battery.power_plugged else "not charging"
    remaining = ""
    if battery.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and battery.secsleft >= 0:
        hours, seconds = divmod(int(battery.secsleft), 3600)
        minutes = seconds // 60
        remaining = f"\nEstimated time remaining: {hours}h {minutes}m"
    return f"Battery: {battery.percent:.0f}% ({state}){remaining}"

def network_status() -> str:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Install project requirements to use network_status (psutil).") from exc

    stats = psutil.net_if_stats()
    addresses = psutil.net_if_addrs()
    active = []
    for name, state in sorted(stats.items()):
        if not state.isup:
            continue
        families = []
        for address in addresses.get(name, []):
            if getattr(address.family, "name", "") == "AF_INET":
                families.append(address.address)
        suffix = f" — IPv4 {', '.join(families)}" if families else ""
        active.append(f"{name}: up{suffix}")
    if not active:
        return "No active network interfaces were reported."
    return "Active network interfaces\n" + "\n".join(active[:12])


# ---------------------------------------------------------------------------
# G5.20: Local date and time
# ---------------------------------------------------------------------------

def current_datetime() -> str:
    from datetime import datetime, timezone
    now = datetime.now().astimezone()
    zone = now.tzname() or "local timezone"
    offset = now.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return (
        f"Date: {now.strftime('%A, %d %B %Y')}\n"
        f"Time: {now.strftime('%I:%M:%S %p')}\n"
        f"Timezone: {zone} (UTC{offset})"
    )
