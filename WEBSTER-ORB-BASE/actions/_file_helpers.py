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
    path = Path(argument(raw, "file path")).expanduser().resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError("The supplied path must be an existing regular file.")
    return path

def existing_folder(raw: str) -> Path:
    path = Path(argument(raw, "folder path")).expanduser().resolve(strict=True)
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
