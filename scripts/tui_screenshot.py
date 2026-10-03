"""Render a dashboard page to an image, to check a design change by eye.

    python scripts/tui_screenshot.py home shots/home.png
    python scripts/tui_screenshot.py download shots/dl.png --size 120x40 --sample

The dashboard runs headless against a throwaway home folder, so your real
~/.max_cli (settings, queue, history) is never read or changed. It writes an
SVG next to the PNG; the PNG needs Chrome or Edge, which draw the SVG.
`--sample` fills the activity log and the queue with made-up entries, so
charts and lists aren't empty. The queue worker stays off, so nothing runs.

See the max-tui-design skill (.claude/skills/max-tui-design/SKILL.md).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SIZE = "140x44"
CELL_WIDTH_PX = 9
CELL_HEIGHT_PX = 20
WINDOW_MARGIN_PX = 60
BROWSER_CANDIDATES = (
    "chrome",
    "msedge",
    "google-chrome",
    "chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
SAMPLE_DAYS = 14


def _use_throwaway_home() -> Path:
    """Point the home folder at a temp dir before max_cli reads it."""
    home = Path(tempfile.mkdtemp(prefix="max-shot-"))
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    return home


def _browser() -> str | None:
    for candidate in BROWSER_CANDIDATES:
        found = shutil.which(candidate) or (
            candidate if Path(candidate).is_file() else None
        )
        if found:
            return found
    return None


def _seed_sample_data() -> None:
    import random
    from datetime import datetime, timedelta

    from max_cli.common.activity_log import ActivityLog
    from max_cli.core.engines import task_manager
    from max_cli.core.engines.task_queue import TaskItem, TaskStatus, TaskType

    rng = random.Random(7)
    log = ActivityLog()
    now = datetime.now()
    # Shaped like real entries: a command group, the action, its arguments,
    # what it made, sizes before and after, how long it took.
    samples = [
        ("video", "compress", "trip.mp4", 812_000_000, 296_000_000),
        ("video", "audio-convert", "lofi mix.m4a", 0, 0),
        ("video", "to-audio", "lecture.mp4", 0, 0),
        ("audio", "compress", "podcast 12.wav", 98_000_000, 31_000_000),
        ("pdf", "compress", "scan 2026.pdf", 24_000_000, 6_100_000),
        ("pdf", "merge", "invoices", 0, 0),
        ("download", "download", "https://youtu.be/sample", 0, 0),
        ("images", "compress", "holiday photos", 61_000_000, 19_000_000),
        ("files", "smart-sort", "Downloads", 0, 0),
    ]
    weights = [5, 4, 3, 3, 2, 1, 6, 2, 1]
    prompts = [
        "convert every .m4a here to mp3",
        "shrink the videos in this folder",
        "which files take the most space?",
    ]
    for day in range(SAMPLE_DAYS):
        for _ in range(rng.randint(0, 9)):
            stamp = (now - timedelta(days=day, minutes=rng.randint(0, 600))).isoformat()
            status = "failed" if rng.random() < 0.06 else "success"
            if rng.random() < 0.15:
                entry = log.add_entry(
                    "ai",
                    "agent",
                    status=status,
                    details={
                        "prompt": rng.choice(prompts),
                        "tokens": rng.randint(3, 14) * 1000,
                    },
                    duration_ms=rng.randint(4, 90) * 1000,
                )
                entry.timestamp = stamp
                continue
            group, action, target, before, after = rng.choices(samples, weights)[0]
            name = Path(target).name
            details = {
                "args": {"target": target},
                "via": "ai" if rng.random() < 0.3 else "",
                "ok": status == "success",
                "message": "Done" if status == "success" else "Unsupported codec",
                "output_files": [f"{Path(name).stem}_out{Path(name).suffix or '.pdf'}"],
                "details": {"input_size": before, "output_size": after}
                if before
                else {},
            }
            if status == "failed":
                details["error"] = "Unsupported codec in the input file"
            entry = log.add_entry(
                group,
                action,
                status=status,
                details=details,
                duration_ms=rng.randint(2, 400) * 1000,
            )
            entry.timestamp = stamp
    log.add_entry(
        "video",
        "compress",
        status="success",
        details={
            "args": {"target": "holiday.mp4"},
            "via": "ai",
            "output_files": ["holiday_compressed.mp4"],
            "details": {"input_size": 1_400_000_000, "output_size": 420_000_000},
        },
        duration_ms=212_000,
    )

    task_manager.TaskManager.start_worker = lambda self: None  # show, don't run
    manager = task_manager.get_task_manager()
    manager.add(
        TaskItem(
            type=TaskType.ACTION,
            status=TaskStatus.RUNNING,
            title="Sample download, running",
            progress=42,
            speed="2.10 MB/s",
            eta="3:12",
        )
    )
    manager.add(TaskItem(type=TaskType.ACTION, title="Sample download, waiting"))
    manager.record(
        TaskItem(
            type=TaskType.ACTION,
            status=TaskStatus.COMPLETED,
            title="Sample download, done",
            payload={"action": "grab.download"},
            output_files=[str(Path.home() / "Max Downloads" / "sample.mp4")],
            result={"details": {"size_bytes": 412_000_000}},
        )
    )
    manager.record(
        TaskItem(
            type=TaskType.ACTION,
            status=TaskStatus.FAILED,
            title="Sample compress, failed",
            payload={"action": "video.compress"},
            error="FFmpeg exited with code 1",
        )
    )


async def _render(page: str, size: tuple[int, int], open_jobs: bool) -> str:
    from max_cli.interface.tui.app import MaxDashboardApp

    app = MaxDashboardApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.navigate(page)
        if open_jobs:
            app.action_toggle_jobs()
        await pilot.pause()
        await pilot.pause()
        return app.export_screenshot()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page", help="home, download, tools, files, queue, ...")
    parser.add_argument("out", type=Path, help="PNG path (an SVG is written beside it)")
    parser.add_argument(
        "--size", default=DEFAULT_SIZE, help="columns x rows, e.g. 120x40"
    )
    parser.add_argument("--sample", action="store_true", help="fill in sample activity")
    parser.add_argument("--jobs", action="store_true", help="open the Jobs window")
    args = parser.parse_args()
    columns, rows = (int(part) for part in args.size.lower().split("x"))

    _use_throwaway_home()
    if args.sample:
        _seed_sample_data()
    svg = asyncio.run(_render(args.page, (columns, rows), args.jobs))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    svg_path = args.out.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    browser = _browser()
    if browser is None:
        print(
            f"Wrote {svg_path}. No Chrome or Edge found for the PNG; open the SVG instead."
        )
        return 0
    window = f"{columns * CELL_WIDTH_PX + WINDOW_MARGIN_PX},{rows * CELL_HEIGHT_PX + WINDOW_MARGIN_PX}"
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            f"--screenshot={args.out.resolve()}",
            f"--window-size={window}",
            svg_path.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    print(f"Wrote {args.out} and {svg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
