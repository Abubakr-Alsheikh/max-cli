#!/usr/bin/env bash
# Launch a hook script with the first Python interpreter that actually runs.
# (On Windows, `python3` is often a Microsoft Store stub that exits non-zero.)
hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$1"
shift
for candidate in python python3 py; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
        exec "$candidate" "$hook_dir/$script" "$@"
    fi
done
echo "max-cli hooks: no working Python interpreter found on PATH" >&2
exit 0
