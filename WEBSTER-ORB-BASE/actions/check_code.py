"""G5.59: syntax-check a Python source file without executing it."""
ACTION_ID = "check_code"
DESCRIPTION = "Check a Python file's syntax with ast.parse; does not import or execute the file."

def run():
    import ast
    from pathlib import Path
    path = Path(ACTION_ARGUMENTS.strip().strip('"')).expanduser()
    if not path.is_file() or path.suffix.lower() != ".py":
        return "Supply the full path to an existing .py file."
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        return f"Syntax OK: {path}\nThe file was parsed only; it was not executed."
    except SyntaxError as exc:
        return f"Syntax error at line {exc.lineno}, column {exc.offset}: {exc.msg}"
    except Exception as exc:
        return f"Could not check file: {exc}"
