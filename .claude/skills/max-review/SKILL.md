---
name: max-review
description: Self-review checklist for Max CLI changes before commit or PR - runs the AGENTS.md rule audit, mypy, tests, and checks the bug classes this codebase has actually shipped (append-mode writes, escaped newlines, lock races, non-atomic JSON, unvalidated AI paths, Python 3.9 syntax). Use before committing, when asked to review a diff, or after a large change.
---

# Max CLI self-review

## 1. Automated gates
Run all four and read the output:
```bash
git diff --stat && git status --short
python .claude/hooks/check_rules.py --audit <changed files or dirs>
ruff check . && ruff format --check <changed files>
mypy <changed files>
pytest
```
`check_rules.py --audit` lists every AGENTS.md violation in the given paths. For each path, compare the output against HEAD. Your change must not add violations, and it should remove any in the lines you touched.

## 2. Bug classes found in this codebase
Check every changed hunk against this list:

| Pattern | Real example | Check |
|---|---|---|
| Open mode ignores `seek` | `open(p, "ba+")` in shred appended instead of overwriting | Overwrites use `"r+b"`, appends use `"a"` |
| Escaped escape | `f"...\\n"` wrote a literal backslash-n into the concat list | Look for `\\n` in f-strings that feed files |
| Status logic order | `cancel` set CANCELLED and then checked for PENDING | Read each state machine transition top to bottom |
| Shared state outside the lock | `DaemonManager` mutated the queue outside `_lock` | Every read-modify-write of shared lists or dicts happens under the lock |
| Callbacks under a lock | `EventEmitter` called subscribers while holding a non-reentrant lock | Copy the subscriber list under the lock, then call outside it |
| Unbounded queues or caches | events pushed into a `Queue` that nothing drained | Everything that grows must have a cap or a consumer |
| Non-atomic state writes | queue, history, cache and transaction log use `write_text` directly | Write to a temp file, then `Path.replace()` |
| AI output trusted | `smart_sort` moved files to AI-supplied `../` paths | Validate types, and `resolve().is_relative_to(base)` |
| Whole-file reads | MD5 dedupe read entire files into memory | Hash in chunks, and group by size first |
| Windows `rename` | `Path.rename` fails when the target exists | Use `Path.replace` |
| Python 3.9 syntax | `list[str] \| None` in a signature crashes at import | Use `Optional[...]` or a `__future__` import |
| Silent failure | `_get_duration` returned 0.0 on every error | Errors surface as a `MaxError` or get logged |
| Duplicated presets | TUI CRF 32 vs CLI CRF 35 | Presets live in one place and get imported |
| Tar extraction | `extractall` with no filter | `extractall(path, filter="data")` |

## 3. Architecture checks
- Core engines import nothing from `interface/`, and nothing from Rich or `logger`.
- No new second store for data that already has one. Queue and history live in `DaemonManager` / `task_queue`. Don't add a third history file.
- Interface files hold no business logic. File discovery, globbing, URL cleaning and downloads all belong in engines.
- New files under 500 lines. If a file grows past that, propose a split instead of growing it further.

## 4. Report format
List the findings as `path:line: severity: problem. fix.`, most severe first. State plainly which gates passed and which failed, and paste the shortest failing line. Don't claim "all good" while a gate is still red.
