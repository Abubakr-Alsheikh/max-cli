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

The sidebar on the left lists ten sections in three groups. Press a section's number to jump to it, or click it, or move with the arrow keys and press `Enter`. The dashboard opens on the section you used last.

| Key | Section | What it does |
|-----|---------|--------------|
| | **Do** | |
| `1` | **Home** | Quick actions that open the matching section |
| `2` | **Download** | Download form with progress and recent downloads |
| `3` | **Tools** | A form for each command, with all its options |
| `4` | **Files** | File browser with quick actions |
| `5` | **Chat** | AI chat with command suggestions |
| | **Track** | |
| `6` | **Queue** | Live task queue; refreshes every 2 seconds |
| `7` | **History** | Finished tasks, with filters |
| `8` | **Analytics** | Live usage and system monitoring |
| | **Setup** | |
| `9` | **Config** | View and edit your settings |
| `0` | **System** | Disk usage of `~/.max_cli/` and system info |

Badges next to a section show what needs a look: `●2` on Download means two downloads are running, `3` on Queue means three tasks are waiting or running, and `!1` on History means one action failed since you last opened History.

In a window narrower than 100 columns, the sidebar shows icons only. `Ctrl+B` switches between icons and full labels, and the dashboard remembers your choice.

The Queue and History sections read the same task store as `max queue` and `max grab`. See [Queue](queue.md).

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` to `9`, `0` | Jump to a section |
| `Alt+Left` | Back to the previous section |
| `Esc` | Move to the sidebar |
| `?` | Show every shortcut |
| `Ctrl+P` | Command palette (themes and more) |
| `q` | Quit |
| `r` | Refresh the sections |
| `Ctrl+B` | Collapse or expand the sidebar |
| `Tab` / `Shift+Tab` | Move between buttons and fields |
| `Enter` | Press the focused button |

Number keys and `q` type into a text field when one has focus. Press `Esc` first to leave the field.

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
