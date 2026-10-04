# File Commands

Max records every rename, move and delete these commands make, so `max files undo` can reverse them, newest first. `shred` is the exception: it keeps no copy on purpose.

`smart-sort` asks the AI for a folder per file. When the AI can't answer, or skips a file, the file goes to a folder for its kind: Music, Videos, Images, PDFs, Documents or Archives.

In the dashboard, the Files page (`7`) has a form for each command. A form asks before it moves or deletes anything. To skip those questions here and in the CLI, turn off **Ask before moving, overwriting or deleting files** in Settings (`CONFIRM_DESTRUCTIVE=false`): it works like `--force` on every command. `shred` asks either way.

## Several files at once

`backup` takes several files, a folder or a pattern:

```bash
max files backup notes.txt todo.md      # these two
max files backup ./thesis               # every file in the folder
max files backup "*.docx" --recursive   # every Word file here and in subfolders
```

A folder gives every file in it; `--recursive` adds the files in its subfolders. Max leaves out hidden files and folders, and works on up to four files at once. Each run makes a new dated copy, so `backup` never skips a file and has no `--redo`. If a file fails, Max backs up the rest, lists the failures at the end and exits with code 1.

`shred` takes one file at a time on purpose: it can't be undone.

## order

Add a number prefix to every file in a folder (`1_file.txt`, `2_file.txt`, ...). Max skips files that already have a number. It asks before it renames anything.

```bash
max files order FOLDER [--dry-run] [--force] [--start N]
```

**Options:**

- `--dry-run` - Show the new names without renaming
- `--force`, `-f` - Skip the confirmation prompt
- `--start` - First number (default: 1)

## smart-sort

Use AI to sort files into folders by what they contain, not only by extension.

```bash
max files smart-sort [PATH] [--dry-run]
```

**Options:**

- `PATH` - Folder to organize (default: current folder)
- `--dry-run` - Show the moves without moving files

## duplicates

Find files with identical content.

```bash
max files duplicates [FOLDER] [--recursive] [--delete] [--force]
```

**Options:**

- `FOLDER` - Folder to scan (default: current folder)
- `--recursive`, `-r` - Scan subfolders too
- `--delete`, `-d` - Delete duplicates and keep the first file of each group. Max lists the groups and asks before deleting.
- `--force`, `-f` - With `--delete`, delete without asking

Max backs up every file it deletes, so `max files undo` can bring them back.

**Examples:**

```bash
max files duplicates ./downloads -r
max files duplicates ./downloads -r --delete
```

## shred

Overwrite a file with random data, then delete it. Max asks before it shreds. Max keeps no backup, so `max files undo` can't bring the file back.

```bash
max files shred TARGET [--passes N] [--force]
```

**Options:**

- `--passes`, `-p` - Number of overwrite passes (default: 3)
- `--force`, `-f` - Skip the confirmation prompt

## preview

Show a file's size and dates, plus a preview of its content. For text files Max prints the first lines; for images and PDFs it prints dimensions or page count.

```bash
max files preview TARGET [--lines N]
```

**Options:**

- `--lines`, `-n` - Lines to show for text files (default: 20)

## backup

Copy a file into `~/.max_cli/backups/` as `<name>_<label>_<date>_<time>.<ext>`.

```bash
max files backup TARGET... [--label LABEL] [--recursive]
```

`TARGET` can be several files, a folder or a pattern (see [Several files at once](#several-files-at-once)).

**Options:**

- `--label`, `-l` - Label added to the backup name (default: `manual`)
- `--recursive` - With a folder or pattern, look in subfolders too

**Examples:**

```bash
max files backup report.docx -l before-edit
max files backup ./thesis --recursive
```

## backups

List backups, or restore one.

```bash
max files backups
max files backups --filter report
max files backups --restore ~/.max_cli/backups/report_manual_20260925_101500.txt
max files backups --restore <backup> -o ./restored
```

**Options:**

- `--filter`, `-f` - Show only backups whose name contains this text
- `--restore`, `-r` - Backup file to restore
- `-o` - Folder to restore into

With `--restore` alone, the file goes back to the path it was backed up from. The command refuses to overwrite a file that already exists there. In that case, pass `-o DIR` to restore into another folder. Backups made before Max CLI recorded original locations also need `-o DIR`.

## backup-cleanup

Delete backups older than a number of days. Max asks first.

```bash
max files backup-cleanup [--days N] [--force]
```

**Options:**

- `--days`, `-d` - Remove backups older than N days (default: 30)
- `--force`, `-f` - Skip the confirmation prompt

## undo

Reverse the newest group of file operations that isn't undone yet. Run it again to step further back, one command at a time.

```bash
max files undo
```

This command:

- Reverses the renames, moves and deletes from the last operation
- Restores deleted files from the automatic backups
- Removes the folders the operation created (organize's Artist/Album folders, smart-sort's category folders) once they're empty again; a folder you made yourself stays
- Works with `files order`, `files smart-sort`, `files duplicates --delete` and `audio organize`. `files shred` can't be undone.

## history

Show recent file operations.

```bash
max files history [--limit N] [--verbose]
```

**Options:**

- `--limit`, `-n` - Number of entries to show (default: 10)
- `--verbose`, `-v` - Show each file in every operation

**Examples:**

```bash
max files history -n 20
max files history -v
```

## Transaction Log

Max records each file operation group as a JSON file in `~/.max_cli/transactions/`. `max files undo` and `max files history` read these records.
