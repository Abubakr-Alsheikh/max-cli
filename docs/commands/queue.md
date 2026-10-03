# Queue Commands

The `max queue` group manages background tasks. You add a task with the `--queue` flag on a heavy command, or the AI agent queues a long job for you. Max then runs it in the background: the command returns at once, and closing the terminal doesn't stop the job.

A task that fails goes back in line and runs again, up to `MAX_RETRIES` more times (2 unless you change it in `max config` or on the dashboard's Settings page). After that it moves to history as failed.

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

# Both run in the background; see how they're doing
max queue status
```

Max stores tasks in `~/.max_cli/tasks/`: pending tasks in `queue.json` and finished ones in `history.json`. `max grab queue`, `max grab history` and the dashboard read the same store, so a download you queue with `max grab` shows up here too.

One process at a time runs the queue: the dashboard while it's open, or else the background worker that a queued job starts. The worker runs every waiting task, waits 30 seconds for more, then exits; its log is `~/.max_cli/tasks/worker.log`. Press `J` in the dashboard to watch the tasks, whichever process runs them. If a worker stops in the middle of a task (the computer sleeps, you end the process), the next worker runs that task again.

Every process that changes the queue (the dashboard, a terminal, the worker) reads it, changes it and saves it in one locked step, so a task you add from a terminal while the dashboard runs a job is never lost.

## status

List every task in the queue with its ID, type, status and progress.

```bash
max queue status
```

## start

Start the background worker yourself, for tasks you queued with `--no-process`
or left from earlier. It does nothing when a worker already runs.

```bash
max queue start
```

## process

Run pending tasks now, in this terminal. When the dashboard or the background
worker already runs the queue, Max says so and leaves the tasks to it.

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

Cancel a task. Copy the ID from `max queue status`. Max removes a pending or paused task at once. It marks a running task as cancelled; the process running it sees that within 2 seconds, even from another terminal, and moves it to history when the job stops. Downloads stop at once; other jobs finish the file they're on.

```bash
max queue cancel TASK_ID
```

## retry

Reset a task to pending so the queue runs it again. This works for failed tasks and for finished tasks in history. A running task is left alone.

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
- `--failed` - Remove failed tasks only
- `--force` - Skip the confirmation prompt
