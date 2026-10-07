"""The agent's view of the computer, and the one thing it may start: opening
a file, a folder or a web link with its default app.

- `system_info`: disks, memory, CPU, battery and uptime (psutil).
- `processes`: the programs using the most memory, optionally by name.
- `open_target`: a file or folder (inside the allowed folders) or an http(s)
  link. Programs and scripts are refused: opening one would run it.
- `find_process` and `stop_process`: end a program the user names. System
  processes, Max itself and other users' processes are refused; the agent
  asks before each stop.
- `run_command`: a program with its arguments (never through a shell), in a
  folder, with a time limit. Only when AGENT_SHELL is on, after a yes.

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
# Processes the agent never stops: the system's own, and the desktop.
PROTECTED_PROCESSES = frozenset(
    {
        "system", "system idle process", "registry", "smss.exe", "csrss.exe",
        "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
        "svchost.exe", "fontdrvhost.exe", "dwm.exe", "explorer.exe",
        "memory compression", "secure system", "init", "systemd", "launchd",
        "kernel_task", "loginwindow", "windowserver", "sshd", "dbus-daemon",
        "xorg", "gnome-shell", "kwin_x11", "kwin_wayland",
    }
)  # fmt: skip
STOP_WAIT_SECONDS = 5
COMMAND_TIMEOUT_SECONDS = 60
MAX_COMMAND_OUTPUT = 4_000


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


# --- stopping a program ------------------------------------------------------


def find_process(pid: int = 0, name: str = "") -> Any:
    """The process to stop, by pid or by name (the biggest one of that name).
    Raises ValidationError for one the agent must never stop."""
    import getpass
    import os

    import psutil

    if pid:
        try:
            process = psutil.Process(int(pid))
        except (psutil.NoSuchProcess, ValueError):
            raise ValidationError(f"No running program has pid {pid}.") from None
    else:
        wanted = name.strip().casefold()
        if not wanted:
            raise ValidationError("Name the program or give its pid.")
        matches = [
            found
            for found in psutil.process_iter(["name", "memory_info"])
            if wanted in str(found.info.get("name") or "").casefold()
        ]
        if not matches:
            raise ValidationError(f"No running program is called {name}.")
        process = max(
            matches,
            key=lambda found: getattr(found.info.get("memory_info"), "rss", 0),
        )
    own = {os.getpid(), os.getppid()}
    if process.pid in own or process.pid in (0, 4):
        raise ValidationError("That's Max itself or the system; I won't stop it.")
    try:
        process_name = process.name()
        owner = process.username()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        raise ValidationError(
            "That program belongs to the system or another user; I won't stop it."
        ) from None
    if process_name.casefold() in PROTECTED_PROCESSES:
        raise ValidationError(f"{process_name} is part of the system; I won't stop it.")
    user = getpass.getuser().casefold()
    if owner and owner.split("\\")[-1].casefold() != user:
        raise ValidationError(f"{process_name} belongs to {owner}; I won't stop it.")
    return process


def describe_process(process: Any) -> str:
    """`chrome.exe (pid 1234, 1.20 GB)`."""
    import psutil

    try:
        memory = format_size(process.memory_info().rss)
    except psutil.Error:
        memory = "unknown size"
    return f"{process.name()} (pid {process.pid}, {memory})"


def stop_process(process: Any) -> str:
    """Ask the process to end; force it after STOP_WAIT_SECONDS. What happened."""
    import psutil

    described = describe_process(process)
    try:
        process.terminate()
        process.wait(timeout=STOP_WAIT_SECONDS)
        return f"Stopped {described}."
    except psutil.TimeoutExpired:
        process.kill()
        return f"{described} didn't close, so it was ended."
    except psutil.NoSuchProcess:
        return f"{described} had already ended."
    except psutil.AccessDenied:
        raise ValidationError(f"Windows refused to stop {described}.") from None


# --- running a command --------------------------------------------------------


def command_words(command: str) -> list[str]:
    """`command` split into a program and its arguments. Shell syntax (pipes,
    redirects, &&) is refused: there is no shell to run it."""
    import shlex

    if any(mark in command for mark in ("|", "&&", "||", ">", "<", ";", "`", "$(")):
        raise ValidationError(
            "Shell syntax (pipes, redirects, && or ;) isn't supported: run one "
            "program with its arguments."
        )
    try:
        words = shlex.split(command, posix=sys.platform != "win32")
    except ValueError as e:
        raise ValidationError(f"Can't read that command: {e}") from None
    if not words:
        raise ValidationError("The command is empty.")
    return [word.strip('"') for word in words]


def run_command(words: list[str], folder: Path) -> str:
    """Run a program in `folder` and return what it printed, as JSON."""
    import shutil
    import subprocess

    program = shutil.which(words[0]) or words[0]
    try:
        result = subprocess.run(
            [program, *words[1:]],
            cwd=folder,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        raise ValidationError(
            f"No program called {words[0]}. Windows commands such as dir or copy "
            "live inside cmd, which isn't run; use Max's actions instead."
        ) from None
    except subprocess.TimeoutExpired:
        raise ValidationError(
            f"{words[0]} was still running after {COMMAND_TIMEOUT_SECONDS} "
            "seconds, so it was stopped."
        ) from None
    output = (result.stdout + result.stderr).strip()
    return json.dumps(
        {
            "exit_code": result.returncode,
            "output": output[-MAX_COMMAND_OUTPUT:],
            "cut": len(output) > MAX_COMMAND_OUTPUT,
        },
        ensure_ascii=False,
    )
