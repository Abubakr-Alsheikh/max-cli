# TUI Dashboard

`max dashboard` opens an interactive terminal dashboard. You can download media, watch the task queue, browse files, edit settings and chat with the AI from one screen.

## Installation

The dashboard needs the `tui` extra, which installs `textual` and `psutil`:

```bash
pip install max-cli[tui]
```

## Usage

```bash
max dashboard
```

## Sections

A sidebar on the left switches between nine sections. Click a section, or move to it with `Tab` and press `Enter`.

| Section | What it does |
|---------|--------------|
| **Home** | Quick actions that open the matching section |
| **Download** | Download form with progress and recent downloads |
| **Queue** | Live task queue; refreshes every 2 seconds |
| **History** | Finished tasks, with filters |
| **Files** | File browser with quick actions |
| **Analytics** | Live usage and system monitoring |
| **Config** | View and edit your settings |
| **System** | Disk usage of `~/.max_cli/` and system info |
| **Chat** | AI chat with command suggestions |

The Queue and History sections read the same task store as `max queue` and `max grab`. See [Queue](queue.md).

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh the sections |
| `Ctrl+B` | Collapse or expand the sidebar |
| `Tab` / `Shift+Tab` | Move between buttons and fields |
| `Enter` | Press the focused button |

## Troubleshooting

### "The TUI dashboard requires the 'textual' library"

You ran `max dashboard` without the TUI extra. Install it:

```bash
pip install max-cli[tui]
```

### Dashboard not refreshing

Press `r` to refresh. The visible section also refreshes every 2 seconds.
