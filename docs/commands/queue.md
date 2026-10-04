# Queue Commands

The `max queue` group manages background tasks. You add a task with the `--queue` flag on a heavy command, or the AI agent queues a long job for you. Max then runs it in the background: the command returns at once, and closing the terminal doesn't stop the job.

A task that fails goes back in line and runs again, up to `MAX_RETRIES` more times (2 unless you change it in `max config` or on the dashboard's Settings page). After that it moves to history as failed.

These commands can queue work with `--queue`: `max video` compress,
convert, to-audio, gif, cut, louder, mute, brightness, color, stabilize,
normalize, denoise and audio-convert; `max audio` compress and denoise;
`max pdf ocr`; and `max grab download` (`-Q`). With several files, a folder
or a pattern, each file becomes its own task.

```bash
# Queue two jobs
max video compress movie.mp4 --queue
max video denoise lecture.mp4 --queue

# Both run in the background; see how they're doing
max queue status
```

## How the queue runs

Max stores tasks in `~/.max_cli/tasks/`: pending and running tasks in `queue.json`, finished ones in `history.json`. Every Max process uses this one store: the dashboard, each terminal you run `max` in, and the background worker. `max grab queue` and `max grab history` read it too, so a download you queue with `max grab` shows up here.

Each process locks the store while it reads, changes and saves it. A task you add from one terminal while the dashboard runs a job in another is never lost.

Only one process runs tasks at a time. It runs them one after another, in the order you added them:

- **The dashboard**, while it's open. Press `J` there to watch the tasks, whichever process runs them.
- **The background worker** (`max queue worker`, a hidden command you don't run yourself). `--queue`, the AI agent's queued jobs and `max queue start` start it when no other process runs the queue. It runs apart from your terminal, so closing the terminal doesn't stop it. When the queue stays empty for 30 seconds, it exits. It writes what it did and what failed to `~/.max_cli/tasks/worker.log`.
- **`max queue process`**, which runs pending tasks in your terminal until they're done.

If the process running a task stops in the middle (it crashes, you end it, or the computer shuts down), the task stays marked as running. The next process that runs the queue puts it back to pending with the note "Interrupted: the worker running it stopped. It runs again." and runs it from the start. Run `max queue start` to start that worker yourself.

## status

List every task in the queue with its ID, type, title, status, progress and creation time, then the counts of pending, running and failed tasks. The last line says whether a worker is running the queue. When none is and tasks are waiting, it tells you to run `max queue start`.

```bash
max queue status
```

## start

Start the background worker yourself: for tasks you queued with `--no-process`, tasks left from earlier, or tasks a stopped worker left behind. Max prints the worker's log path. When the dashboard or a worker already runs the queue, it says so and starts nothing.

```bash
max queue start
```

## process

Run pending tasks now, in this terminal. The command returns when no pending task is left (or after `--max` tasks). When the dashboard or the background worker already runs the queue, Max says so and leaves the tasks to it.

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

List finished tasks, newest first. Max keeps the last 200.

```bash
max queue history [--limit N] [--type TYPE]
```

**Options:**

- `--limit`, `-n` - Number of items to show (default: 20)
- `--type`, `-t` - Show only one task type

Task types: `action` (what `--queue` on video, audio and PDF commands and the AI agent add), `download` (`max grab download --queue`). Tasks saved by older versions can have these types: `video_compress`, `video_convert`, `video_to_audio`, `video_denoise`, `audio_denoise`, `audio_convert`, `ai_batch`, `pdf_merge`, `pdf_compress`, `file_organize`, `file_duplicates`, `file_backup`, `custom`. Max prints the valid types when you pass an unknown one.

**Example:**

```bash
max queue history --type download -n 5
```

## cancel

Cancel a task. Copy the ID from `max queue status`. Max removes a pending or paused task at once. It marks a running task as cancelled. The process running it sees that within 2 seconds, even from another terminal, and moves it to history when the job stops. A download that the AI agent or the dashboard queued stops at once and Max deletes its partial files. Other jobs, including `max grab download --queue`, run to the end before they stop.

```bash
max queue cancel TASK_ID
```

## retry

Reset a task to pending so the queue runs it again. This works for failed tasks and for finished tasks in history. Max resets its retry count, so it gets `MAX_RETRIES` retries again. A running task is left alone.

```bash
max queue retry TASK_ID
```

`retry` doesn't start a worker. Run `max queue start` if none is running.

## clear

Remove tasks from the queue. Max asks before it clears anything. Finished tasks in history stay.

```bash
max queue clear [--all | --failed] [--force]
```

**Options:**

- With no flag, Max removes pending tasks
- `--all`, `-a` - Remove every task that isn't running
- `--failed` - Remove failed tasks only
- `--force` - Skip the confirmation prompt
