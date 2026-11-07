# WEBSTER Actions (G4.6)

This is a **flat folder**: add one reviewed Python file directly inside
`actions/`. Nested folders are not scanned.

## Action file contract

```python
ACTION_ID = "my_action"
DESCRIPTION = "A short explanation shown before approval."


def run() -> str:
    # Do the action's work here.
    return "Action completed."
```

Rules:

- Use a unique lowercase `ACTION_ID` (letters, numbers and underscores).
- Keep `DESCRIPTION` short and accurate.
- Define a synchronous `run()` function with no required arguments.
- Return a short string (or `None`) for WEBSTER to report.
- Restart WEBSTER after adding or replacing an action so its permission
  allowlist is rebuilt from the folder.
- Ask WEBSTER for `actions` to see valid files.
- Use `run action my_action` to request an action. WEBSTER asks for explicit
  YES/NO confirmation before importing and running it.

## Security boundary

Discovery reads only literal metadata using Python's AST; it does not import
or execute action files. A module is imported only after an explicit action
request and confirmation.

**This is not a Python sandbox.** Once approved, an action runs as the current
user with the same access as WEBSTER. Review every line of an action file and
only put code you trust in this folder. Do not place unreviewed AI-generated
code here. G4.7 Vikaas will use a separate review/approval step before an
action is copied into this folder.
