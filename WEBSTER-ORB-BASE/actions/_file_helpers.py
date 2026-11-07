"""Bounded, explicit-path file helpers for WEBSTER actions."""
from __future__ import annotations
import ast
import operator
import os
import platform
import subprocess
import webbrowser
from pathlib import Path

MAX_TEXT_BYTES = 64 * 1024
MAX_APPEND_BYTES = 16 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".py", ".log", ".yaml", ".yml", ".toml", ".ini", ".xml"}

def argument(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Please provide {label}.")
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if not value or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError(f"Provide {label} as a single line of at most 2048 characters.")
    return value

def split_path_and_text(raw: str, label: str = "path and text") -> tuple[str, str]:
    raw = argument(raw, label)
    # The first | separates the path from user-provided content.
    if "|" not in raw:
        raise ValueError("Use: <path> | <text>")
    path, content = raw.split("|", 1)
    path = argument(path, "file path")
    if not content.strip():
        raise ValueError("Text content cannot be empty.")
    return path, content.lstrip()

def existing_file(raw: str) -> Path:
    candidate = Path(argument(raw, "file path")).expanduser()
    if candidate.is_symlink():
        raise ValueError("Symbolic links are not accepted for this file action.")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError("The supplied path must be an existing regular file.")
    return path

def existing_folder(raw: str) -> Path:
    candidate = Path(argument(raw, "folder path")).expanduser()
    if candidate.is_symlink():
        raise ValueError("Symbolic links are not accepted for this folder action.")
    path = candidate.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("The supplied path must be an existing folder.")
    return path

def open_file(raw: str) -> str:
    path = existing_file(raw)
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif system == "Linux":
        subprocess.Popen(["xdg-open", str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise RuntimeError(f"Opening files is unsupported on {system}.")
    return f"Opened file: {path.name}"

def create_folder(raw: str) -> str:
    path = Path(argument(raw, "new folder path")).expanduser()
    if path.exists():
        raise FileExistsError("That path already exists; WEBSTER will not replace it.")
    path.mkdir(parents=True, exist_ok=False)
    return f"Created folder: {path.resolve()}"

def create_text_file(raw: str) -> str:
    raw = argument(raw, "file path and text")
    path_text, content = split_path_and_text(raw)
    path = Path(path_text).expanduser()
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Choose a recognised text-file extension (for example .txt or .md).")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_TEXT_BYTES:
        raise ValueError("New file content is limited to 64 KiB.")
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)
    return f"Created new text file: {path.resolve()}"

def append_text_file(raw: str) -> str:
    path_text, content = split_path_and_text(raw)
    path = existing_file(path_text)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Appending is limited to recognised text files.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_APPEND_BYTES:
        raise ValueError("One append operation is limited to 16 KiB.")
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(content)
    return f"Appended {len(encoded)} UTF-8 bytes to {path.name}."

def list_folder(raw: str) -> str:
    folder = existing_folder(raw)
    entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
    if not entries:
        return f"{folder} is empty."
    lines = []
    for item in entries[:100]:
        if item.is_symlink():
            kind = "link"
        elif item.is_dir():
            kind = "folder"
        elif item.is_file():
            kind = "file"
        else:
            kind = "other"
        lines.append(f"[{kind}] {item.name}")
    suffix = f"\n... and {len(entries)-100} more" if len(entries) > 100 else ""
    return f"Contents of {folder} ({len(entries)} entries):\n" + "\n".join(lines) + suffix

def search_files(raw: str) -> str:
    raw = argument(raw, "folder path and filename fragment")
    if "|" not in raw:
        raise ValueError("Use: <folder path> | <filename fragment>")
    folder_raw, fragment = raw.split("|", 1)
    folder = existing_folder(folder_raw)
    fragment = argument(fragment, "filename fragment").casefold()
    found = []
    base_depth = len(folder.parts)
    visited = 0
    for current, dirs, names in os.walk(folder, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        dirs[:] = sorted(d for d in dirs if not (current_path / d).is_symlink())
        if depth >= 4:
            dirs[:] = []
        for name in sorted(names):
            visited += 1
            if visited > 5000:
                break
            candidate = current_path / name
            if fragment in name.casefold() and not candidate.is_symlink() and candidate.is_file():
                found.append(candidate)
                if len(found) >= 50:
                    break
        if visited > 5000 or len(found) >= 50:
            break
    if not found:
        return f"No filenames containing '{fragment}' were found within the bounded search."
    return "Matching files (up to 50; maximum depth 4):\n" + "\n".join(str(p) for p in found)

def file_info(raw: str) -> str:
    path = existing_file(raw)
    stat = path.stat()
    return (f"File: {path.name}\nPath: {path}\nSize: {stat.st_size:,} bytes\n"
            f"Suffix: {path.suffix or '(none)'}\nModified: {__import__('datetime').datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec='seconds')}")

def read_text_file(raw: str) -> str:
    path = existing_file(raw)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("For safety, read_text_file only reads recognised text-file types.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("The file is larger than the 64 KiB read limit.")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The file is not valid UTF-8 text.") from exc
    return f"Contents of {path.name}:\n{content}"

def find_text_in_file(raw: str) -> str:
    raw = argument(raw, "file path and search text")
    if "|" not in raw:
        raise ValueError("Use: <file path> | <text to find>")
    path_raw, query = raw.split("|", 1)
    path = existing_file(path_raw)
    query = argument(query, "search text")
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Search is limited to recognised text-file types.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("The file is larger than the 64 KiB search limit.")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("The file is not valid UTF-8 text.") from exc
    matches = [f"{i}: {line[:300]}" for i, line in enumerate(lines, 1) if query.casefold() in line.casefold()]
    return "\n".join(matches[:50]) if matches else f"No matches for '{query}' in {path.name}."

def calculate(raw: str) -> str:
    expression = argument(raw, "arithmetic expression")
    if len(expression) > 160:
        raise ValueError("Expression is limited to 160 characters.")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent magnitude is limited to 8.")
            value = binary[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            value = unary[type(node.op)](visit(node.operand))
        else:
            raise ValueError("Only basic arithmetic (+, -, *, /, //, %, **, parentheses) is supported.")
        if not isinstance(value, (int, float)) or abs(value) > 10**15:
            raise ValueError("Result is outside the supported numeric range.")
        return value
    try:
        result = visit(ast.parse(expression, mode="eval"))
    except ZeroDivisionError as exc:
        raise ValueError("Division by zero is not allowed.") from exc
    except (SyntaxError, OverflowError) as exc:
        raise ValueError("That is not a valid supported arithmetic expression.") from exc
    return f"{expression} = {result}"


# G5.31–G5.40 bounded file and text utilities
def _split_pair(raw: str, left_label: str, right_label: str) -> tuple[str, str]:
    raw = argument(raw, f"{left_label} and {right_label}")
    if "|" not in raw:
        raise ValueError(f"Use: <{left_label}> | <{right_label}>")
    left, right = raw.split("|", 1)
    return argument(left, left_label), argument(right, right_label)

def copy_file(raw: str) -> str:
    import shutil
    source_raw, destination_raw = _split_pair(raw, "source file", "destination path")
    source = existing_file(source_raw)
    destination = Path(destination_raw).expanduser()
    if not destination.parent.is_dir():
        raise FileNotFoundError("The destination folder does not exist.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destination already exists; copy will not overwrite it.")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Copy is limited to files up to 100 MiB.")
    shutil.copy2(source, destination)
    return f"Copied {source.name} to {destination.resolve()}."

def rename_file(raw: str) -> str:
    source_raw, new_name = _split_pair(raw, "source file", "new filename")
    source = existing_file(source_raw)
    if new_name in {".", ".."} or Path(new_name).name != new_name or any(c in new_name for c in ("/", "\\\\")):
        raise ValueError("Provide only a new filename, not a path.")
    destination = source.with_name(new_name)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("A file with that name already exists; nothing was changed.")
    source.rename(destination)
    return f"Renamed {source.name} to {destination.name}."

def hash_file(raw: str) -> str:
    import hashlib
    path = existing_file(raw)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Hashing is limited to files up to 100 MiB.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"SHA-256 ({path.name}): {digest.hexdigest()}"

def word_count(raw: str) -> str:
    path = existing_file(raw)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Word count is limited to recognised text files.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("The file is larger than the 64 KiB analysis limit.")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The file is not valid UTF-8 text.") from exc
    words = content.split()
    return f"{path.name}: {len(words)} words, {len(content)} characters."

def text_statistics(raw: str) -> str:
    path = existing_file(raw)
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError("Text statistics are limited to recognised text files.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("The file is larger than the 64 KiB analysis limit.")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The file is not valid UTF-8 text.") from exc
    lines = content.splitlines()
    return (f"{path.name}: {len(lines)} lines, {len(content)} characters, "
            f"{len(content.split())} words, {len(content.encode('utf-8'))} UTF-8 bytes.")

def convert_units(raw: str) -> str:
    import re
    expression = argument(raw, "conversion such as '5 km to miles'")
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s+to\s+([a-zA-Z]+)\s*", expression)
    if not match:
        raise ValueError("Use: <number> <unit> to <unit>, for example: 5 km to miles.")
    value = float(match.group(1))
    import math
    if not math.isfinite(value) or abs(value) > 1e15:
        raise ValueError("Conversion value must be finite and no greater than 10^15 in magnitude.")
    source, target = match.group(2).lower(), match.group(3).lower()
    groups = {
        "length": {"mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344, "meter": 1.0, "meters": 1.0, "mile": 1609.344, "miles": 1609.344},
        "mass": {"mg": 0.001, "g": 1.0, "kg": 1000.0, "oz": 28.349523125, "lb": 453.59237, "lbs": 453.59237, "gram": 1.0, "grams": 1.0, "pound": 453.59237, "pounds": 453.59237},
        "time": {"ms": 0.001, "s": 1.0, "sec": 1.0, "min": 60.0, "minutes": 60.0, "h": 3600.0, "hr": 3600.0, "hours": 3600.0, "day": 86400.0, "days": 86400.0},
        "volume": {"ml": 0.001, "l": 1.0, "litre": 1.0, "litres": 1.0, "liter": 1.0, "liters": 1.0, "cup": 0.2365882365, "cups": 0.2365882365},
    }
    for units in groups.values():
        if source in units and target in units:
            result = value * units[source] / units[target]
            return f"{value:g} {source} = {result:.8g} {target}"
    if source in {"c", "celsius"} and target in {"f", "fahrenheit"}:
        result = value * 9 / 5 + 32
    elif source in {"f", "fahrenheit"} and target in {"c", "celsius"}:
        result = (value - 32) * 5 / 9
    else:
        raise ValueError("Those units are unsupported or belong to different categories.")
    return f"{value:g} {source} = {result:.8g} {target}"

def generate_uuid(_raw: str = "") -> str:
    import uuid
    if _raw.strip():
        raise ValueError("This action takes no arguments.")
    return f"UUID: {uuid.uuid4()}"

def compare_text_files(raw: str) -> str:
    import difflib
    first_raw, second_raw = _split_pair(raw, "first text file", "second text file")
    first, second = existing_file(first_raw), existing_file(second_raw)
    for path in (first, second):
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError("Both files must be recognised text files no larger than 64 KiB.")
    try:
        a = first.read_text(encoding="utf-8").splitlines()
        b = second.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Both files must be valid UTF-8 text.") from exc
    if a == b:
        return "The two text files are identical."
    diff = list(difflib.unified_diff(a, b, fromfile=first.name, tofile=second.name, lineterm=""))
    return "\\n".join(diff[:100])[:3500] or "The files differ."

def search_text_in_folder(raw: str) -> str:
    import os
    folder_raw, query = _split_pair(raw, "folder path", "text to find")
    folder = existing_folder(folder_raw)
    query_folded = query.casefold()
    matches, inspected = [], 0
    for current, dirs, names in os.walk(folder, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.parts) - len(folder.parts)
        dirs[:] = sorted(d for d in dirs if not (current_path / d).is_symlink())
        if depth >= 3:
            dirs[:] = []
        for name in sorted(names):
            candidate = current_path / name
            if candidate.is_symlink() or candidate.suffix.lower() not in TEXT_SUFFIXES:
                continue
            inspected += 1
            if inspected > 1000:
                break
            try:
                if candidate.stat().st_size > MAX_TEXT_BYTES:
                    continue
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for line_no, line in enumerate(lines, 1):
                if query_folded in line.casefold():
                    matches.append(f"{candidate}:{line_no}: {line[:180]}")
                    if len(matches) >= 30:
                        break
            if len(matches) >= 30:
                break
        if inspected > 1000 or len(matches) >= 30:
            break
    if not matches:
        return f"No matches found in the bounded text search (checked up to {inspected} files)."
    return "Matches (up to 30; maximum depth 3):\n" + "\n".join(matches)

def validate_json_file(raw: str) -> str:
    import json
    path = existing_file(raw)
    if path.suffix.lower() != ".json":
        raise ValueError("Choose a .json file.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("JSON validation is limited to 64 KiB.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    kind = type(data).__name__
    return f"Valid JSON: {path.name} (top-level type: {kind})."
