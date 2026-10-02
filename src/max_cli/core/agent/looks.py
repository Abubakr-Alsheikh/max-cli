"""Read-only tools that let the agent look before it acts.

`list_folder` says what a folder holds; `inspect` gives the facts about one
file or folder: a song's tags, a video's length and codecs, an image's
size and camera, a PDF's pages. They reuse the `describe` functions the
dashboard pages show, change nothing and never ask. Paths go through the
same folder limits as actions.
"""

import dataclasses
import json
from pathlib import Path
from typing import Any, Callable

from max_cli.common.exceptions import ResourceNotFoundError
from max_cli.common.file_kinds import AUDIO, IMAGE, PDF, VIDEO, kind_of
from max_cli.common.utils import format_size

MAX_LISTED = 60  # entries list_folder names; the counts cover every file
# A folder is "mostly" one kind at this share, so inspect adds that kind's
# facts (an audio folder's tag summary, an image folder's formats).
MOSTLY = 0.5
MAX_LOOK_CHARS = 6_000


def _plain(value: Any) -> Any:
    """Facts as JSON-safe values: paths and dates become text."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _to_json(data: dict[str, Any]) -> str:
    return json.dumps(_plain(data), ensure_ascii=False)[:MAX_LOOK_CHARS]


def list_folder(path: Path) -> str:
    """A folder's subfolders and files (name, kind, size), the files counted
    by kind, as JSON for the model."""
    if not path.is_dir():
        raise ResourceNotFoundError(f"Not a folder: {path}")
    folders: list[str] = []
    files: list[tuple[str, str, int]] = []
    for entry in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                folders.append(entry.name)
            elif entry.is_file():
                files.append((entry.name, kind_of(entry), entry.stat().st_size))
        except OSError:
            continue  # vanished, or a broken link
    kinds: dict[str, int] = {}
    for _name, kind, _size in files:
        kinds[kind] = kinds.get(kind, 0) + 1
    listed = files[:MAX_LISTED]
    return _to_json(
        {
            "folder": str(path),
            "subfolders": folders[:MAX_LISTED],
            "file_count": len(files),
            "total_size": format_size(sum(size for _n, _k, size in files)),
            "kinds": kinds,
            "files": [
                {"name": name, "kind": kind, "size": format_size(size)}
                for name, kind, size in listed
            ],
            "more_files": max(0, len(files) - len(listed)),
        }
    )


def _describers() -> dict[str, Callable[[Path], Any]]:
    from max_cli.core.operations import audio, images, pdf, video

    return {
        AUDIO: audio.describe,
        IMAGE: images.describe,
        PDF: pdf.describe,
        VIDEO: video.describe,
    }


def inspect(path: Path) -> str:
    """The facts about a file, or a folder and its main kind of file."""
    from max_cli.core.operations import files

    facts = files.describe(path)  # raises for a missing path
    result: dict[str, Any] = {"basics": facts}
    describers = _describers()
    if facts.is_folder:
        main = max(facts.kinds, key=lambda kind: facts.kinds[kind], default="")
        mostly = facts.file_count and facts.kinds.get(main, 0) / facts.file_count
        # Video and PDF facts are per file; audio and images sum up a folder.
        if main in (AUDIO, IMAGE) and mostly >= MOSTLY:
            result[main] = describers[main](path)
    elif kind_of(path) in describers:
        result[kind_of(path)] = describers[kind_of(path)](path)
    return _to_json(result)
