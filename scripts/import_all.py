"""Import every max_cli module, so an old Python meets every annotation and
piece of syntax it can't handle at import time.

    .ci-venvs/py3.9/Scripts/python scripts/import_all.py

scripts/ci_local.py runs it on Python 3.9 in its default check. Heavy
libraries load lazily inside functions, so this takes a few seconds. It goes
by file rather than pkgutil, which skips folders without an __init__.py.
"""

import importlib
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src"


def module_names(source: Path = SOURCE) -> list[str]:
    names = []
    for path in sorted((source / "max_cli").rglob("*.py")):
        parts = path.relative_to(source).with_suffix("").parts
        if parts[-1] == "__main__":
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
        names.append(".".join(parts))
    return names


def main() -> int:
    sys.path.insert(0, str(SOURCE))
    names = module_names()
    for name in names:
        importlib.import_module(name)
    print(f"Imported {len(names)} modules on Python {sys.version.split()[0]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
