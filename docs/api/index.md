# API Reference

You can drive Max from Python. The CLI, the dashboard and the AI agent all use the layers below, so a script gets the same checks, defaults and results.

- [Core](core.md): the action catalog, operations, batches, the task queue, the agent and the engines.
- [Common](common.md): shared helpers (atomic writes, file locks, undo log, caching).
- [Config](config.md): every setting and its default.

## Run an action

Every command is an action in the catalog, named `group.command`. `run_action` checks the arguments, fills in defaults and returns an `ActionResult`.

```python
from max_cli.core.catalog import get_action
from max_cli.core.catalog.runner import run_action

result = run_action(get_action("video.compress"), {"target": "movie.mp4", "level": "high"})
print(result.ok, result.message, result.output_files)
```

Arguments are the same strings a dashboard form sends, or JSON values. Paths can be strings.

## Run it on many files

```python
from max_cli.core.catalog import get_action
from max_cli.core.catalog.batch import run_each

result = run_each(get_action("pdf.ocr"), {"target": "scans/"}, recursive=True)
print(result.message)        # one summary for every file
```

## Queue it

```python
from max_cli.core.catalog import get_action
from max_cli.core.catalog.batch import enqueue_each
from max_cli.core.engines.background_worker import start_background_worker

tasks, batch = enqueue_each(get_action("video.compress"), {"target": "videos/"})
print(f"{len(tasks)} jobs, {len(batch.done_already)} done already")
start_background_worker()    # runs them, even after this script ends
```

## Ask the agent

```python
from max_cli.core.agent.agent import Agent

agent = Agent.from_settings(confirm=lambda call: input(f"{call.describe()}? [y/N] ") == "y")
reply = agent.ask("convert the wav files here to mp3")
print(reply.text)
```
