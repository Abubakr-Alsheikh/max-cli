"""Where the agent may work (dashboard-first-ai-agent.md, D4).

The folder Max started in, plus folders you name in your requests: a path
you type (`D:\\Photos`, `~/Music`) or a usual folder by name ("my
Downloads"). Every path argument must sit under one of them.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Union

# Folder names people say ("my downloads") and the folder under home.
KNOWN_FOLDERS = ("Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos")
# A Windows path (C:\..., C:/...), a home path (~/...) or a POSIX path (/...),
# up to the next quote or the end of the line. Quotes can wrap one with spaces.
_QUOTED = re.compile(r"[\"']([^\"']+)[\"']")
# It must start a word, so "and/or" doesn't read as the path "/or".
_BARE = re.compile(r"(?<![\w.~/\\])(?:[A-Za-z]:[\\/]|~[\\/]|/)[^\s\"',;]+")
WILDCARDS = "*?["


def _folder_of(text: str) -> Optional[Path]:
    """The folder a typed path names: the folder itself, or a file's folder.

    Never a drive or filesystem root: "/" alone would open everything.
    """
    path = Path(text.strip()).expanduser()
    if not path.is_absolute():
        return None
    folder = path if path.is_dir() else path.parent
    if not folder.is_dir() or folder == Path(folder.anchor):
        return None
    return folder.resolve()


def folders_named_in(request: str) -> list[Path]:
    """Folders a request names, that exist on this computer."""
    found: list[Path] = []
    candidates = _QUOTED.findall(request) + _BARE.findall(request)
    for candidate in candidates:
        folder = _folder_of(candidate)
        if folder is not None:
            found.append(folder)
    words = {word.casefold() for word in re.findall(r"[A-Za-z]+", request)}
    for name in KNOWN_FOLDERS:
        folder = Path.home() / name
        if name.casefold() in words and folder.is_dir():
            found.append(folder.resolve())
    return found


def _without_pattern(path: Path) -> Path:
    """`D:/music/*.mp3` becomes `D:/music`: check the part before a wildcard."""
    parts = path.parts
    for index, part in enumerate(parts):
        if any(mark in part for mark in WILDCARDS):
            return Path(*parts[:index]) if index else Path(".")
    return path


class PathScope:
    """The folders the agent may read and change."""

    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd.resolve()
        self.roots: list[Path] = [self.cwd]

    def allow(self, folder: Path) -> None:
        """Add a folder Max itself uses, such as the download folder."""
        resolved = folder.expanduser().resolve()
        if resolved not in self.roots:
            self.roots.append(resolved)

    def add_from(self, request: str) -> list[Path]:
        """Add the folders a request names; returns the new ones."""
        added = []
        for folder in folders_named_in(request):
            if folder not in self.roots:
                self.roots.append(folder)
                added.append(folder)
        return added

    def resolve(self, value: Union[str, Path]) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.cwd / path
        return _without_pattern(path).resolve()

    def allows(self, value: Union[str, Path]) -> bool:
        path = self.resolve(value)
        return any(path == root or root in path.parents for root in self.roots)

    def outside(self, values: Iterable[Union[str, Path]]) -> list[str]:
        """The values that point outside every allowed folder."""
        return [str(value) for value in values if not self.allows(value)]
