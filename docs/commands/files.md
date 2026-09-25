# File Commands

## organize

Organize files into categories.

```bash
max files organize <directory>
```

## duplicates

Find duplicate files.

```bash
max files duplicates <directory> [--recursive] [--delete] [--force]
```

**Options:**
- `-r, --recursive` - Search recursively
- `-d, --delete` - Delete duplicates, keeping the alphabetically first copy of each group. Asks before deleting.
- `-f, --force` - Delete without asking

## shred

Securely delete files.

```bash
max files shred <file> [--passes N]
```

## backup

Create backup of directory.

```bash
max files backup <directory>
```

## backups

List available backups, or restore one.

```bash
max files backups
max files backups --filter report
max files backups --restore ~/.max_cli/backups/report_manual_20260925_101500.txt
max files backups --restore <backup> -o ./restored
```

With `--restore` alone, the file goes back to the path it was backed up from. The command refuses to overwrite a file that already exists there. In that case, pass `-o DIR` to restore into another folder. Backups made before Max CLI recorded original locations also need `-o DIR`.

## backup-cleanup

Clean up old backups.

```bash
max files backup-cleanup [--keep N]
```

## undo

Reverse the last file operation group. All file operations are recorded in `~/.max_cli/transactions/`.

```bash
max files undo
```

This command:
- Reverses renames, moves, copies, and deletes from the last operation
- Restores files from auto-backups created by destructive commands
- Works with `smart-sort`, `order`, `duplicates`, `shred`, and `backup`

## history

Show recent file operation history.

```bash
max files history
```

**Options:**
- `-v, --verbose` - Show individual file paths in each operation
- `-n, --limit` - Number of entries to show (default: 20)

**Examples:**

```bash
# Show last 10 operations
max files history -n 10

# Show full details with file paths
max files history -v
```

## Transaction Log

All file operations are automatically logged to `~/.max_cli/transactions/transactions.json`. Destructive operations (`shred`, `duplicates --delete`) create auto-backups before execution, enabling safe undo.
