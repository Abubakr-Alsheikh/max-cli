"""One action over many files: the CLI, the dashboard and the agent share it.

An action whose file param is marked `each` takes one file per run, but a
caller may give several files, a folder or a pattern such as *.m4a.
`expand_each` turns that into the files to run:

- A folder gives its files of the param's kinds (subfolders too with
  `recursive`); a pattern gives the files it matches.
- Files found that way are left out when their result exists already
  (the action's `output_name`), and so are Max's own earlier outputs
  (`a_compressed.mp4` next to `a.mp4`). `redo` keeps them.
- Files named one by one always run: the caller asked for each of them.

`run_each` runs the files side by side and sums them up in one
ActionResult; `enqueue_each` queues one task per file.
"""

import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from max_cli.common.exceptions import ValidationError
from max_cli.common.file_kinds import kind_of
from max_cli.core.catalog import runner
from max_cli.core.catalog.runner import _is_empty, _list_items, coerce_args
from max_cli.core.catalog.spec import Action, Param
from max_cli.core.engines.task_queue import TaskItem
from max_cli.core.operations.result import ActionResult

WILDCARDS = frozenset("*?[")
OUTPUT_PARAM = "output"
# Files run side by side. FFmpeg uses several cores per file already, so
# more than this only makes each one slower.
BATCH_WORKERS = min(4, os.cpu_count() or 1)

OnFile = Callable[[Path, Optional[ActionResult], str], None]


@dataclass
class FileBatch:
    """The files a batch runs, and the ones it leaves out."""

    files: list[Path]
    done_already: list[Path] = field(default_factory=list)  # their result exists
    many: bool = False  # a folder, a pattern or several files: not one file

    @property
    def total(self) -> int:
        return len(self.files) + len(self.done_already)


def is_batch(action: Action, raw_args: Mapping[str, Any]) -> bool:
    """True when the args name more than one plain file: a list, a folder or
    a pattern. One plain file runs exactly as before."""
    param = action.each_param()
    if param is None:
        return False
    value = raw_args.get(param.name)
    items = _items(value)
    if len(items) != 1:
        return len(items) > 1
    path = Path(str(items[0])).expanduser()
    return _is_pattern(path) or path.is_dir()


def expand_each(
    action: Action,
    raw_args: Mapping[str, Any],
    recursive: bool = False,
    redo: bool = False,
) -> FileBatch:
    """The files the args name, as described in the module docstring."""
    param = _each(action)
    items = _items(raw_args.get(param.name))
    if not items:
        raise ValidationError(f"{action.id}: '{param.name}' is required")
    named: list[Path] = []
    found: list[Path] = []
    for item in items:
        path = Path(str(item)).expanduser()
        if path.is_dir():
            found += _folder_files(path, param, recursive)
        elif _is_pattern(path):
            found += _pattern_files(path, recursive)
        else:
            named.append(path)
    found = _unique([path for path in found if path not in named])
    if not named and not found:
        listed = ", ".join(str(item) for item in items)
        raise ValidationError(f"{action.id}: no matching files in {listed}")
    many = len(items) > 1 or bool(found) or len(named) > 1
    if many and not _is_empty(raw_args.get(OUTPUT_PARAM)):
        raise ValidationError(
            f"{action.id}: 'output' names one file. Leave it out to save each "
            "result next to its file."
        )
    done_already: list[Path] = []
    if action.output_name:
        outputs = {output_for(action, path, raw_args) for path in named + found}
        # Max's own earlier results aren't new inputs.
        found = [path for path in found if path not in outputs]
        if not redo:
            done_already = [
                path for path in found if output_for(action, path, raw_args).exists()
            ]
            found = [path for path in found if path not in done_already]
    return FileBatch(_unique(named + found), done_already, many)


def output_for(action: Action, path: Path, raw_args: Mapping[str, Any]) -> Path:
    """Where the action saves its result for `path` by default."""
    param = _each(action)
    raw = {**raw_args, param.name: str(path)}
    raw.pop(OUTPUT_PARAM, None)
    values = coerce_args(action, raw)
    fields = {name: str(value) for name, value in values.items() if value is not None}
    fields.update(stem=path.stem, suffix=path.suffix)
    return path.with_name(action.output_name.format(**fields))


def run_each(
    action: Action,
    raw_args: Mapping[str, Any],
    recursive: bool = False,
    redo: bool = False,
    workers: int = BATCH_WORKERS,
    on_file: Optional[OnFile] = None,
    batch: Optional[FileBatch] = None,
) -> ActionResult:
    """Run the action once per file, side by side; one result for them all.
    One plain file runs exactly as run_action would. `on_file(path, result,
    error)` hears about each file as it ends. Pass `batch` when the caller
    expanded the files already (to show them first)."""
    if batch is None:
        if not is_batch(action, raw_args):
            return runner.run_action(action, one_file(action, raw_args))
        batch = expand_each(action, raw_args, recursive, redo)
    param = _each(action)

    def one(path: Path) -> tuple[Path, Optional[ActionResult], str]:
        try:
            result = runner.run_action(action, {**raw_args, param.name: str(path)})
        except Exception as e:  # noqa: BLE001 - one file's failure goes in the summary
            outcome: tuple[Path, Optional[ActionResult], str] = (path, None, str(e))
        else:
            outcome = (path, result, "" if result.ok else result.message)
        if on_file is not None:
            on_file(*outcome)
        return outcome

    with ThreadPoolExecutor(
        max_workers=max(1, min(workers, len(batch.files) or 1))
    ) as pool:
        outcomes = list(pool.map(one, batch.files))
    return summarize(action, batch, outcomes)


def summarize(
    action: Action,
    batch: FileBatch,
    outcomes: list[tuple[Path, Optional[ActionResult], str]],
) -> ActionResult:
    worked = [(path, result) for path, result, error in outcomes if not error]
    failed = [
        {"file": str(path), "error": error} for path, _r, error in outcomes if error
    ]
    outputs = [out for _path, result in worked if result for out in result.output_files]
    parts = [f"{len(worked)} of {batch.total} files done"]
    if batch.done_already:
        parts.append(f"{len(batch.done_already)} had their result already")
    if failed:
        parts.append(f"{len(failed)} failed")
    if not batch.files:
        message = f"Nothing to do: all {batch.total} files have their result already."
    else:
        message = f"{action.group} {action.name}: " + ", ".join(parts) + "."
    return ActionResult(
        not failed,
        message,
        outputs,
        {
            "done": [str(path) for path, _result in worked],
            "done_already": [str(path) for path in batch.done_already],
            "failed": failed,
        },
    )


def enqueue_each(
    action: Action,
    raw_args: Mapping[str, Any],
    recursive: bool = False,
    redo: bool = False,
) -> tuple[list[TaskItem], FileBatch]:
    """Queue one task per file, so each shows and can be cancelled alone."""
    if not is_batch(action, raw_args):
        single = one_file(action, raw_args)
        task = runner.enqueue_action(action, single)
        return [task], FileBatch([Path(str(single[_each(action).name]))])
    batch = expand_each(action, raw_args, recursive, redo)
    param = _each(action)
    tasks = [
        runner.enqueue_action(action, {**raw_args, param.name: str(path)})
        for path in batch.files
    ]
    return tasks, batch


def one_file(action: Action, raw_args: Mapping[str, Any]) -> dict[str, Any]:
    """The args with the file param as one path, not a one-item list."""
    param = _each(action)
    items = _items(raw_args.get(param.name))
    return {**raw_args, param.name: items[0] if items else None}


def _each(action: Action) -> Param:
    param = action.each_param()
    if param is None:
        raise ValidationError(f"{action.id} takes no file, so it can't run on several")
    return param


def _items(value: Any) -> list[Any]:
    if _is_empty(value):
        return []
    return _list_items(value)


def _is_pattern(path: Path) -> bool:
    return bool(WILDCARDS & set(path.name))


def _folder_files(folder: Path, param: Param, recursive: bool) -> list[Path]:
    entries = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        entry
        for entry in entries
        if entry.is_file()
        and not _hidden(entry, folder)
        and (not param.kinds or kind_of(entry) in param.kinds)
    )


def _pattern_files(pattern: Path, recursive: bool) -> list[Path]:
    folder = pattern.parent
    matches = folder.rglob(pattern.name) if recursive else folder.glob(pattern.name)
    return sorted(
        entry for entry in matches if entry.is_file() and not _hidden(entry, folder)
    )


def _hidden(entry: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in entry.relative_to(root).parts)


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    kept = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            kept.append(path)
    return kept
