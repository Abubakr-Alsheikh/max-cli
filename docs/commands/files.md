# File Commands

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
- `-r, --recursive` - Scan subfolders too
- `-d, --delete` - Delete duplicates and keep the first file of each group. Max lists the groups and asks before deleting.
- `-f, --force` - With `--delete`, delete without asking

Max backs up every file it deletes, so `max files undo` can bring them back.

**Examples:**

```bash
max files duplicates ./downloads -r
max files duplicates ./downloads -r --delete
```

## shred

Overwrite a file with random data, then delete it. Max asks before it shreds.

```bash
max files shred TARGET [--passes N] [--force]
```

**Options:**

- `--passes`, `-p` - Number of overwrite passes (default: 3)
- `--force`, `-f` - Skip the confirmation prompt

Max keeps a backup of the file in `~/.max_cli/backups/` so `max files undo` can restore it. Run `max files backup-cleanup` to remove old backups.

## preview

Show a file's size and dates, plus a preview of its content. For text files Max prints the first lines; for images and PDFs it prints dimensions or page count.

```bash
max files preview TARGET [--lines N]
```

**Options:**

- `--lines`, `-n` - Lines to show for text files (default: 20)

## backup

Copy a file into `~/.max_cli/backups/`.

```bash
max files backup TARGET [--label LABEL]
```

**Options:**

- `--label`, `-l` - Label added to the backup name (default: `manual`)

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

Reverse the last group of file operations.

```bash
max files undo
```

This command:

- Reverses the renames, moves and deletes from the last operation
- Restores deleted files from the automatic backups
- Works with `files order`, `files smart-sort`, `files duplicates --delete`, `files shred` and `audio organize`

## history

Show recent file operations.

```bash
max files history [--limit N] [--verbose]
```

**Options:**

- `-n, --limit` - Number of entries to show (default: 10)
- `-v, --verbose` - Show each file in every operation

**Examples:**

```bash
max files history -n 20
max files history -v
```

## Transaction Log

Max records each file operation group as a JSON file in `~/.max_cli/transactions/`. `max files undo` and `max files history` read these records.
