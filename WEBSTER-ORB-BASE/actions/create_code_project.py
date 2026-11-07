"""G5.58: create a small, non-executed Python project scaffold."""
ACTION_ID = "create_code_project"
DESCRIPTION = "Create a starter Python project in a new folder without overwriting or executing files."

def run():
    from pathlib import Path
    import re
    name = ACTION_ARGUMENTS.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name):
        return "Supply a simple project name using letters, numbers, _ or -."
    root = Path.home() / "Documents" / "WEBSTER_Projects" / name
    if root.exists():
        return f"Project already exists; nothing was overwritten: {root}"
    root.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "main.py").write_text('def main():\n    print("Hello from your new project!")\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")
    (root / "README.md").write_text(f"# {name}\n\nPython project scaffold created by WEBSTER. Review files before running.\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n*.py[cod]\n.venv/\n.env\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    return f"Created project scaffold (no code executed): {root}"
