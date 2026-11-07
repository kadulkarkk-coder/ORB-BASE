"""Bounded system and archive helpers for WEBSTER G5.41–G5.50."""
from __future__ import annotations
import os, platform, re, socket, sys, time, zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_FILES=2000
MAX_ARCHIVE_ENTRIES=500
MAX_ARCHIVE_BYTES=100*1024*1024
HOST_RE=re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")

def _arg(raw,label):
    if not isinstance(raw,str): raise ValueError(f"Provide {label}.")
    value=raw.strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in {"'",'"'}: value=value[1:-1].strip()
    if not value or len(value)>2048 or any(ord(c)<32 for c in value): raise ValueError(f"Provide {label} as one line of at most 2048 characters.")
    return value

def _pair(raw,left,right):
    value=_arg(raw,f"{left} | {right}")
    if "|" not in value: raise ValueError(f"Use: <{left}> | <{right}>")
    a,b=value.split("|",1)
    return _arg(a,left),_arg(b,right)

def clipboard_copy(raw):
    text=_arg(raw,"text to copy")
    if len(text.encode("utf-8"))>16*1024: raise ValueError("Clipboard text is limited to 16 KiB.")
    try:
        import tkinter
        root=tkinter.Tk(); root.withdraw(); root.clipboard_clear(); root.clipboard_append(text); root.update(); root.destroy()
    except Exception as exc: raise RuntimeError(f"Could not access desktop clipboard: {exc}") from exc
    return f"Copied {len(text)} characters to the clipboard."

def create_zip_archive(raw):
    source_raw,archive_raw=_pair(raw,"source folder","new .zip path")
    candidate=Path(source_raw).expanduser()
    if candidate.is_symlink(): raise ValueError("Symbolic-link source folders are not accepted.")
    source=candidate.resolve(strict=True)
    if not source.is_dir(): raise ValueError("Source must be an existing folder.")
    archive=Path(archive_raw).expanduser()
    if archive.suffix.lower()!=".zip": raise ValueError("Destination must have a .zip extension.")
    if not archive.parent.is_dir(): raise FileNotFoundError("Destination folder must already exist.")
    if archive.exists() or archive.is_symlink(): raise FileExistsError("Archive already exists; it will not be overwritten.")
    files=[]; total=0
    for current,dirs,names in os.walk(source,followlinks=False):
        current_path=Path(current); dirs[:]=sorted(d for d in dirs if not (current_path/d).is_symlink())
        for name in sorted(names):
            item=current_path/name
            if item.is_symlink() or not item.is_file(): continue
            if item.resolve()==archive.resolve(): continue
            files.append(item); total+=item.stat().st_size
            if len(files)>MAX_ARCHIVE_FILES or total>MAX_ARCHIVE_BYTES: raise ValueError("Archive limit exceeded (2,000 files or 100 MiB).")
    if not files: raise ValueError("Source folder contains no regular files.")
    try:
        with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED) as z:
            for item in files: z.write(item,item.relative_to(source).as_posix())
    except Exception:
        archive.unlink(missing_ok=True); raise
    return f"Created {archive.resolve()} with {len(files)} files ({total:,} uncompressed bytes)."

def _safe_members(z):
    infos=z.infolist()
    if len(infos)>MAX_ARCHIVE_ENTRIES: raise ValueError("Archive contains more than 500 entries.")
    total=0
    for info in infos:
        name=info.filename; member=PurePosixPath(name); mode=(info.external_attr>>16)&0o170000
        if not name or "\\" in name or member.is_absolute() or any(p in {"..",""} for p in member.parts) or (member.parts and ":" in member.parts[0]) or mode==0o120000:
            raise ValueError("Archive contains an unsafe path or symbolic link.")
        total+=info.file_size
        if info.file_size<0 or total>MAX_ARCHIVE_BYTES: raise ValueError("Archive expands beyond 100 MiB.")
        if info.compress_size==0 and info.file_size>0: raise ValueError("Archive contains an invalid compression entry.")
        if info.compress_size and info.file_size/info.compress_size>200: raise ValueError("Archive has an excessive compression ratio.")
    return infos,total

def _zip_path(raw):
    p=Path(_arg(raw,"ZIP archive path")).expanduser()
    if p.is_symlink(): raise ValueError("Symbolic-link archives are not accepted.")
    p=p.resolve(strict=True)
    if not p.is_file() or p.suffix.lower()!=".zip": raise ValueError("Provide an existing .zip file.")
    return p

def inspect_zip_archive(raw):
    p=_zip_path(raw)
    with zipfile.ZipFile(p) as z:
        infos,total=_safe_members(z)
        lines=[f"{'DIR ' if i.is_dir() else 'FILE'} {i.filename} ({i.file_size:,} bytes)" for i in infos[:100]]
    extra=f"\n... and {len(infos)-100} more entries" if len(infos)>100 else ""
    return f"Archive: {p.name}\nEntries: {len(infos)}\nUncompressed size: {total:,} bytes\n"+"\n".join(lines)+extra

def extract_zip_archive(raw):
    archive_raw,folder_raw=_pair(raw,"ZIP archive path","existing destination folder")
    archive=_zip_path(archive_raw); candidate=Path(folder_raw).expanduser()
    if candidate.is_symlink(): raise ValueError("Symbolic-link destination folders are not accepted.")
    folder=candidate.resolve(strict=True)
    if not folder.is_dir(): raise ValueError("Destination must be an existing folder.")
    with zipfile.ZipFile(archive) as z:
        infos,_=_safe_members(z); targets=[]
        for info in infos:
            target=(folder/Path(*PurePosixPath(info.filename).parts)).resolve()
            if target!=folder and folder not in target.parents: raise ValueError("Archive entry escapes destination.")
            rel=target.relative_to(folder); cursor=folder
            for part in rel.parts[:-1] if not info.is_dir() else rel.parts:
                cursor=cursor/part
                if cursor.is_symlink(): raise ValueError("Destination path contains a symbolic link.")
            if target.exists() or target.is_symlink(): raise FileExistsError(f"Extraction would overwrite: {target.name}")
            targets.append((info,target))
        written=0
        for info,target in targets:
            if info.is_dir(): target.mkdir(parents=True,exist_ok=False); continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as src,target.open("xb") as dst:
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk: break
                    dst.write(chunk)
            written+=1
    return f"Extracted {written} files into {folder}."

def uptime_status(raw=""):
    if raw.strip(): raise ValueError("uptime_status takes no arguments.")
    import psutil
    boot=psutil.boot_time(); seconds=max(0,int(time.time()-boot)); days,rem=divmod(seconds,86400); hours,rem=divmod(rem,3600)
    return f"System uptime: {days} days, {hours} hours, {rem//60} minutes\nBoot time: {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(boot))}"

def process_summary(raw=""):
    if raw.strip(): raise ValueError("process_summary takes no arguments.")
    import psutil
    count=running=0
    for proc in psutil.process_iter(["status"]):
        count+=1
        try:
            if proc.info.get("status")==psutil.STATUS_RUNNING: running+=1
        except (psutil.NoSuchProcess,psutil.AccessDenied): continue
    return f"Processes observed: {count}\nCurrently running: {running}"

def top_processes(raw=""):
    if raw.strip(): raise ValueError("top_processes takes no arguments.")
    import psutil
    rows=[]
    for proc in psutil.process_iter(["pid","name","memory_info"]):
        try:
            info=proc.info; mem=info.get("memory_info"); rows.append((mem.rss if mem else 0,info.get("pid",0),info.get("name") or "unknown"))
        except (psutil.NoSuchProcess,psutil.AccessDenied): continue
    rows.sort(reverse=True)
    if not rows: return "No process information is available."
    return "Top processes by memory (up to 10):\n"+"\n".join(f"PID {pid}: {name} — {size/(1024*1024):.1f} MiB" for size,pid,name in rows[:10])

def dns_lookup(raw):
    host=_arg(raw,"hostname")
    if not HOST_RE.fullmatch(host) or ".." in host: raise ValueError("Provide a hostname only, without URL, path, or port.")
    try: results=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
    except socket.gaierror as exc: raise ValueError(f"DNS lookup failed for {host}: {exc}") from exc
    return f"DNS results for {host}:\n"+"\n".join(sorted({item[4][0] for item in results})[:20])

def python_environment(raw=""):
    if raw.strip(): raise ValueError("python_environment takes no arguments.")
    return (f"Python: {platform.python_version()}\nImplementation: {platform.python_implementation()}\n"
            f"Executable: {sys.executable}\nPlatform: {platform.platform()}\nPrefix: {sys.prefix}\n"
            f"Virtual environment: {'yes' if sys.prefix!=sys.base_prefix else 'no'}")

def disk_volumes(raw=""):
    if raw.strip(): raise ValueError("disk_volumes takes no arguments.")
    import psutil
    lines=[]; seen=set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen: continue
        seen.add(part.mountpoint)
        try: usage=psutil.disk_usage(part.mountpoint)
        except (PermissionError,OSError): continue
        lines.append(f"{part.mountpoint}: {usage.used/(1024**3):.1f} GiB used / {usage.total/(1024**3):.1f} GiB total ({usage.percent:.0f}% used)")
    return "Mounted volumes:\n"+("\n".join(lines) if lines else "No readable mounted volumes found.")
