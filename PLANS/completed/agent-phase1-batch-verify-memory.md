# Plan: AI agent, phase 1: batches, checks, jobs and memory

**Status:** Completed
**Priority:** P1
**Updated:** 2026-10-07

## Goal

Ask the agent to work on a whole folder and it does it in one step: it finds
the files (subfolders, names, sizes, ages), shows how many and how big before
it asks, runs them together or queues them when there are many, checks that
every result exists, and tells you what went wrong. It can see your queued
jobs, undo Max's last file change, and remembers what you tell it to (your
music folder, your usual quality) from one session to the next.

Phase 2 (a plan card you approve, `ask_user`, summaries of long chats,
automatic context) and phase 3 (PC tools, an optional shell, vision tools,
model routing, agent evals) follow.

## Tasks

- [x] Batches: `run_action` takes `select` (`recursive`, `redo`, `name`,
      `min_size_mb`, `max_size_mb`, `newer_than_days`, `older_than_days`)
      for the files a folder or pattern gives.
- [x] Preview: the one question a batch asks says how many files, their size
      and how many were done already; a dry run lists the files instead of
      "carry on as if it worked".
- [x] Limits: `MAX_EACH` 500; a batch of a queueable action over
      `AUTO_QUEUE_FILES` goes to the queue when the agent can queue.
- [x] Checks: after each run, every output file must exist and not be empty;
      problems go to the model and the step.
- [x] `job_status` look: running, waiting and recently finished jobs with
      progress, errors and outputs.
- [x] Undo: the prompt points at `files.undo` for "undo that".
- [x] Memory: `core/agent/memory.py`, `remember` and `forget` tools, notes in
      the system prompt, `max ai memory` (list, `--forget`, `--clear`).
- [x] AI page: one card per batch with its progress, not one per file.
- [x] Tests: `tests/test_agent.py`, `tests/test_agent_memory.py`, the AI page.
- [x] Docs: `docs/commands/ai.md`, README, AGENTS.md, CHANGELOG.

## Decisions

- `select` sits on `run_action`, not a new `run_batch` tool: one way to run
  actions keeps the prompt short, and `each` already takes folders.
- Memory is notes the model writes with `remember`, not a profile Max
  guesses: you can read and delete every note (`max ai memory`).
- "Undo" needed no new tool: `files.undo` was already an agent action; the
  prompt now points at it.
- The first prompt grew from about 6,000 to 7,700 characters (the new tools
  and rules); `tests/test_agent.py` allows 8,000.
