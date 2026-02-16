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
