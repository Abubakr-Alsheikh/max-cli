"""What the agent remembers between sessions: short notes it saves with the
`remember` tool ("Music lives in D:/Music", "use 192 kbps for MP3s").

Every session's system prompt lists them, so the next request starts with
them. `max ai memory` shows them, forgets one or clears them all; nothing
else ever leaves this file.
"""

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from max_cli.common.atomic import atomic_write_json
from max_cli.common.exceptions import ValidationError

MEMORY_FILE_NAME = "agent_memory.json"
MAX_NOTES = 50  # the oldest go when a new one would pass this
MAX_NOTE_CHARS = 300
NOTE_ID_BYTES = 3  # six hex characters: short enough to type


@dataclass(frozen=True)
class Note:
    id: str
    text: str
    saved: str  # ISO date and time


def memory_file() -> Path:
    return Path.home() / ".max_cli" / MEMORY_FILE_NAME


class AgentMemory:
    """The notes in `~/.max_cli/agent_memory.json`, oldest first."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or memory_file()

    def notes(self) -> list[Note]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [
            Note(str(item["id"]), str(item["text"]), str(item.get("saved", "")))
            for item in data
            if isinstance(item, dict) and item.get("id") and item.get("text")
        ]

    def remember(self, text: str) -> Note:
        """Save a note. The same text again keeps the one already saved."""
        text = " ".join(text.split())
        if not text:
            raise ValidationError("Nothing to remember: the note is empty.")
        if len(text) > MAX_NOTE_CHARS:
            raise ValidationError(
                f"Keep a note under {MAX_NOTE_CHARS} characters; save the fact, "
                "not the whole conversation."
            )
        notes = self.notes()
        for note in notes:
            if note.text.casefold() == text.casefold():
                return note
        note = Note(
            secrets.token_hex(NOTE_ID_BYTES),
            text,
            datetime.now().isoformat(timespec="seconds"),
        )
        self._save([*notes, note][-MAX_NOTES:])
        return note

    def forget(self, note_id: str) -> Optional[Note]:
        """Delete a note by its id. None when there is no such note."""
        notes = self.notes()
        gone = next((note for note in notes if note.id == note_id.strip()), None)
        if gone is not None:
            self._save([note for note in notes if note is not gone])
        return gone

    def clear(self) -> int:
        """Delete every note; how many there were."""
        count = len(self.notes())
        if count:
            self._save([])
        return count

    def prompt_lines(self) -> str:
        """The notes for the system prompt, one per line with its id."""
        return "\n".join(f"- [{note.id}] {note.text}" for note in self.notes())

    def _save(self, notes: list[Note]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, [asdict(note) for note in notes])
