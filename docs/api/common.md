# Common Utilities

`max_cli.common` holds helpers that every layer can use. Check here before you write a new one.

## Files and state

| Module | Use it for |
|--------|------------|
| `atomic` | `atomic_write_text(path, text)` and `atomic_write_json(path, data)`: write a temporary file, then swap it in, so a crash never leaves half a file. Use them for every state file |
| `file_lock` | `FileLock(path)` (a context manager, or `acquire(timeout)` and `release()`) and `is_locked(path)`. The operating system drops the lock when the process dies |
| `archives` | `safe_extract_tar`: use it for every tar extraction |
| `settings_file` | Read and update `~/.max_config.env` key by key, keeping the rest |
| `file_kinds` | `kind_of(path)`: `video`, `audio`, `image`, `pdf` and so on, from the suffix |

## History and undo

| Module | Use it for |
|--------|------------|
| `transaction_log` | `TransactionLog` records file moves, renames and deletes so `max files undo` can reverse them |
| `activity_log` | `ActivityLog` records every action the CLI, the dashboard and the agent run. The dashboard's Home and History read it |

## Running work

| Module | Use it for |
|--------|------------|
| `concurrent` | `process_batch_parallel(items, processor, max_workers=4, emitter=None)` and `process_batch_sequential` |
| `events` | `EventEmitter` and event models: core code reports progress, and the interface draws it |
| `retry` | `@retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(...))` |
| `cache` | `Cache`, `get_default_cache()` and the `@cached(key_prefix, ttl)` decorator, for slow or paid lookups |
| `ffmpeg_resolver` | Finds FFmpeg on the PATH or in `~/.max_cli/bin/`, or downloads it |

## Errors and output

| Module | Use it for |
|--------|------------|
| `exceptions` | `MaxError` and its subclasses: `ResourceNotFoundError`, `ValidationError`, `ConfigurationError`, `ProcessingError`, `OperationCancelled`, `NetworkError`, `AIError` |
| `logger` | `console`, `log_success` and `log_error` for the interface layer. `log_error` marks the run as failed, so `max` exits 1 |
| `exit_status` | The failed-run flag behind that exit code |
| `logging` | `setup_logging(log_level, log_file)` and `get_logger(name)` |
| `utils` | `format_size`, `natural_sort_key`, `encode_image_to_base64`, `open_in_file_manager` |
