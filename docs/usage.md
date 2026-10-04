# Usage

You can use Max in three ways: type commands, ask the AI agent, or open the dashboard. All three run the same code and offer the same options.

## Commands

Each job is `max <group> <command>`:

```bash
max --help                     # the groups
max video --help               # a group's commands
max video compress --help      # a command's options
```

A few examples:

```bash
max video compress movie.mp4
max video to-audio lecture.mp4 --format wav
max pdf merge a.pdf b.pdf -o both.pdf
max pdf split report.pdf -s 1 -e 5
max images compress ./photos -m 1080
max grab download "https://youtube.com/watch?v=..." -a
max files smart-sort ~/Downloads
```

When you leave out a path, most commands use the current folder.

## Several files at once

Commands that work on one file also take several files, a folder or a pattern. Max runs the files side by side and prints one summary at the end.

```bash
max video compress clip1.mp4 clip2.mp4
max video audio-convert "*.m4a" --format mp3
max audio compress ~/Music --recursive
max pdf ocr scans/ --redo
```

- `--recursive` looks in subfolders too.
- A folder or a pattern skips files whose result already exists, and Max's own results. `--redo` runs them anyway. Files you name always run.
- Max asks once before it overwrites anything.
- One failed file doesn't stop the others, and the command exits with code 1.

Commands that take batches: the `max video` commands except `concat`, `record`, `stream` and `preview`; `max audio compress`, `denoise` and `clear`; `max pdf split`, `lock`, `rip`, `ocr`, `form-flatten` and `optimize`; `max files backup`. `max images` commands work on folders on their own.

## Background jobs

Add `--queue` to a long job. Max adds it to the queue and starts a background worker, which keeps running after you close the terminal.

```bash
max video compress ~/Videos --queue     # one job per video
max grab download URL --queue
max queue status
```

See [Queue](commands/queue.md) for cancel, retry, history and running the queue in your terminal.

## The AI agent

```bash
max "shrink every video in this folder"
max ai ask "merge the PDFs in Downloads into one file"
max "sort my Music folder into Artist/Album folders" --dry-run
max ai chat
```

The agent looks at your files, plans the steps and runs Max's commands. It asks before it moves, overwrites or deletes files, stays inside the folders you work in, and can't run other programs. `--dry-run` shows the plan and changes nothing. See [AI](commands/ai.md).

## The dashboard

Type `max` on its own. Number keys open the pages, `Ctrl+P` finds any action, and `?` lists every key. See [Dashboard](commands/dashboard.md).

## Undo and safety

```bash
max files undo        # reverse the last file change
max files history     # what you can undo
```

Max asks before a command moves, overwrites or deletes files. `--force` skips the question. `max files shred` always asks and can't be undone.

## Exit codes

`max` exits 0 when a command works and 1 when it reports an error, even if it kept going (for example one failed file in a batch). A usage mistake such as a bad option exits 2. Check `$?` (or `%ERRORLEVEL%` on Windows) in scripts.

## Configuration

```bash
max config setup      # main AI and a fallback
max config grab       # download defaults
max config show       # where each setting comes from
max config validate
```

See [Config](commands/config.md) and [Config settings](api/config.md).
