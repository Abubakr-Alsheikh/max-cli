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

The sidebar on the left lists eight sections in three groups. It starts as a strip of icons; hover an icon to see its name, or press the `»` button at the top (or `Ctrl+B`) to show the names. Press a section's number to jump to it, click it, or move with the arrow keys and press `Enter`. The dashboard opens on the section you used last.

| Key | Section | What it does |
|-----|---------|--------------|
| | **Do** | |
| `1` | **Home** | Command center: live CPU, memory and disk, your download and action counts, activity over the last 14 days, a breakdown by type, quick launch and recent activity |
| `2` | **Download** | Download form with progress and recent downloads |
| `3` | **Tools** | A form for each command, with all its options |
| `4` | **Files** | File browser with quick actions |
| `5` | **Chat** | AI chat with command suggestions |
| | **Track** | |
| `6` | **Queue** | What's running, waiting and finished, with buttons to pause, cancel and retry |
| `7` | **History** | Finished tasks, with filters |
| | **Setup** | |
| `8` | **Settings** | Your defaults (AI, downloads, images) and upkeep: FFmpeg status, data size, cache and undo cleanup |

Badges next to a section show what needs a look: a green `2` on Download means two downloads are running, a yellow `3` on Queue means three tasks are waiting or running, and a red `!1` on History means one action failed since you last opened History.

The dashboard remembers whether you expanded the sidebar. In a window narrower than 100 columns it always shows icons only.

The Queue and History sections read the same task store as `max queue` and `max grab`. See [Queue](queue.md).

## Download page

Paste a link and press `Enter`, or wait a moment: the page checks the link. While it checks, the Check button reads "Checking" and the preview shows a spinner with the seconds so far. Then it shows its title, channel, length, chapters, views, likes, upload date, the best video and audio streams, the subtitle languages and the site. Each quality button shows the size you'll get, and the Audio (MP3) buttons show the size at each bitrate.

- **Options**, under the preview, holds the other `max grab download` options: an exact resolution, the YouTube player client, and checkboxes for subtitles, metadata and playlist handling.
- **Transfers** has two tabs. Downloads shows one row per download with its progress; "Clear finished" removes the done, failed and cancelled rows. History shows 8 past downloads at a time: type in the filter box to search titles and sites, and use "< Prev" and "Next >" to page. Press `Enter` on a row, or "Download again", to put its link back in the box. "Copy link" copies it.
- **Tools** sums up your downloads (count, done, failed, total size, sites) and shows whether the YouTube fix is installed. If YouTube downloads fail with HTTP 403, press "Install fix": it does what `max grab pot-setup` does, after one confirmation. It needs Deno. The other buttons open the download folder, the Queue page and the settings.

## Queue page

The Queue page (`6`) shows the work the dashboard runs, one task at a time. At the top, four counters show what's running and waiting, and how many tasks finished or failed today. The light in the corner says whether the queue is running.

- **Now running** shows the running task with its progress, speed and time left. Cancel stops it.
- **Up next** lists the waiting tasks in the order they'll run. Each one has Pause (or Resume) and Cancel. "Pause all", "Resume all" and "Clear waiting" act on the whole list; "Clear waiting" asks first and leaves the running task alone.
- **Finished** shows the last 8 tasks. Retry puts a failed or cancelled task back in line, "Run again" repeats a finished one, and "Open folder" opens where its files went. The History page (`7`) has everything else.

## Settings page

The Settings page (`8`) edits the same settings as `max config`, saved in `~/.max_config.env`. It shows only settings that change something:

- **AI:** the API key (hidden; press Show to see it), the base URL, the chat and image models, and Ollama.
- **Downloads:** the folder, format, quality, how many downloads run at once, metadata, and playlist links.
- **Images:** the default quality and how many images run at once.

"Save changes" checks the values first, writes only the settings you changed and applies them at once; "Downloads at once" applies the next time `max` starts. An empty API key removes it from the file. If a `.env` file in the folder you started `max` from sets the same settings, it wins; Maintenance says so.

**Maintenance** shows the Max, Python and system versions, whether FFmpeg is found, and how much `~/.max_cli` holds. Its buttons clear the cache, remove undo backups and undo records older than 30 days, and reset every setting. Each one asks first.

## Jobs window

Press `J` to open or close the Jobs window above the footer. It shows the task running now, with its progress, speed and time left, then the tasks waiting their turn, then the last few that finished, failed or were cancelled. It opens by itself when you press "Queue for later" on the Download page or "Add to queue" on a Tools form.

While the dashboard is open it runs queued tasks one after another, including any left from earlier runs. To cancel or retry a task, open the Queue page (`6`).

## Theme

The dashboard uses its own dark theme, `max-cyber`. Press `Ctrl+P` and search "theme" to try another one; the dashboard remembers your choice.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` to `8` | Jump to a section |
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
