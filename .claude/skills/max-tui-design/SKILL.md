---
name: max-tui-design
description: The Max dashboard's design system - the max-cyber theme, page anatomy (header, cards, grids), shared components (Digits, charts, chips, rows, Jobs window), smoothness rules and CSS pitfalls. Use before building or redesigning any dashboard page or widget in src/max_cli/interface/tui, so every page looks and behaves like Home and the sidebar.
---

# Designing Max dashboard pages

Every page in `max` (the Textual dashboard) should look like one product: the Home page and the sidebar set the style. Read this before you touch a page, then copy the patterns below rather than inventing new ones. The plan behind it is `PLANS/active/dashboard-design-system.md`.

**Reference implementations** (open them while you work):

| File | What to copy from it |
|------|----------------------|
| `interface/tui/theme.py` | The `max-cyber` theme and its colour tokens |
| `interface/tui/widgets/home_panel.py` | Page header, cards, grid rows, `Digits` tiles, gauges, charts, empty states, one-repaint refresh |
| `interface/tui/widgets/charts.py` | `BarChart`, `HBarChart`, `Spark`, `Meter` |
| `interface/tui/widgets/sidebar.py` | Large click targets, badges, compact mode, CSS that depends on a parent's state |
| `interface/tui/widgets/jobs_drawer.py` | Live list with aligned columns, refresh while open only |
| `interface/tui/widgets/queue_panel.py` | Live lists of widget rows updated in place (`TaskRow.show`, `QueuePanel._sync`), tiles that dim at zero |
| `interface/tui/tables.py` | `show_rows`: refill a `DataTable` without flicker |

## The look: futuristic command center

Deep navy panels, neon cyan for live values, magenta for peaks and "now", violet for focus. Uppercase card titles, big block digits for key numbers, thin block-character charts. Calm, dense and readable; no decoration that doesn't carry information.

### Colours: theme tokens only

The app registers `max-cyber` (`theme.py`). Style with its variables, in CSS and in `Content` styles alike. Never write a hex colour or a colour name (`red`, `green`) in page CSS or markup: a user can switch themes with Ctrl+P, and hard-coded colours break.

| Token | Means | Use for |
|-------|-------|---------|
| `$primary` (cyan) | live, important, "go" | big values, card titles, selected chips, running progress |
| `$secondary` (magenta) | highlight | today's bar, peaks, the brand mark `◢◤` |
| `$accent` (violet) | focus, where you are | the active page, focused inputs, the Jobs window's top edge |
| `$success` / `$warning` / `$error` | state | done / waiting or busy / failed |
| `$panel` | page background | set on every page |
| `$surface` | card background | every card |
| `$boost` | hover, tracks, unselected chips | backgrounds, the empty part of bars |
| `$border` | quiet lines | card borders, dividers |
| `$text-muted` | secondary text | captions, meta lines, hints |

Load colours for a percentage: below 60% `$primary`, 60-84% `$warning`, 85% and up `$error` (`home_panel.load_colour`).

Don't redefine `$variables` in the app CSS: those reach only the app's own CSS, not widgets' `DEFAULT_CSS` or `Content` styles. Change `theme.py` instead.

## Page anatomy

```
┌ page (padding 1 2, background $panel) ────────────────────────────┐
│ ◢◤ PAGE // WHAT IT DOES                        [page controls]    │  header, height 3
│ greeting or one-line help, muted                                  │
│                                                                   │
│ ╭ CARD TITLE ──────────╮  ╭ CARD TITLE ──────────╮                │  Grid row: grid-gutter 0 2
│ │ content              │  │ content              │                │  margin-bottom 1
│ ╰──────────────────────╯  ╰──────────────────────╯                │
│ ╭ CARD TITLE ─────────────────────────────────────╮               │  full-width card
│ ╰─────────────────────────────────────────────────╯               │
└───────────────────────────────────────────────────────────────────┘
```

**Header.** A `Static` with two lines of `Content`, height 3, plus the page's own controls on the right (a segmented switch, status lights):

```python
Content.assemble(
    ("◢◤ ", "bold $secondary"),
    ("DOWNLOAD", "bold $primary"),
    (" // MEDIA GRABBER\n", "bold"),
    ("One line that says what to do here", "$text-muted"),
)
```

**Cards.** Every section is a card: `$surface` background, `round $border`, an uppercase `border_title` in bold `$primary`, `padding: 0 1`. The border turns `$primary` on hover or when a field inside has focus:

```css
.card {
    height: auto;
    background: $surface;
    border: round $border;
    border-title-color: $primary;
    border-title-style: bold;
    padding: 0 1;
    margin-bottom: 1;
}
.card:hover, .card:focus-within {
    border: round $primary;
}
```

Set titles in `on_mount`: `self.query_one("#my-card").border_title = "QUEUE"`.

**Rows of cards.** Use a `Grid` with `grid-size`, `grid-columns` (e.g. `3fr 2fr`) and `grid-gutter: 0 2`. Give fixed heights to cards that hold charts or scroll areas (Home uses 9, 6, 14, 11), and `height: auto` to the rest.

## Components

| Need | Use | Notes |
|------|-----|-------|
| A key number | `Digits` in bold `$primary`, a muted caption under it | See `home_panel.Tile`; show "0" and "nothing yet", not "0.00 B" |
| A percentage right now | `Digits` + `%` + a `Spark` (history) or a `Meter` (fullness) | `Spark` has a fixed 0-100 scale; Textual's `Sparkline` doesn't |
| Counts per day | `charts.BarChart` with `Bar(label, value, highlight=today)` | Shows its own empty-state sentence |
| Counts per kind | `charts.HBarChart` with `HBar(label, value, style)` | Largest first |
| Progress of one job | `charts.Meter` with a muted line under it: `42%  ·  2.1 MB/s  ·  0:31 left` | Not Textual's `ProgressBar`: it runs its own timer and ignores the theme |
| A choice of 2-3 options | `.segmented` buttons | `-selected`: `$primary 25%` background, `$primary` text, `tall $primary` border |
| A choice of many | `.chip` buttons in a `Grid` | Same selected style as segmented |
| The main action | one `variant="success"` button, `width: 1fr` | One per page; secondary actions are plain buttons |
| A list of jobs or events | rows with a coloured left edge (`border-left: outer <state colour>`) | See `DownloadRow`; align columns with fixed widths |
| Status lights | `● LABEL` in `$success` or `$text-muted` | Home header |
| Long tables | `DataTable` filled through `tables.show_rows` | Keeps cursor and scroll |
| A long list inside a scrolling page | a page of rows (8) with a filter `Input` and `< Prev` / `Next >` | Download History; never an inner scroll area |
| Facts about one thing | lines of `key` (muted, fixed width) and value | `download_panel.media_facts`; skip facts the source left out |
| A few options in a card | `ActionForm(action, include=..., compact=True)` | Two fields a row, checkboxes, help as tooltips |
| A button inside a list row | one line high: `height: 1; border: none` on a row class | `DownloadRow`; three-line buttons made rows twice as tall |
| A setting | caption above a control that fits it: `Select` for choices, `Checkbox` for on/off, a password `Input` with Show for secrets, `Input` + Change... for folders | `settings_panel.py` |
| A link to another page | `self.post_message(messages.OpenPage("queue"))` | The app navigates |

Separate facts on one line with `  ·  `. Label cards and headings in UPPERCASE; write sentences in normal case.

### States every section needs

- **Empty:** one muted sentence that says what will appear and how to start ("Nothing yet. Press 2 to download something.").
- **Loading:** disable the button that started the work and relabel it ("Checking"; keep the label within the button's width), and show a one-line spinner with the seconds so far, updated with `layout=False` (`DownloadPanel._start_checking`). Past a few seconds, say why it can take long. Stop it only for the answer to the latest request.
- **Error:** the reason in `$error`, in plain words, and what to do next. Errors from a finished action also go to `self.notify(..., severity="error")`.

## Smoothness rules (these caused real flicker)

On Windows, Textual can't make the terminal draw a frame all at once, so every repaint risks a half-drawn screen. Fewer, smaller repaints:

1. A page's timed refresh runs inside `with self.app.batch_update():`, one repaint for everything.
2. Update a widget only when its value changed. Keep the last value and compare (`Tile.show`, `set_data` in `charts.py`).
3. A one-line label that changes often updates with `Static.update(text, layout=False)`.
4. Throttle progress to at most 2 updates a second per job, and group bar and text in one `batch_update`.
5. Never rebuild widgets or tables on a timer. Mount once, then change values. Refill tables with `tables.show_rows`.
6. Don't set a tab's `label` unless the text changed: it restarts the tab underline animation.
7. Blocking work (network, disk walks, AI) runs in a thread worker; post results back with `call_from_thread`.
8. One scroll area per page. An inner scroll area gets a fixed height, never `1fr`.
9. Something that refreshes only matters while visible: pause its timer when hidden (`jobs_drawer.py`).

## CSS pitfalls (each one cost a fix)

- A widget's `DEFAULT_CSS` is scoped to that widget: a rule starting at a parent (`Sidebar.-compact NavItem`) never matches there. Put rules that depend on a parent's state in the parent's CSS.
- The app's `CSS` beats every widget's `DEFAULT_CSS`, whatever the selector. A global rule like `Button { min-width: 12 }` needs its exceptions in the app CSS too. The app's `DataTable { height: 1fr; min-height: 8 }` made the Download history 35 rows tall; `#download-history-table` has its exception there.
- In a narrow column, put a field's caption above it (`.field-caption`), not beside it: a label column cut the quality buttons' sizes off.
- Set `padding` as a whole (`padding: 0 2 0 1`). A lone `padding-left` reset the other sides.
- `content-align` doesn't move text a widget draws in `render()`; centre it there.
- `$text-muted` isn't allowed as a border colour; use `$border`.
- Don't dock anything else at the bottom: the `Footer` docks there and covers it.
- Use ASCII or single-width marks for badges and states (`»`, `!`, `·`, `✓`, `✗`). Ambiguous-width symbols such as `●` or `▶` are two columns wide in some fonts and break alignment.
- Don't name a widget attribute `_task`: `MessagePump` keeps its asyncio task there, and overwriting it crashes the widget on mount. Other private names Textual uses: `_parent`, `_id`, `_classes`, `_nodes`.
- User text (titles, paths, URLs, errors) goes in as `Content(text)` or through `text.markup()`'s `$variables`, never as markup: `Song [red]` loses text, and some strings crash the parser.

## Keyboard

- Pages are `1`-`8` (`sidebar.SECTION_KEYS`); `J` Jobs; `?` help; `Esc` back to the sidebar.
- The field a page is for gets focus when it shows (`on_show`).
- Every action has a key or a button; the footer shows a page's keys.
- New global keys go in the app's `BINDINGS` and in `GLOBAL_KEYS` (the help screen).

## Before you open a PR

1. Screenshots: `python scripts/tui_screenshot.py <page> <out.png>` renders a page at 140x44 with a temporary home folder. Look at it at 120x40 and 90x30 too.
2. Tests with Pilot for behaviour (see the `max-testing` skill). For flicker fixes, test that nothing redraws when nothing changed. To wait for a thread worker, poll with `await pilot.pause(...)`; never call `event.wait()` in the test: it blocks the app's event loop, the worker never starts, and a fake that waits for Cancel hangs the run. Give such fakes a deadline.
3. Every colour is a theme token; every user string is `Content`.
4. `python scripts/ci_local.py --full`.
