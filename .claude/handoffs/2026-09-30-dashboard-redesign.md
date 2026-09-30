# Session Handoff: Dashboard redesign (theme, sidebar, Home, Download, queue)

**Date:** 2026-09-30 **Project:** `D:\GitHub\Personal\max-cli` **Session:** continued from `2026-09-26-catalog-and-download-page.md`

**Goal (user's words):** "after you finish, make a handover", after getting the redesigned Download page back ("it was looking good").

## Current State

- **Task:** the dashboard redesign (`PLANS/active/dashboard-design-system.md`). The maintainer tests each change by running `max` and asks for fixes by screenshot or description.
- **Done this session:**
  - local CI;
  - the front door (bare `max` opens the dashboard);
  - catalog ports for `images`, `pdf` and `files`;
  - smoothness fixes;
  - the sidebar;
  - the `max-cyber` theme;
  - the Home command center;
  - the queue fix with the Jobs window;
  - the design skill;
  - the Download page redesign.
- **Phase:** between features. The Download redesign PR (#34) and this handoff are the last pieces.

## Repository State

- **Branch:** `main`. Merged this session:
  - #24 local CI;
  - #25 front door;
  - #26 images, #27 pdf and #28 files on the catalog;
  - #29 smoothness;
  - #30 sidebar;
  - #31 Home and theme;
  - #32 queue and Jobs window;
  - #33 design skill.
- **#34** is the Download redesign plus this handoff (branch `feat/download-redesign`). The maintainer asked to have the redesign back, so it is merged when its checks pass. Check with `gh pr view 34`.
- **Stash:** `stash@{0}: WIP on main: 5378faa` belongs to the maintainer. Leave it alone. Never use `git stash`; save a patch file instead.
- **Maintainer's `~/.max_cli/dashboard_prefs.json`** holds their own choices (`download_mode`, `download_format`, `last_page`, an old `sidebar_compact`). Don't edit it. Screenshots use a throwaway home (below).

## Plan Status

- **Dashboard design:** `PLANS/active/dashboard-design-system.md`.
  - Done: R0 (smoothness), the sidebar, R1 (skill and screenshot script), R2 (theme), R3 (Home and Download), and the queue fix.
  - Open, in likely order:
    1. The maintainer checks a real download and scrolling in Windows Terminal.
    2. R1 leftovers: vendor `gfargo/tui-design-skill` (approved; read it in full first, add an override block, record it in `.claude/skills/THIRD_PARTY.md`), and mechanical checks in `check_rules.py` (no hex colours in `interface/tui`, no table rebuilds in `refresh_data`).
    3. R2 leftovers: a light theme variant, page jumps in the command palette, page keys in the footer, and theme-coloured scrollbars on pages (they still show a dark bar).
    4. R3 leftover: path and URL autocomplete (`textual-autocomplete`, approved).
    5. R4: redesign Queue, History, Files, Tools, Analytics (with `textual-plotext`, approved), Config, System and Chat in the same style. Move the System and Analytics folder-size walks into a thread worker.
- **Command catalog:** `PLANS/active/command-catalog.md`. `video`, `images`, `pdf`, `files` and `grab download` are ported.
  - Next: `audio` (the last heavy group), then step 5 (agent tool views: `list_groups`, `load_group`, token budget test), then step 6 (delete `command_registry.py` and `command_executor.py`; only `audio` and `ai` remain there).
- **Roadmap:** `PLANS/active/dashboard-first-ai-agent.md`. Front door part 1 is done. The big next feature is Step 4: the agent behind `max "request"`.

## Quality Gates (on the #34 branch, 2026-09-30)

- **pytest:** dashboard suite 114 passed, 1 skipped. The full run of `python scripts/ci_local.py --full` was in progress when this was written; #34's result says whether it passed.
- **ruff:** clean. **mypy:** 37, matching `mypy-baseline.txt`.
- **Local CI:**
  - `python scripts/ci_local.py` is the quick check.
  - `--full` covers Python 3.9 to 3.12 and the build.
  - The guard hook refuses `gh pr create` until HEAD has passed `--full` on a clean tree. Run `--full` as its own command before `gh pr create`: the hook checks before the command runs.

## What We Did

- **Local CI** (`scripts/ci_local.py`, #24).
  - It mirrors `.github/workflows/ci.yml`: fresh uv venvs, two suites at once, coverage only on 3.11.
  - The timing test runs alone, because it failed while two suites shared the CPU.
  - A pre-push hook, and the guard for PRs.
- **Front door** (#25): bare `max` opens the dashboard when stdin and stdout are a terminal. `textual>=6.0.0` and `psutil` are required now.
- **Catalog ports** (#26-#28).
  - New: `Param.multiple`, `ParamKind.SECRET`, and the drift test's `--force` rule.
  - Files operations return `undo_group`.
- **Smoothness** (#29).
  - Tabs were relabelled on every progress tick, restarting their animation.
  - The Screen background was left near-black.
  - Queue and History tables were rebuilt every 2 s.
- **Sidebar** (#30). The maintainer asked for three rounds of changes:
  - A grouped list of 3-row `NavItem`s, starting as a 7-column icon strip with a `»`/`«` button.
  - Number keys, `Alt+Left`, `?` help, badges.
  - Equal margins, centred icons.
- **Theme and Home** (#31): `interface/tui/theme.py` (`max-cyber`); the Home command center with `Digits`, `Spark`, `Meter`, `BarChart`, `HBarChart` and a quick launch.
- **Queue** (#32):
  - The dashboard never started the queue worker; now it does.
  - The executor passes cancel and progress hooks.
  - Two task-store races are fixed.
  - `TaskItem.speed` and `eta` are text.
  - New Jobs window (`J`).
- **Design skill** (#33): `.claude/skills/max-tui-design/SKILL.md` and `scripts/tui_screenshot.py`.
- **Download** (#34): the same card style as Home, with Save to in the LINK card and state-coloured rows with a `Meter`.

## Decisions Made

- **One theme, `max-cyber`**, registered in `theme.py`. The old `$variable` overrides in app CSS reached only the app's CSS.
- **Our own charts** in `widgets/charts.py`; `textual-plotext` isn't needed for Home.
- **The dashboard runs the queue.** The worker starts on mount; tasks left from earlier runs run too.
- **Sidebar:** icons first; the choice is saved as `sidebar_collapsed`. The older `sidebar_compact` key is ignored, so the maintainer's old choice doesn't hide the new default.
- **Every page follows the `max-tui-design` skill.** Read it before any dashboard work.

## Pitfalls (hit this session)

- **Shell escaping:** backslashes and `\n` in bash heredocs and `sed` get mangled; it happened five times. Write change scripts with the Write tool and run them, or use the Edit tool.
- **Textual CSS:**
  - A widget's `DEFAULT_CSS` is scoped to it, so `Sidebar.-compact NavItem` there never matches.
  - App CSS beats widget CSS.
  - A lone `padding-left` resets other sides.
  - `$text-muted` isn't a valid border colour.
  - `$boost` as a text colour is near-white.
  - The Footer docks at the bottom and covers other bottom docks.
  - The skill lists these and more.
- **Ambiguous-width symbols** (`●`, `▶`) are two columns wide in some fonts. Use `»`, `!`, `·`.
- **Mocks and signatures:** `patch(..., autospec=True)` when code inspects a function's signature. The queue executor does.
- **`TaskManager.get()` searches history too.** To check the queue, use `get_all()`.
- **Pydantic doesn't validate assignment:** a wrong type saves and fails on the next load.
- **A test hangs under load:** in one `--full` run, Python 3.9 stopped at the 600 s step limit while another suite ran beside it. Alone it passes in 105 s. `ci_local.py` now streams each step to its log, so the next hang keeps pytest's stack dump (`faulthandler_timeout`) in `.ci-venvs/logs/`. Suspect a Pilot test that waits on a worker thread.
- **Low memory** killed an idle background test run once. Run heavy checks in the foreground, and don't restart a reaped run without asking.
- **The screenshot tool** is `python scripts/tui_screenshot.py <page> <out.png> [--size 120x40] [--sample] [--jobs]`. It uses a throwaway home and needs Chrome or Edge for the PNG.

## Context to Remember

- **Platform:** Windows 11, Python 3.11 (`python`), Git Bash; uv 0.10.
- **Maintainer preferences:**
  - Terse replies (caveman style). Commits, PRs, docs and plans in plain English, following stop-slop.
  - One branch and one PR per piece; merge when they say "merge". They sometimes say "merge and next".
  - They judge the dashboard by using it, and they care about looks and smoothness. Show screenshots, and fix what they point at quickly.
  - Ask before `pyproject.toml` changes; the guard prompts. Don't touch the stash or `~/.max_cli`.

## Next Steps

1. [ ] `git checkout main && git pull`. Confirm #34 is merged; if not, check `gh pr checks 34` and merge when green (the maintainer asked for it).
2. [ ] Ask the maintainer how Download and the Jobs window feel in real use, and whether the flashing is gone in Windows Terminal.
3. [ ] Next redesign, per the skill: the Queue page (it pairs with the Jobs window), then History, Files and Tools. Show screenshots before merging.
4. [ ] Or, if the maintainer prefers features: port `audio` to the catalog, then the agent tool views, then the agent (`max "request"`).
5. [ ] Small debts: vendor `tui-design-skill`; add the TUI rules to `check_rules.py`; theme the page scrollbars.

## Files to Review on Resume

- `.claude/skills/max-tui-design/SKILL.md`: the design system; read it first for any dashboard work.
- `PLANS/active/dashboard-design-system.md`: decisions and the open items.
- `src/max_cli/interface/tui/theme.py`, `widgets/home_panel.py`, `widgets/charts.py`, `widgets/sidebar.py`, `widgets/jobs_drawer.py`, `widgets/download_panel.py`.
- `scripts/ci_local.py` and `scripts/tui_screenshot.py`.
