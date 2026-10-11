# Session Handoff: AI agent overhaul, release 1.1.0, and what to build next

**Date:** 2026-10-11 **Project:** `D:\GitHub\Personal\max-cli` **Session:** continued from `2026-10-02-dashboard-pages-done.md` (with 1.0.0 shipped in between)

**Goal (maintainer's words):** "merge the changes, and make a handover to also include them" (the feature ideas at the end of this file).

## Current State

- **Task:** no task open. The AI agent work (phases 1-3b, guides, stop/undo/notices/notes) is merged and released as **1.1.0**.
- **Phase:** between features. The maintainer picks the next one from "Feature Ideas" below or "Open Decisions".

## Repository State

- **Branch:** `main` at `43dbfb3` (Merge #63). Working tree clean; no open PRs.
- **Release:** `v1.1.0` tagged on `f43bd13`; on PyPI (wheel and sdist) and as the GitHub release with the CHANGELOG section as notes. The maintainer's editable install shows `max 1.1.0`.
- **PRs merged this session:** #54 (download tags, track-63 fix, folder picker), #55 (versioning rules, `release_plan.py`, lighter CI gates), #56 (agent phases 1-2), #57 (phase 3a, light local CI), #58 (phase 3b, evals), #59 (activity-log tie order), #60 (action guides), #61 (stop, undo, notices, notes), #62 (release 1.1.0), #63 (no asking for installs and pyproject edits).
- **Stash:** `stash@{0}` (WIP on main from 0.4.0) belongs to the maintainer. Leave it; never `git stash`.

## Plan Status

- Completed this session: `PLANS/completed/agent-phase1-batch-verify-memory.md`, `agent-phase2-plan-ask-context.md`, `agent-phase3-pc-vision-models.md`.
- Still active: `PLANS/active/README.md` lists them. `user-workflows-aliases.md` (saved workflows, P1, not started) matches idea 10 below.
- The feature ideas below are not in `PLANS/` yet. Make a plan with the `max-plans` skill when the maintainer picks one.

## Quality Gates (all green on `main`)

- GitHub CI: all 14 checks passed on every merged PR (3 OSes x Python 3.9-3.12, typecheck, build).
- Local: `python scripts/ci_local.py` (the light check) passes; the release PR ran the whole suite locally (pyproject.toml changed) and passed in 528 s.
- mypy: 27 errors, matching `mypy-baseline.txt`.
- `scripts/agent_eval.py` on `gemini-flash-lite-latest`: 4-5 of 5 scenarios per run (it varies run to run).

## What We Did

- **Downloads:** tags and folders (artist, album, genre, year, playlist track numbers `3/43`, `Artist - Song` splitting, `--sort-into album|artist/album`), one "Whole playlist" switch and an Items box on the Download page, the ID3v1 "track 63" fix, and the Browse "Max downloads" place.
- **AI agent:** whole-folder batches (`select`, preview, auto-queue over 20 files, batch cards), checked outputs, `job_status`, memory (`remember`/`forget`, `max ai memory`, Notes dialog), plans and questions (one `ask` callback), request context, chat summaries, PC tools (`system_info`, `processes`, `open`, `look_at_image`, `stop_process`), opt-in `run_command` (`AGENT_SHELL`), `AI_FAST_MODEL`, per-action guides on all 52 actions, no re-asking after a no, Stop (Ctrl+C / button), whole-request undo (`undo_request`, `max ai undo`), job notices.
- **Tooling:** the light local CI (`ci_local.py` checks only the tests of changed files, 1-3 min; `--quick`/`--full` remain), `scripts/import_all.py` (Python 3.9 import of all modules), the stop hook runs related tests only, `scripts/agent_eval.py`, `scripts/release_plan.py` and the `max-release` skill.

## Decisions Made

- **Merge only when the maintainer says "merge".** Everything else (installs, `pyproject.toml` edits) doesn't need asking: vet it and say what changed (AGENTS.md section 6, memory `decide-installs-and-pyproject`).
- **No Claude attribution** in commits or PRs (memory `no-claude-attribution`).
- **Light local CI only** before a PR; GitHub runs the full matrix and must pass before a merge (memory `local-ci-only-for-package`). The full local run kept getting killed on this machine (low memory).
- **Guides over prompt rules:** how the agent picks an action lives in each `Action.guide` ("Use for / Not for / How"), shown only in `load_group`, so the first prompt stays about 11,000 characters.
- **Undo moves, never deletes:** files a request made go to `~/.max_cli/backups/agent-undo/<time>/`.

## Open Decisions (the maintainer's)

- **FFmpeg overwrite:** a single-file video/audio action replaces an existing output without asking (`-y`). Ask first, or save under a new name?
- **HEIC support:** `pillow-heif` as a base dependency or an optional extra?

## Context to Remember

- The maintainer writes short messages and works on Windows; their music test folder is `C:\Users\ASUS\Videos\Max Downloads\Electronic Gems` (the songs there carry track 63 in ID3v2 from an earlier batch run; renumbering by name or re-downloading the playlist fixes them).
- The machine is often short of memory: long background jobs get killed when the session is idle. Wait on long commands in the foreground (a `timeout 585 bash -c 'until ...'` loop), not in the background.
- The stop hook's pytest now runs only related tests; if it still times out, say it's the time limit, not a failure.
- Tests never touch the real `~/.max_cli` (the `isolated_home` fixture); debug scripts run in a temporary home (memory `isolate-debug-scripts`).

## Feature Ideas (proposed 2026-10-10, not started)

Size: S about a day, M a few days, L a week or more. The maintainer liked them; the top three are marked.

1. **Compress to a target size (S, top 3):** "fit this video in 25 MB" works out the bitrate; the same for PDFs and images ("under 2 MB").
2. **Auto subtitles and transcripts (M, top 3):** `max video subtitles talk.mp4` writes an `.srt` with Whisper (local or API); `--translate ar`; `max audio transcribe` for voice notes and podcasts.
3. **Cut the silences (S):** jump cuts that remove dead air from recordings and lectures.
4. **Watch folders (M, top 3):** rules such as "when a file lands in Downloads: sort it, convert HEIC to JPG, move PDFs to Documents", with undo for every change; the agent can write the rules from plain words.
5. **Photo library tidy-up (M):** near-duplicate photos (perceptual hash), rename by date taken, sort into Year/Month.
6. **Space finder on the dashboard (M):** what fills the disk (old downloads, huge videos, duplicates), cleaned up in one click with undo.
7. **Phone bridge (M):** `max share` serves a folder on the local network with a QR code, plus a drop page for the phone to send files back.
8. **Search by meaning (L):** "the receipt from March", "the beach photo at sunset": the AI describes files once into a local index, then search is instant.
9. **The dashboard in a browser (S-M):** `max serve` runs the Textual dashboard as a web page for the phone or another computer.
10. **Saved workflows (M):** a request that worked becomes a command (`max weekly-cleanup`), optionally on a schedule; see `PLANS/active/user-workflows-aliases.md`.

Agent follow-ups still open: more eval scenarios (refusals, undo, unclear requests, big batches) and `max ai check-model`; per-folder `.max.md` notes; retry after a failed action with changed settings; streaming replies; the `ai` image commands as agent tools.

## Next Steps

1. [ ] Ask the maintainer which feature to build first (they liked all; my top three are 1, 2 and 4) and settle the two open decisions.
2. [ ] Write a plan in `PLANS/active/` for the chosen feature (`max-plans` skill), then build it on a branch; `python scripts/ci_local.py` before the PR.
3. [ ] After the next batch of features, run `python scripts/release_plan.py` and offer a release (`max-release` skill).

## Files to Review on Resume

- `AGENTS.md`: the AI Agent Pattern (agent, guides, stop/undo) and section 6 (what needs asking).
- `src/max_cli/core/agent/agent.py`: the loop, tools, plans, stop and undo recording.
- `src/max_cli/core/catalog/groups/*.py`: each action's `guide`.
- `scripts/ci_local.py`, `scripts/agent_eval.py`, `scripts/release_plan.py`.
- `CHANGELOG.md`: the 1.1.0 notes.
