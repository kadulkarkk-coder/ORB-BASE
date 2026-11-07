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
    vk_lwin,vk_d,keyup=0x5B,0x44,0x0002
    user32.keybd_event(vk_lwin,0,0,0)
    try:
        user32.keybd_event(vk_d,0,0,0)
        user32.keybd_event(vk_d,0,keyup,0)
    finally:
        user32.keybd_event(vk_lwin,0,keyup,0)
    return "Showing the desktop."
