# TUI Dashboard

Type `max` on its own to open the interactive terminal dashboard. You can download media, run tools, watch the task queue, browse files, edit settings and chat with the AI from one screen.

## Usage

```bash
max              # opens the dashboard
max dashboard    # the same, by name
```

A bare `max` opens the dashboard only when you run it in a terminal. In a script, a pipe or CI it prints the help text, so nothing waits for key presses.

The dashboard comes with the base install. Older instructions say `pip install max-cli[tui]`; that command still works.

## Sections

A sidebar on the left switches between ten sections. Click a section, or move to it with `Tab` and press `Enter`.

| Section | What it does |
|---------|--------------|
| **Home** | Quick actions that open the matching section |
| **Download** | Download form with progress and recent downloads |
| **Queue** | Live task queue; refreshes every 2 seconds |
| **History** | Finished tasks, with filters |
| **Files** | File browser with quick actions |
| **Tools** | A form for each command, with all its options |
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

### "The dashboard needs the 'textual' library, which is missing"

Your install is broken or partly removed. Reinstall Max:

```bash
pip install --upgrade max-cli
```

### `max` prints help instead of opening the dashboard

`max` opens the dashboard only when both its input and its output are a terminal. Run it directly, without `|` or `>`, or run `max dashboard`.

### Dashboard not refreshing

Press `r` to refresh. The visible section also refreshes every 2 seconds.
