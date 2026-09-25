"""What every operation returns, whoever called it."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ActionResult:
    ok: bool
    message: str
    output_files: list[Path] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    undo_group: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form, for task results and the activity log."""
        return {
            "ok": self.ok,
            "message": self.message,
            "output_files": [str(path) for path in self.output_files],
            "details": self.details,
            "undo_group": self.undo_group,
        }
