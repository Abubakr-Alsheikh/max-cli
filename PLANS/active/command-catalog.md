# Plan: One Command Catalog

**Status:** Design, waiting for the maintainer's review
**Priority:** P1
**Updated:** 2026-09-26
**Parent:** `dashboard-first-ai-agent.md`, Step 2

## Goal

Max describes each action once, in core. The CLI, the dashboard forms and the AI agent all read that description, so they offer the same options with the same defaults and run the same code.

## What we have today (survey, 2026-09-26)

- **CLI:** 11 visible Typer groups and about 85 visible commands, plus hidden short aliases.
- **Dashboard:** `interface/tui/command_registry.py` lists 39 hand-written entries, and `command_executor.py` maps form fields onto engine methods.
  - The dashboard runs only 3 of them: `grab download`, `images compress` and `video compress`.
  - About 20 of the other entries raise `TypeError` or `AttributeError` if run. The field names don't match the engine arguments (`target` against `input_path`, `prompt` against `user_prompt`), or the method doesn't exist (`ai chat`).
- **The agent** sees `AIEngine.generate_cli_schema`. That is one line per command, with no parameters, types or defaults. It misses config's sub-commands.
- **Logic in the interface layer.** Only about 12 commands are one engine call. Other CLI functions do real work:
  - Images and `pdf compress` loop over folders and name the output files.
  - `files order`, `duplicates` and `smart-sort` write the transaction log (undo).
  - `grab download` retries, cleans URLs and handles playlists.
  - `smart-sort` calls two engines.

  The dashboard copies none of this, so its results differ from the CLI's.
- **Queue:** 10 task types have executors. The CLI queues 3 of them (`video compress`, `video denoise`, `grab download`). The dashboard queues others as `CUSTOM`, which has no executor.

Three smaller bugs turned up in the survey:
- The PDF compress executor defaults quality to 75, while the preset is 80.
- `audio compress` hard-codes `"h"` instead of using the preset.
- `grab download --no-process` is declared but never used.

## Design

### 1. Operations: one callable per action, in core

For each action, a function in `core/operations/<group>.py` does everything the CLI function does today apart from parsing and printing:
- folder expansion and batching;
- output naming;
- the transaction log;
- choosing the engine;
- progress events.

Each function takes plain Python values and returns an `ActionResult`:

```python
@dataclass
class ActionResult:
    ok: bool
    message: str                       # one line for people
    output_files: list[Path]
    details: dict[str, Any]            # counts, sizes, per-file errors
    undo_group: Optional[str] = None   # transaction log group, when undoable
```

Operations never prompt and never print. Whoever calls them (the CLI, the dashboard or the agent) asks for confirmation first, based on the catalog's danger level.

The existing CLI commands become thin: parse, confirm, call the operation, print the result. This is the same change as the "Router Principle" in AGENTS.md, done for real.

### 2. The catalog: one entry per action

`core/catalog/` holds the descriptions. Each group gets its own module (`core/catalog/groups/video.py`), so loading one group doesn't import the others.

```python
@dataclass(frozen=True)
class Param:
    name: str                  # Python name, same as the operation argument
    kind: ParamKind            # text, int, float, bool, choice, file, files, folder, output, url, secret
    help: str
    default: Any = REQUIRED    # a value, or Setting("GRAB_QUALITY") read at run time
    choices: tuple[str, ...] = ()
    cli: tuple[str, ...] = ()  # CLI spellings, e.g. ("--quality", "-q"), for the drift test
    advanced: bool = False     # forms fold it away

@dataclass(frozen=True)
class Action:
    group: str                 # "video"
    name: str                  # "compress", same as the CLI command
    summary: str               # one line: help text, form title, agent tool description
    operation: str             # "max_cli.core.operations.video:compress", imported on first call
    params: tuple[Param, ...]
    danger: Danger             # NONE, WRITES_NEW, MOVES, OVERWRITES, DELETES
    task_type: Optional[TaskType] = None   # set when the action can be queued
    surfaces: frozenset[str] = ALL         # "cli", "dashboard", "agent"
```

- Defaults come from `core/presets.py` or from a `Setting(...)` marker that reads the user's config when the action runs. The dashboard then shows the user's own defaults, which fixes the `grab download` mismatch.
- `danger` drives confirmation everywhere. The agent asks before `MOVES`, `OVERWRITES` and `DELETES` (D4).
- `task_type` replaces the dashboard's guesswork. An action can be queued only if its task type has an executor, and a test checks that.
- `surfaces` keeps interactive commands out of forms and agent tools: `video record`, `stream` and `preview`, `ai chat`, `grab pot-setup` and the config wizards.

### 3. Three views built from the catalog

- **CLI:** the Typer commands stay hand-written for now. A drift test checks each command against its catalog entry: the same parameters, CLI spellings and defaults. Generating Typer commands from the catalog can come later, once every group is ported.
- **Dashboard:** one generic form widget builds a form from an `Action`:
  - required fields first, advanced fields folded away, help text under each field;
  - a file or folder picker for path kinds;
  - an "Add to queue" switch when `task_type` is set.

  `command_registry.py` and `command_executor.py` go away once every group is ported.
- **Agent:** two levels, as the maintainer asked:
  - `list_groups()` returns the enabled groups with one line each. That is all the first prompt holds.
  - `load_group(name)` returns that group's actions as tool definitions: a JSON Schema built from `params`, with the summary and the danger level.
  - `run(action, args)` calls the operation through the same confirmation rules.

  Loaded groups stay loaded for the conversation.

### 4. Feature packs hook in here

Each group entry carries its feature name. Every view filters by the enabled features (`feature-packs.md`), so hiding a feature removes it from the dashboard, the agent's group list and, later, `max --help`.

### 5. Rules that keep it fast and layered

- Catalog modules import no engines and no heavy libraries. `operation` is a string, imported when the action runs. `tests/test_startup_time.py` keeps guarding `import max_cli.main`.
- `core/catalog` and `core/operations` never import `interface`.
- One place per fact: defaults in `presets.py` or settings, and names in the catalog. The TUI preset drift test becomes a catalog drift test.

## Build order

Each step is one PR, with tests first.

1. **Skeleton and a pilot group.**
   - Add `core/catalog` (the types, the lazy group loader and the JSON Schema builder) and `core/operations/video.py`.
   - Port the `video` group: 15 thin commands, and 6 of them are broken in the dashboard today.
   - Add the CLI drift test for `video`, and make the `video` CLI call the operations.
2. **Generic dashboard form.** Build the form widget from the catalog and use it for `video`. Remove the `video` entries from `command_registry.py`.
3. **The heavy groups.** Move the orchestration into operations, one group per PR:
   - `images` (batching and output naming);
   - `pdf` (folder compress, the split modes);
   - `files` (transaction log, `smart-sort`'s two engines);
   - `audio` (the batch loop).
4. **`grab download`.**
   - Split out a core `download` operation: retries, URL cleaning and playlist rules.
   - The CLI keeps its interactive prompt loop, and the dashboard's Download page calls the operation.
5. **Agent tool views:** `list_groups`, `load_group` and JSON Schema. Test that the first prompt holds only the group list, and measure the tokens. This step feeds roadmap Step 4.
6. **Clean up.** Delete `command_registry.py` and `command_executor.py`, and fix the three small bugs above if an earlier step hasn't already.

## Questions for the maintainer

- [ ] **Q1.** Check the Typer commands against the catalog (proposed), or generate them from it? Checking is smaller and keeps each CLI command readable. Generating removes the duplicate but touches every command at once.
- [ ] **Q2.** `video` as the pilot group (proposed)? It's the largest set of thin commands and fixes 6 broken dashboard forms at once.
- [ ] **Q3.** Should the dashboard get a form for every catalog action (a "Tools" page with a group picker), or only on the pages that exist now? Proposed: a "Tools" page, since it replaces the removed Tools panel with generated forms.

## Decisions

- 2026-09-26: Written from a survey of all CLI commands, the TUI registry and the executor. Waiting for review before code.
