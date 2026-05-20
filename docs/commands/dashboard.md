# TUI Dashboard

Max includes an interactive terminal dashboard for monitoring queues, history, configuration, and system status.

## Installation

The TUI requires the `textual` library as an optional dependency:

```bash
pip install max-cli[tui]
```

## Usage

```bash
# Launch dashboard
max dashboard

# Dev mode with hot-reload for development
max dashboard --dev
```

## Tabs

### Queue

Live view of the download queue with real-time progress updates.

- Shows active, pending, completed, and failed tasks
- Auto-refreshes every 2 seconds
- Displays progress bars for active downloads

### History

Filterable view of recent operations.

- Filter by status (success, failed, pending)
- Filter by type (video, audio, file, grab)
- Shows timestamps and duration

### Config

Editable configuration panel.

- View and modify environment variables
- Toggle settings on/off
- Changes apply immediately

### System

Disk usage and system information.

- Shows `~/.max_cli/` directory size
- Cache usage breakdown
- Platform and Python version info

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Switch between tabs |
| `q` / `Esc` | Quit dashboard |
| `r` | Refresh current panel |
| `Arrow keys` | Navigate lists |
| `Enter` | Select item / toggle setting |

## Troubleshooting

### "textual is not installed"

If you run `max dashboard` without installing the TUI extra, you'll see a message with installation instructions:

```bash
pip install max-cli[tui]
```

### Dashboard not refreshing

Press `r` to manually refresh the current panel. The queue panel auto-refreshes every 2 seconds.

### Dev mode

Use `max dashboard --dev` during development to enable hot-reload. Changes to TUI source files will automatically refresh the dashboard without restarting.
