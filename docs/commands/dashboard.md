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

The sidebar on the left lists ten sections in three groups. It starts as a strip of icons; hover an icon to see its name, or press the `»` button at the top (or `Ctrl+B`) to show the names. Press a section's number to jump to it, click it, or move with the arrow keys and press `Enter`. The dashboard opens on the section you used last.

| Key | Section | What it does |
|-----|---------|--------------|
| | **Do** | |
| `1` | **Home** | Command center: live CPU, memory and disk, your download and action counts, activity over the last 14 days, a breakdown by type, quick launch and recent activity |
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

Badges next to a section show what needs a look: a green `2` on Download means two downloads are running, a yellow `3` on Queue means three tasks are waiting or running, and a red `!1` on History means one action failed since you last opened History.

The dashboard remembers whether you expanded the sidebar. In a window narrower than 100 columns it always shows icons only.

The Queue and History sections read the same task store as `max queue` and `max grab`. See [Queue](queue.md).

## Jobs window

Press `J` to open or close the Jobs window above the footer. It shows the task running now, with its progress, speed and time left, then the tasks waiting their turn, then the last few that finished, failed or were cancelled. It opens by itself when you press "Queue for later" on the Download page or "Add to queue" on a Tools form.

While the dashboard is open it runs queued tasks one after another, including any left from earlier runs. To cancel or retry a task, open the Queue page (`6`).

## Theme

The dashboard uses its own dark theme, `max-cyber`. Press `Ctrl+P` and search "theme" to try another one; the dashboard remembers your choice.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` to `9`, `0` | Jump to a section |
| `Alt+Left` | Back to the previous section |
| `Esc` | Move to the sidebar |
| `?` | Show every shortcut |
| `J` | Show or hide the Jobs window |
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
