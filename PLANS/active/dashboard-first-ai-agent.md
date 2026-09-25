# Plan: Dashboard-First Max with an AI Agent

**Status:** Draft
**Priority:** P1
**Updated:** 2026-09-26

## Goal

People who don't know the command line can use Max. You type `max` and the dashboard opens. You type `max shrink every video in Downloads` and an AI agent plans the work, shows the plan, asks before anything destructive, runs it, and can undo it. The CLI keeps working as it does today for scripts and power users.

## Why

Max started as a personal tool, and its commands are long and hard to remember for anyone else. The dashboard and the AI commands already exist, but they're separate side doors. This plan makes them the front door.

## Decisions to make before building

- [ ] **D1. Routing rule for `max <text>`.** Proposal:
  - If the first word is a known command group (`video`, `pdf`, ...), run the command as today.
  - Otherwise, send the text to the agent.
  - A quoted phrase always goes to the agent: `max "images of my cats to jpg"`.
  - `max ai ...` stays as the explicit route.
- [ ] **D2. When bare `max` opens the dashboard.** Proposal: only when stdin and stdout are an interactive terminal. In scripts, pipes and CI, bare `max` keeps printing help.
- [ ] **D3. Textual as a core dependency.** Proposal: make `textual` (and `psutil`) required, not the `[tui]` extra, so bare `max` never fails with "install textual first". Changing `pyproject.toml` needs approval.
- [ ] **D4. How far the agent may reach.** Proposal:
  - The agent works under the folder you started in, plus folders you name.
  - Deletes, shreds and overwrites always need a yes.
  - It never runs raw shell commands.
- [ ] **D5. Model support.** Proposal: keep the provider configurable (OpenAI-compatible APIs, Ollama). Multi-step tool use needs a capable model, so local models get a simpler single-step mode.

## Tasks

### Step 1: Fix the dashboard first (prerequisite)
- [x] Fix the P0 bugs in `tui-bugfix-and-ux-improvements.md` (2026-09-26):
  - The Config search crash.
  - The dead Files filter.
  - The Downloads card that reads 0 (`grab`/`download` category mismatch).
  - AI chat blocking the UI.
- [x] Every page scrolls (from `dashboard-ui-redesign.md`).
- [ ] Wire or remove the dead System buttons (`interactive-tui-expansion.md`).

### Step 2: One command catalog (single source of truth)
- [ ] Grow `interface/tui/command_registry.py` into one catalog in core that describes each action once. Each entry holds: its engine method, typed parameters with defaults from `core/presets.py`, whether it's destructive, and help text.
- [ ] Generate from the catalog:
  - The dashboard forms (all parameters, see `dashboard-ui-redesign.md`).
  - The agent's tool definitions.
  - A drift test against the Typer commands.
- [ ] Decide whether the Typer commands are generated from the catalog or only checked against it. Checking is the smaller step.

### Step 3: New front door
- [ ] Bare `max` opens the dashboard when a person is at an interactive terminal (D2).
- [ ] `max <text>` routes to the agent (D1). The routing lives in `LazyTyperGroup` (`core/cli/lazy_group.py`), where an unknown command name becomes an agent request.
- [ ] `max --help` and every existing command keep working unchanged.

### Step 4: Agent v2
- [ ] A tool-calling loop in core (`core/agent/`):
  1. The model picks a tool from the catalog.
  2. The engine runs it.
  3. The result goes back to the model, and the loop repeats until done.
- [ ] Plan and confirm: show the steps before running, and ask before destructive ones (D4).
- [ ] Undo: every file change goes through the transaction log, so "undo that" works.
- [ ] Progress through the event system, so the CLI and the Chat panel both show live steps.
- [ ] The dashboard Chat panel and `max <text>` run the same agent.
- [ ] **Load commands on demand (maintainer, 2026-09-26).** Don't put the whole command catalog in the context window.
  - At the start, the agent sees only the parent command groups, each with a one-line description (`video`, `pdf`, `grab`, ...).
  - When a request needs a group, the agent calls a lookup tool (for example `load_group("video")`). That tool returns the group's child commands with their parameters, defaults and usage notes, and only then does the agent call them.
  - The agent sees only the groups for features the user turned on (see `feature-packs.md`).
  - Loaded groups stay available for the rest of the conversation, so they aren't fetched twice.
  - Measure the token cost per request, and add a test that the first prompt holds only the group list.
  - Goal: an efficient agent that uses a small context, picks the right command, and gets the work done.
- [ ] Guardrails: path limits, a step limit, cost and token limits, a dry-run mode.
- [ ] Replace `ai ask`'s "write one command string" approach, keeping `ai ask` as an alias.

### Step 5: Onboarding and packaging
- [ ] A first-run wizard covering the API key (optional), FFmpeg and the download folder, with sensible defaults. It uses the arrow-key select menus from `feature-packs.md`, so you pick which settings to set up instead of typing answers.
- [ ] Friendlier errors: "did you mean ...", plus a next step in every message.
- [ ] Distribution for non-technical users, for example a Windows installer or a single executable. Research needed.

### Tests and docs
- [ ] Routing tests for D1 and D2, including non-interactive terminals.
- [ ] Agent tests with a mocked model: tool selection, confirmation, refusal, undo.
- [ ] README and `docs/`: a new "Getting started" built around `max` and plain-language requests.

## Related drafts

- `dashboard-ui-redesign.md`: page layout, scrolling, a design standard, full command options.
- `cli-dashboard-sync.md`: CLI and dashboard share one live state.
- `paths-from-anywhere.md`: run commands on any file or folder, not only the current one.
- `feature-packs.md`: choose which features and dashboard pages you want.
- `user-workflows-aliases.md`: saved recipes, which the agent could create.

## Decisions

- 2026-09-26: Drafted from the maintainer's idea: "`max` opens the dashboard, `max <text>` goes to an AI agent." Needs D1-D5 answered before Step 3.
