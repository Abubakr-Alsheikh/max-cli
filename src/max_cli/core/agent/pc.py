"""The agent's view of the computer, and the one thing it may start: opening
a file, a folder or a web link with its default app.

- `system_info`: disks, memory, CPU, battery and uptime (psutil).
- `processes`: the programs using the most memory, optionally by name.
- `open_target`: a file or folder (inside the allowed folders) or an http(s)
  link. Programs and scripts are refused: opening one would run it, and the
  agent never runs programs.

Reading changes nothing and never asks; opening needs no question either,
as it changes no file.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

from max_cli.common.exceptions import ValidationError
from max_cli.common.utils import format_size

MAX_PROCESSES = 15
SECONDS_PER_HOUR = 3600
# Opening these would run a program or a script.
RUNNABLE_SUFFIXES = frozenset(
    {
        ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js",
        ".jse", ".wsf", ".wsh", ".msi", ".msp", ".scr", ".lnk", ".url", ".jar",
        ".py", ".pyw", ".sh", ".bash", ".zsh", ".command", ".app", ".appimage",
        ".deb", ".rpm", ".reg", ".hta", ".cpl", ".pif", ".gadget", ".application",
    }
)  # fmt: skip
WEB_SCHEMES = ("http://", "https://")


def system_info() -> str:
    """Disks, memory, CPU, battery and uptime, as JSON."""
    import platform

    import psutil

    disks = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue  # an empty card reader, a disconnected drive
        disks.append(
            {
                "drive": partition.mountpoint,
                "free": format_size(usage.free),
                "total": format_size(usage.total),
                "used": f"{usage.percent:.0f}%",
            }
        )
    memory = psutil.virtual_memory()
    info: dict[str, Any] = {
        "system": f"{platform.system()} {platform.release()}",
        "cpu_used": f"{psutil.cpu_percent(interval=0.2):.0f}%",
        "cpu_cores": psutil.cpu_count(logical=True),
        "memory_used": f"{memory.percent:.0f}%",
        "memory_free": format_size(memory.available),
        "memory_total": format_size(memory.total),
        "disks": disks,
        "up_for_hours": round((time.time() - psutil.boot_time()) / SECONDS_PER_HOUR, 1),
    }
    battery = getattr(psutil, "sensors_battery", lambda: None)()
    if battery is not None:
        info["battery"] = f"{battery.percent:.0f}%" + (
            ", charging" if battery.power_plugged else ""
        )
    return json.dumps(info, ensure_ascii=False)


def processes(name: str = "", limit: int = 10) -> str:
    """The programs using the most memory, as JSON; `name` narrows by name."""
    import psutil

    limit = max(1, min(int(limit or 10), MAX_PROCESSES))
    wanted = name.strip().casefold()
    found = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        info = process.info
        process_name = str(info.get("name") or "")
        memory = info.get("memory_info")
        if memory is None or (wanted and wanted not in process_name.casefold()):
            continue
        found.append((memory.rss, info["pid"], process_name))
    found.sort(reverse=True)
    return json.dumps(
        {
            "matches": len(found),
            "processes": [
                {"name": process_name, "pid": pid, "memory": format_size(rss)}
                for rss, pid, process_name in found[:limit]
            ],
        },
        ensure_ascii=False,
    )


def is_web_link(target: str) -> bool:
    return target.strip().lower().startswith(WEB_SCHEMES)


def check_openable(path: Path) -> None:
    """Raise ValidationError for what opening would run, or what isn't there."""
    if not path.exists():
        raise ValidationError(f"Not found: {path}")
    # Suffix only: a macOS .app is a folder that runs when opened.
    if path.suffix.lower() in RUNNABLE_SUFFIXES:
        raise ValidationError(
            f"{path.name} is a program or script; opening it would run it, and "
            "I never run programs. The user can open it themselves."
        )


def open_target(target: str) -> None:
    """Open an http(s) link, a file or a folder with its default app. The
    caller checks the path's folder first (the agent's scope)."""
    import subprocess
    import webbrowser

    if is_web_link(target):
        webbrowser.open(target.strip())
        return
    path = Path(target).expanduser()
    check_openable(path)
    if sys.platform == "win32":
        # os.startfile exists only on Windows, so mypy on other systems can't see it.
        import os

        getattr(os, "startfile")(str(path))  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
