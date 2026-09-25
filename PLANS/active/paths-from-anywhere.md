# Plan: Run Commands on Any File or Folder

**Status:** Draft (idea captured; plan it later)
**Priority:** P1
**Updated:** 2026-09-26

## Goal

You can point any command at any file or folder, in the CLI and in the dashboard, without first moving into that folder.

## The idea (maintainer, 2026-09-26)

"I should be in the same folder to apply the scripts to the folder or file." Make it easy to run a command on any path, in both the command line and the interface.

## What we know today

- Most commands take a path argument, but several default to `.` (current folder). The docs and examples assume you `cd` first.
- Some commands behave badly with `.`. Hardening fixed `images compress` writing to `./_optimized`; others may have similar edge cases.
- The dashboard asks you to type or paste paths. The Download panel's "Browse" button only shows a hint.

## Ideas to plan later

- [ ] Audit every command for path handling: absolute and relative paths, `~`, quotes, spaces, Windows drive letters, and folders versus single files. Add tests for each case.
- [ ] Shared path resolving in `common/` (expand `~`, resolve, validate, give a friendly "not found, did you mean ..." error), used by every command.
- [ ] Dashboard: a real file and folder picker (Textual `DirectoryTree`), a recent-folders list and favourites.
- [ ] CLI: shell completion for paths, and remembering the last folder used per command where it helps.
- [ ] Agent: the agent resolves "my Downloads folder" or "the video I just downloaded" to real paths (see `dashboard-first-ai-agent.md`).
- [ ] Safety: destructive commands show the resolved absolute path in their confirmation.

## Related

- `dashboard-ui-redesign.md` (the picker component), `dashboard-first-ai-agent.md`.
