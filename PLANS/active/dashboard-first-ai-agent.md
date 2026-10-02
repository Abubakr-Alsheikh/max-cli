# Plan: Dashboard-First Max with an AI Agent

**Status:** In Progress
**Priority:** P1
**Updated:** 2026-09-26

## Goal

People who don't know the command line can use Max. You type `max` and the dashboard opens. You type `max shrink every video in Downloads` and an AI agent plans the work, shows the plan, asks before anything destructive, runs it, and can undo it. The CLI keeps working as it does today for scripts and power users.

## Why

Max started as a personal tool, and its commands are long and hard to remember for anyone else. The dashboard and the AI commands already exist, but they're separate side doors. This plan makes them the front door.

## Decisions (answered 2026-09-26)

- [x] **D1. Routing rule for `max <text>`.**
  - The main form is a quoted request: `max "shrink every video in Downloads"`. The shell passes it as one argument that contains spaces, and the agent gets it.
  - If the first word is a known command group (`video`, `pdf`, ...), the command runs as today.
  - Any other first word also goes to the agent.
  - `max ai ...` stays as the explicit route.
- [x] **D2. When bare `max` opens the dashboard.** Only when stdin and stdout are an interactive terminal. In scripts, pipes and CI, bare `max` keeps printing help. (Taken as the default; the maintainer didn't object.)
- [x] **D3. Textual as a core dependency.** Approved: `textual` and `psutil` move from the `[tui]` extra to the required dependencies. Make the `pyproject.toml` change in Step 3.
- [x] **D4. How far the agent may reach.**
  - The agent works under the folder you started in, plus folders you name in the request.
  - Deletes, shreds and overwrites always need a yes.
  - It never runs raw shell commands.
- [x] **D5. Model support.** The provider stays configurable: any OpenAI-compatible API, plus Ollama. Capable models get multi-step tool use. Small local models get a simpler one-step mode.

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
The design and build order live in `command-catalog.md`.
- [ ] Grow `interface/tui/command_registry.py` into one catalog in core that describes each action once. Each entry holds: its engine method, typed parameters with defaults from `core/presets.py`, whether it's destructive, and help text.
- [ ] Generate from the catalog:
  - The dashboard forms (all parameters, see `dashboard-ui-redesign.md`).
  - The agent's tool definitions.
  - A drift test against the Typer commands.
- [ ] Decide whether the Typer commands are generated from the catalog or only checked against it. Checking is the smaller step.

### Step 3: New front door
- [x] Bare `max` opens the dashboard when a person is at an interactive terminal (D2). `LazyTyperGroup.parse_args` does it; `textual` and `psutil` are required dependencies now, with `textual>=6.0.0` because older releases fail the dashboard tests (2026-09-26).
- [x] `max <text>` routes to the agent (D1). `LazyTyperGroup.parse_args` turns a first word that isn't a command or option into `max ai ask "<all the words>"` (2026-10-02).
- [ ] `max --help` and every existing command keep working unchanged.

### Step 4: Agent v2
- [x] A tool-calling loop in core (`core/agent/`), 2026-10-02, branch `feat/ai-agent`:
  1. The model picks a tool from the catalog.
  2. The engine runs it.
  3. The result goes back to the model, and the loop repeats until done.
- [x] Plan and confirm: each step shows as it runs, and MOVES/OVERWRITES/DELETES ask first (D4). `--dry-run` (and the AI page's Dry run) shows the steps without running them. A full plan shown before the first step is still open.
- [x] Undo: file changes go through the transaction log; the AI page's Undo... opens Activity's Undo tab, and the agent can run `files.undo`.
- [x] Live steps: the agent reports `Step`s through an `on_step` callback, which the CLI prints and the AI page shows. (A callback, not the event system: steps aren't progress bars.)
- [x] The dashboard's AI page (it replaced Chat) and `max <text>` run the same agent.
- [x] **Load commands on demand (maintainer, 2026-09-26).** Don't put the whole command catalog in the context window. Done: the first prompt lists the groups with their action names (about 700 tokens); `load_group` returns one group's arguments (250 to 1,800 tokens). Feature packs don't exist yet, so every group shows.
  - At the start, the agent sees only the parent command groups, each with a one-line description (`video`, `pdf`, `grab`, ...).
  - When a request needs a group, the agent calls a lookup tool (for example `load_group("video")`). That tool returns the group's child commands with their parameters, defaults and usage notes, and only then does the agent call them.
  - The agent sees only the groups for features the user turned on (see `feature-packs.md`).
  - Loaded groups stay available for the rest of the conversation, so they aren't fetched twice.
  - Measure the token cost per request, and add a test that the first prompt holds only the group list.
  - Goal: an efficient agent that uses a small context, picks the right command, and gets the work done.
- [x] Guardrails: path limits, a step limit (12), a token limit (60,000 per request), a dry-run mode.
- [x] Replace `ai ask`'s "write one command string" approach, keeping `ai ask` as an alias. `ai ask` and `ai chat` ran whatever command string the model wrote through `subprocess`; both use the agent now.
- [x] Look before acting (maintainer, 2026-10-02: "the AI is not having the necessary tools ... to have more context"). `list_folder` and `inspect` read a folder or file without changing it, from the pages' `describe` functions; an audio folder's facts name its top artists and albums. Asked how to organize a folder of tagged MP3s, the agent now proposes `audio organize` by Artist/Album instead of a `smart-sort` into "Other". A dry run no longer asks for confirmation. `smart-sort` reads JSON in a code fence and falls back to a folder per kind (Music, Videos ...) instead of "Other", without a traceback.
- [x] More context (maintainer, 2026-10-02): `find_files`, `probe_link` and `recent_activity` look tools; long jobs can go to the queue from the AI page (`run_action` with `queue`). The agent writes every request and action to the activity log from the CLI too, so "what did you just do?" works across runs.
- [ ] Next tool ideas, not built: `ask_choice` (buttons on the AI page for a decision), image understanding for sorting photos by content (costs tokens per image; ask before many).
- [x] Main AI and fallback (maintainer, 2026-10-03: OpenRouter's free credit ran out; fall back to Gemini's free API). `core/engines/ai_providers.py`: OpenAI or a custom URL, OpenRouter, Gemini and Ollama, each with its own key and model; a request that fails on the main AI goes to the fallback, which then stays in use for the session. Settings page: Main AI, Fallback, keys and models per provider, Check AI. `max config setup` asks for both and keeps the rest of the file.
- [ ] Small local models: D5's simpler one-step mode. A model that can't call tools gets a clear error today.
- [ ] The `ai` group (analyze, create, search ...) isn't in the catalog, so the agent can't call it yet.

### Step 5: Onboarding and packaging
- [ ] A first-run wizard covering the API key (optional), FFmpeg and the download folder, with sensible defaults. It uses the arrow-key select menus from `feature-packs.md`, so you pick which settings to set up instead of typing answers.
- [ ] Friendlier errors: "did you mean ...", plus a next step in every message.
- [ ] Distribution for non-technical users, for example a Windows installer or a single executable. Research needed.

### Tests and docs
- [ ] Routing tests for D1 and D2, including non-interactive terminals. D2 is covered in `tests/test_front_door.py`.
- [x] Agent tests with a mocked model: tool selection, confirmation, refusal, dry run, limits (`tests/test_agent.py`, `tests/test_cli_ai.py`, `tests/interface/tui/test_ai_page.py`). Checked live against OpenRouter's `openrouter/free` on 2026-10-02.
- [ ] README and `docs/`: a new "Getting started" built around `max` and plain-language requests.

## Related drafts

- `dashboard-ui-redesign.md`: page layout, scrolling, a design standard, full command options.
- `cli-dashboard-sync.md`: CLI and dashboard share one live state.
- `paths-from-anywhere.md`: run commands on any file or folder, not only the current one.
- `feature-packs.md`: choose which features and dashboard pages you want.
- `user-workflows-aliases.md`: saved recipes, which the agent could create.

## Decisions

- 2026-09-26: Drafted from the maintainer's idea: "`max` opens the dashboard, `max <text>` goes to an AI agent."
- 2026-09-26: The maintainer answered D1-D5 (see above). Step 1 merged in PR #16.
