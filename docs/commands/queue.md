# Queue Commands

The `max queue` group manages background tasks. You add a task with the `--queue` flag on a heavy command, then process it when you're ready.

These commands can queue work:

| Command | Flag |
|---------|------|
| `max video compress` | `--queue`, `-q` |
| `max video denoise` | `--queue`, `-q` |
| `max grab download` | `--queue`, `-Q` |

```bash
# Queue two jobs
max video compress movie.mp4 --queue
max video denoise lecture.mp4 --queue

# Check the queue, then run everything
max queue status
max queue process
```

Max stores tasks in `~/.max_cli/tasks/`: pending tasks in `queue.json` and finished ones in `history.json`. `max grab queue`, `max grab history` and the dashboard read the same store, so a download you queue with `max grab` shows up here too.

## status

List every task in the queue with its ID, type, status and progress.

```bash
max queue status
```

## process

Run pending tasks now.

```bash
max queue process [--max N]
```

**Options:**

- `--max`, `-n` - Stop after N tasks (default: 0, run all)

## stats

Show task counts by status (pending, running, paused, failed) and by type.

```bash
max queue stats
```

## history

List finished tasks, newest first.

```bash
max queue history [--limit N] [--type TYPE]
```

**Options:**

- `--limit`, `-n` - Number of items to show (default: 20)
- `--type`, `-t` - Show only one task type

Task types: `download`, `video_compress`, `video_convert`, `video_to_audio`, `video_denoise`, `audio_denoise`, `audio_convert`, `ai_batch`, `pdf_merge`, `pdf_compress`, `file_organize`, `file_duplicates`, `file_backup`, `custom`.

**Example:**

```bash
max queue history --type video_compress -n 5
```

## cancel

Cancel a task. Copy the ID from `max queue status`. Max removes a pending or paused task at once. It marks a running task as cancelled and moves it to history when the running job returns.

```bash
max queue cancel TASK_ID
```

## retry

Reset a task to pending so the next `max queue process` runs it again. This works for failed tasks and for finished tasks in history.

```bash
max queue retry TASK_ID
```

## clear

Remove tasks from the queue. Max asks before it clears anything.

```bash
max queue clear [--all | --failed] [--force]
```

**Options:**

- With no flag, Max removes pending tasks
- `--all`, `-a` - Remove every task that isn't running
- `--failed`, `-f` - Remove failed tasks only
- `--force` - Skip the confirmation prompt

Note that `-f` means `--failed` here, not `--force`.
