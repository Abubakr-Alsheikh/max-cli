# Plan: Dashboard Design System and Smoothness

**Status:** In Progress
**Priority:** P1
**Updated:** 2026-09-28

## Goal

The dashboard feels calm and smooth. Pages look like one product, with the same spacing, colours, states and keys everywhere, and they never flash or show black blocks. Written rules and automatic checks keep new pages that way, so design work doesn't have to be redone later.

This plan replaces the "design standard" item in `dashboard-ui-redesign.md`.

## Why (the maintainer's report, 2026-09-28)

- The Home and Download pages "don't feel good" to use or look at.
- During a download the UI flashes.
- Scrolling a page up and down turns half the screen black for a moment.

## Research findings

**On Windows, Textual can't show a frame all at once.** Textual asks the terminal for synchronized output (DEC mode 2026) on Linux and macOS, but `windows_driver.py` never does, so on Windows every frame reaches the terminal as it is written. When a burst of repaints arrives, the terminal can show a half-drawn frame. The fix on our side is fewer and smaller repaints.

**Causes in our code**, all fixed in R0:

1. Every progress tick set both Download-tab labels, even to the same text. Setting a `Tab.label` restarts the tab underline animation (0.3 s), so the underline repainted every frame for the whole download. This was the flashing.
2. The row's progress text used `Static.update()` with its default `layout=True`, so each tick laid out the whole page.
3. Nobody set the `Screen` background, so it stayed at the theme's near-black `$background` while pages used `$panel`. Any spot not yet repainted during a scroll showed as black.
4. Queue and History cleared and refilled their tables every 2 s, which repainted the table and snapped the cursor and scroll to the top.
5. Home, System and Analytics updated about 10 labels every 2 s, one repaint each.
6. `#home-activity-scroll` was a `1fr` scroll area inside a scrolling page. It got squeezed on every reflow and fought the page for the mouse wheel.

**Packages.** Stay on Textual: it is MIT, maintained (8.2.8 in June 2026), covers Python 3.9 to 3.14, and nothing else offers CSS theming, workers, a command palette and Pilot tests together. `prompt_toolkit` needs Python 3.10+, `urwid` has partial Windows support, and `asciimatics` stopped releasing in 2023.

**Apps worth studying:** Posting (forms, command palette, themes; closest to the Download page), Harlequin (three-panel layout, theme config), Dolphie (live dashboards; GPL, ideas only), Elia (chat layout).

## Decisions (maintainer, 2026-09-28)

- [x] Vendor `gfargo/tui-design-skill` (MIT) next to `textual-builder`. Read it in full, check it against Textual 8, add a Max override block and record it in `.claude/skills/THIRD_PARTY.md`.
- [x] Add `textual-autocomplete` (path and URL completion in inputs) and `textual-plotext` (charts for Analytics and System). Both are MIT and support Python 3.9. `textual-dev` stays out.
- [x] Order: smoothness fixes first (R0), then rules, theme, and page redesigns.

## Tasks

### R0: Smoothness fixes
- [x] Relabel the Download tabs only on a state change, and only when the text differs.
- [x] Progress text updates without a page layout (`layout=False`), bar and text in one `batch_update`, at most every 0.5 s per download.
- [x] History tab keeps its columns; only rows are refilled.
- [x] `Screen` and every page paint `$panel`.
- [x] `interface/tui/tables.py:show_rows` skips unchanged refills and keeps the cursor and scroll; Queue and History use it. Their user text goes in as plain `Content`, not markup.
- [x] Home, System and Analytics refresh inside one `batch_update`.
- [x] `#home-activity-scroll` gets a fixed height.
- [ ] The maintainer checks a real download and scrolling in Windows Terminal.

### R1: Design rules and checks
- [ ] Vendor `tui-design-skill` (see Decisions).
- [x] Write `.claude/skills/max-tui-design/SKILL.md`: theme tokens, page anatomy, components, states, smoothness rules, CSS pitfalls, keyboard, PR checklist (2026-09-30). It supersedes the draft rules below.
- [x] Point `AGENTS.md` at it.
- [x] `scripts/tui_screenshot.py`: render any page with a throwaway home, optional sample data and the Jobs window.
- [ ] Mechanical checks in `.claude/hooks/check_rules.py` for `interface/tui/`: no hex or named colours outside the theme; no `DataTable.clear(columns=True)` or `recompose()` in a `refresh_data`; progress callbacks throttled.
- [ ] Every UI PR includes Pilot screenshots (SVG to PNG) of the pages it changes.

### R1.5: Sidebar and navigation (maintainer's choice, 2026-09-29: grouped, all 10 pages kept)
- [x] Grouped list (Do, Track, Setup) with one-row items, arrow keys and Enter.
- [x] Number keys 1-9 and 0 jump to pages; `Alt+Left` goes back; `Esc` returns to the sidebar.
- [x] `?` help screen listing every shortcut.
- [x] Badges: running downloads, waiting tasks, failures since History was last opened. They redraw only when a number changes.
- [x] Remember the last page and the icons-only choice; icons only below 100 columns.
- [x] Maintainer feedback (2026-09-29): the expanded sidebar's right margin was wider than its left, and the collapsed strip had too much padding. Margins are now equal, and the icon strip is 7 columns with centred icons.
- [x] Maintainer feedback (2026-09-29): items were too small and the collapsed icons hard to see.
  - Each page is now a 3-row target.
  - Colour emoji replace the thin symbols.
  - The sidebar starts as icons, with a `»`/`«` button to expand it and a tooltip with the name on each icon.
  - The choice is saved as `sidebar_collapsed`; the older `sidebar_compact` key is ignored.

### R2: Theme and navigation
- [x] One registered Max theme, `max-cyber` (`interface/tui/theme.py`), replaces the `$var` overrides in `app.py`. The Ctrl+P theme choice is remembered in `ui_prefs` (2026-09-29).
- [ ] A light variant.
- [ ] Page jumps and main actions in the command palette.
- [ ] Footer shows each page's keys.
- [ ] Style the page scrollbars from the theme (the track shows as a black bar).

### R3: Home and Download redesign
- [x] Home: a command center with a futuristic look (maintainer's request, 2026-09-29).
  - Header with greeting, clock and status lights (online, FFmpeg, AI key).
  - Live CPU and memory gauges with a 2-minute history, and a disk capacity meter, all in large `Digits`.
  - Downloads, actions, queue and downloaded-size tiles.
  - Charts: activity over 14 days (today in magenta) and a by-type breakdown, from `widgets/charts.py`.
  - Quick launch with number keys, and a recent-activity feed.
- [x] Download: the same style (2026-09-30).
  - `◢◤ DOWNLOAD // MEDIA GRABBER` header with the Simple/Advanced switch.
  - A LINK card holds the link and Save to, full width, so paths aren't cut.
  - PREVIEW and OUTPUT cards side by side, then ADVANCED and TRANSFERS.
  - Download rows get a state-coloured left edge and a `charts.Meter` instead of Textual's ProgressBar.
- [x] Download, second round (maintainer's feedback, 2026-09-30):
  - Advanced options were one field per five rows; now a compact card beside the preview (`ActionForm(compact=True)`).
  - History was a 35-row scroll area inside the page (the app's `DataTable` rule); now 8 rows a page with a filter, Prev/Next, and Copy link.
  - The preview shows views, likes, upload date, chapters, subtitles, the best audio stream, and MP3 sizes per bitrate.
  - A TOOLS card brings the rest of `max grab` in: stats (`status`), the YouTube fix (`pot-setup`), and links to the folder, the queue and settings.
  - Download rows are four lines: one-line buttons, and "Clear finished".
- [ ] Mockups as screenshots for the maintainer's approval before building.
- [ ] Then build, with empty, loading and error states for each section.
- [ ] Path and URL autocomplete (`textual-autocomplete`).

### Queue in the dashboard (maintainer's report, 2026-09-29)
- [x] Queued downloads stayed pending: nothing in the dashboard started the queue worker. The app now starts it on mount.
- [x] Queued actions report progress, speed and ETA, and a running one stops when cancelled.
- [x] Two task-store races found on the way: a refused read during `refresh()` wiped the history; a refreshed copy kept a cancelled task queued forever.
- [x] Jobs window (`J`): running job with a progress bar, speed and time left, waiting jobs, the last finished ones. Opens when you queue something.

### R4: The other pages
- [ ] Queue, History, Files, Tools, Analytics (`textual-plotext` charts), Config, System, Chat, using the same rules.
- [ ] Move System's and Analytics' folder-size walks into a thread worker.

## The Max TUI rules (draft for R1; the maintained version is the `max-tui-design` skill)

- Colours come only from theme variables (`$primary`, `$panel`, `$text-muted`, ...). Never hex or `red` in page CSS.
- One scroll area per page. Nested scrollables get a fixed height, never `1fr`.
- Updates that repeat (progress, timers) are throttled, grouped with `batch_update`, and skip unchanged values. A one-line label updates with `layout=False`.
- Never rebuild widgets or tables on a timer. Mount once, then update values.
- Blocking work (network, disk walks, AI) runs in a worker. The UI thread only draws.
- Every section has an empty state that says what goes there and how to start, and a loading state.
- Results and errors show as toasts (`notify`), and the page keeps its place.
- User text (titles, paths, URLs, errors) is `Content`, never markup.
- A widget's `DEFAULT_CSS` is scoped to that widget: a rule there that starts from a parent (`Sidebar.-compact NavItem`) never matches. Put rules that depend on a parent's state in the parent's CSS.
- App CSS beats every widget's `DEFAULT_CSS`, whatever the selector. A global rule such as `Button { min-width: 12 }` needs its exceptions in the app CSS too.
- In Textual CSS, set `padding` as a whole (`padding: 0 2 0 1`). A lone `padding-left` reset the other sides.
- `content-align` doesn't move text a widget draws in `render()`; centre it there.
- Badges and markers use ASCII or single-width symbols. Ambiguous-width symbols (such as a filled dot) are two columns wide in some fonts.
- The first input a page needs gets focus. Every action has a key, and the footer shows it.

## Related

- `dashboard-ui-redesign.md`: the earlier idea list; its design-standard item moves here.
- `grab-page-redesign.md`: the current Download page layout.
