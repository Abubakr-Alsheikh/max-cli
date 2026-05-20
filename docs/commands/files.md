# File Commands

## organize

Organize files into categories.

```bash
max files organize <directory>
```

## duplicates

Find duplicate files.

```bash
max files duplicates <directory> [--recursive] [--delete]
```

**Options:**
- `-r, --recursive` - Search recursively
- `-d, --delete` - Delete duplicates

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

List available backups.

```bash
max files backups
```

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
