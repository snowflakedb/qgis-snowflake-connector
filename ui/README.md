# Generated UI Code

This directory contains **generated** Python files produced by `pyuic6` from
the `.ui` files in the same directory. **Do not edit the `.py` files manually**;
they will be overwritten the next time `pyuic6` is run.

## Regeneration

After editing any `.ui` file in Qt Designer, regenerate the corresponding
Python module:

```bash
pyuic6 ui/<name>.ui -o ui/<name>.py
```

Or regenerate all at once:

```bash
for f in ui/*.ui; do pyuic6 "$f" -o "${f%.ui}.py"; done
```

## Architecture

| Directory   | Purpose                                   |
|-------------|-------------------------------------------|
| `ui/*.ui`   | Qt Designer source files (XML)            |
| `ui/*.py`   | Auto-generated Python UI code (**do not edit**) |
| `dialogs/`  | Runtime logic that subclasses the generated UI  |

All business logic, event handlers, and SQL calls belong in `dialogs/`, never
in the generated `ui/*.py` files.
