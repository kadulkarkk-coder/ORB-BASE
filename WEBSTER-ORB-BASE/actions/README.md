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


## G5.1–G5.10 desktop actions

Use this command format:
- \`run action open_app chrome\`
- \`run action close_app spotify\`
- \`run action switch_window chrome\`
- \`run action minimize_window\`
- \`run action maximize_window\`
- \`run action open_website https://example.com\`
- \`run action open_folder "C:\Users\Student\Documents"\`
- \`run action open_settings display\`
- \`run action lock_screen\`
- \`run action desktop_overview\`

Arguments are passed as a single-line ACTION_ARGUMENTS string only after
explicit confirmation. Quote paths containing spaces. The action manager still
verifies the approved source hash before execution.

Platform notes:
- App launching reuses WEBSTER's existing allowlisted application catalogue.
- Window switching, minimize/maximize, graceful app close, lock screen and
  Task View overview currently target Windows.
- close_app sends normal window-close requests; it never force-kills a process.
- open_settings accepts only a fixed list of Windows Settings pages.
- open_website accepts only HTTP(S) URLs and rejects embedded credentials.
- open_folder only opens an existing directory.


## G5.11–G5.20 audio and system actions

- \`run action volume_up\`
- \`run action volume_down\`
- \`run action volume_mute\`
- \`run action media_play_pause\`
- \`run action media_next\`
- \`run action media_previous\`
- \`run action system_status\`
- \`run action battery_status\`
- \`run action network_status\`
- \`run action current_datetime\`

The volume and media-key actions currently use standard Windows media keys.
The three system diagnostics are read-only and use the project's existing
\`psutil\` dependency. Battery information may be unavailable on desktops or
hardware that does not expose battery telemetry. Network status lists active
interfaces and local IPv4 addresses only; it does not scan the network.


## G5.21–G5.30 utility and file actions

- `run action calculate 12 * (4 + 3)`
- `run action open_file "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action create_folder "C:\\Users\\Student\\Documents\\WEBSTER"`
- `run action create_text_file "C:\\Users\\Student\\Documents\\note.txt | Hello from WEBSTER"`
- `run action append_text_file "C:\\Users\\Student\\Documents\\note.txt | More text"`
- `run action list_folder "C:\\Users\\Student\\Documents"`
- `run action search_files "C:\\Users\\Student\\Documents | notes"`
- `run action file_info "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action read_text_file "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action find_text_in_file "C:\\Users\\Student\\Documents\\notes.txt | keyword"`

File actions require an explicit path and remain behind WEBSTER's normal
confirmation prompt. Creation never overwrites an existing file or folder.
Text creation is capped at 64 KiB; each append is capped at 16 KiB. Reading
and phrase-search are limited to recognised UTF-8 text formats and 64 KiB.
Folder listing is capped at 100 immediate entries. Filename search is bounded
to depth 4, 5,000 inspected filenames and 50 matches; it does not read file
contents. The calculator accepts basic arithmetic only, not Python code.


## G5.31–G5.40 file and text utilities

- `run action copy_file "C:\\Users\\Student\\Documents\\a.txt | C:\\Users\\Student\\Documents\\a-copy.txt"`
- `run action rename_file "C:\\Users\\Student\\Documents\\draft.txt | final.txt"`
- `run action hash_file "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action word_count "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action text_statistics "C:\\Users\\Student\\Documents\\notes.txt"`
- `run action convert_units 5 km to miles`
- `run action generate_uuid`
- `run action compare_text_files "C:\\Users\\Student\\Documents\\old.txt | C:\\Users\\Student\\Documents\\new.txt"`
- `run action search_text_in_folder "C:\\Users\\Student\\Documents | WEBSTER"`
- `run action validate_json_file "C:\\Users\\Student\\Documents\\settings.json"`

Copy and rename never overwrite an existing destination. Copy and SHA-256 are
limited to 100 MiB. Text analysis, comparison and JSON validation are limited
to recognised UTF-8 text files up to 64 KiB. Folder text search is bounded to
depth 3, 1,000 candidate files and 30 matches. JSON validation does not modify
the file. Unit conversion supports a fixed set of common length, mass, time,
volume and temperature units. All actions remain behind explicit confirmation.
