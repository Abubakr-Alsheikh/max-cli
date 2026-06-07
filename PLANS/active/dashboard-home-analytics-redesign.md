# Plan: Dashboard Home Redesign + Analytics Tab

> Status: Draft
> Priority: P1
> Related: UX & Laziness (Feature 2C Phase 3)

## Overview

Redesign the Home tab into a live system dashboard and add a dedicated Analytics tab. The Home tab becomes a "command center" with real-time system stats, richer activity feed, and polished quick-action cards. The Analytics tab provides deep system monitoring (CPU, memory, disk) and activity statistics.

## Goals

- [ ] **Home tab redesigned** — live system status bar (CPU/Memory/Disk), stats cards, richer activity feed, better quick-action grid layout
- [ ] **Analytics tab created** — live CPU, memory, disk monitoring, per-category activity breakdowns, storage management
- [ ] **`psutil` added as optional TUI dependency** for cross-platform system monitoring
- [ ] All auto-refreshing every 2 seconds for a "live terminal" feel
- [ ] Zero UX regressions on existing tabs

## Implementation Details

### Phase 1: Add `psutil` Dependency

**File:** `pyproject.toml`

Add `psutil` to the `tui` optional dependency group:

```toml
tui = [
    "textual>=0.48.0",
    "psutil>=5.9.0",
]
```

`psutil` is loaded lazily inside the panel widgets, so `max --help` does not import it. It is a pure-Python, cross-platform library (no C extensions to compile) — standard for system monitoring.

### Phase 2: Home Panel Redesign

**File:** `src/max_cli/interface/tui/widgets/home_panel.py`

Rewrite `HomePanel` with three sections stacked vertically:

#### Section 1: Live System Status Bar

```
┌─────────────────────────────────────────────────────┐
│  CPU ████████░░ 72%    Mem ██████░░░░ 58%    Disk ██░░ 23%  │
└─────────────────────────────────────────────────────┘
```

Three horizontal `ProgressBar` widgets (CPU, Memory, Disk) with color thresholds:
- Green (< 60%)
- Yellow (60–85%)
- Red (> 85%)

Uses lazy `psutil` import inside `_update_system_bar()`.

#### Section 2: Stats Cards Row

Replace the current single-line stats text with styled stat cards:

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  1,247   │ │    89    │ │    12    │ │  4.2 GB  │
│ Commands │ │ Downloads │ │  Queue   │ │  Cached  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

Data sources:
- Commands run + Downloads: `ActivityLog.get_stats()`
- Queue depth: `DaemonManager.get_stats()`
- Cache size: `Cache.get_size()`

#### Section 3: Quick Actions Grid

Current 8-card horizontal row → 2x4 grid with `grid-size: 4;` CSS. Each card gets:
- Subtle background color per category
- Hover highlight (already works via CSS)
- The button text is more descriptive

#### Section 4: Activity Feed

Enhanced recent activity list with:
- Category icon prefix per entry
- Timestamp column
- Truncation indicator for long details
- Scrollable container

#### CSS Updates for HomePanel

```css
#home-status-bar {
    height: auto;
    margin: 1 0;
    padding: 0 1;
}
#home-status-bar ProgressBar {
    width: 1fr;
    margin: 0 1;
}
#home-stats-row {
    height: auto;
    margin: 1 0;
}
.home-stat-card {
    width: 1fr;
    height: auto;
    border: solid $accent;
    padding: 1;
    text-align: center;
}
#home-cards {
    height: auto;
    grid-size: 4;
    grid-gutter: 1;
}
```

### Phase 3: Analytics Tab

**New File:** `src/max_cli/interface/tui/widgets/analytics_panel.py`

Register in `app.py` compose as a new tab between Files and Config.

#### Structure

```
┌─────────────────────────────────────────────────────┐
│  📊 Analytics Dashboard                             │
├─────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────┐  │
│  │  SYSTEM RESOURCES                              │  │
│  │  CPU:   ██████████░░░░░░ 58%  8 cores         │  │
│  │  Mem:   ████████░░░░░░░░░░ 42%  7.8/16.0 GB   │  │
│  │  Disk:  ██████████████████░ 95%  456/480 GB    │  │
│  │  Python: 3.11.4  │  Max CLI: 1.2.0            │  │
│  │  Uptime: 2h 34m  │  Processes: 127            │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌───────────────────┐ ┌───────────────────────────┐│
│  │  ACTIVITY STATS    │ │  STORAGE                  ││
│  │  Total: 1,247      │ │  Cache:    245 MB (1,200) ││
│  │  Success: 1,201    │ │  Backups:  1.2 GB (47)    ││
│  │  Failed: 46        │ │  Logs:     12 MB          ││
│  │  Success Rate: 96% │ │                           ││
│  └───────────────────┘ └───────────────────────────┘│
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  ACTIVITY BY CATEGORY                          │  │
│  │  Downloads   ████████████░░░░░░░░░░  48%       │  │
│  │  Video       ██████░░░░░░░░░░░░░░░░  22%       │  │
│  │  Files       ████░░░░░░░░░░░░░░░░░░  14%       │  │
│  │  PDF         ██░░░░░░░░░░░░░░░░░░░░   8%       │  │
│  │  AI          ██░░░░░░░░░░░░░░░░░░░░   5%       │  │
│  │  Audio       ░░░░░░░░░░░░░░░░░░░░░░   3%       │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

#### Data Sources

| Widget | Source | Refresh |
|--------|--------|---------|
| CPU % + cores | `psutil.cpu_percent(interval=0)` + `psutil.cpu_count()` | Every 2s |
| Memory | `psutil.virtual_memory()` | Every 2s |
| Disk (system + `.max_cli`) | `shutil.disk_usage()` + `psutil.disk_usage()` | Every 2s |
| Max CLI version | `importlib.metadata.version("max-cli")` | On mount |
| Python version | `sys.version_info` | On mount |
| Uptime (Max CLI daemon) | `DaemonManager.get_daemon_uptime()` or process start time | Every 2s |
| Activity totals | `ActivityLog.get_stats()` | Every 2s |
| Cache size | `Cache.get_size()` + `.count()` | Every 2s |
| Backups | `FileOrganizer.get_backup_dir()` enumerate | Every 2s |
| Activity by category | `ActivityLog.get_entries(limit=1000)` → count per category | Every 2s |

#### Key Implementation Details

```python
class AnalyticsPanel(Vertical):
    """Live analytics and system monitoring panel."""

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]📊 Analytics Dashboard[/bold cyan]", id="analytics-title")

        # System resources section
        yield Static("[bold]System Resources[/bold]", id="analytics-sys-title")
        yield Static("", id="analytics-sys-info")

        # Stats overview section
        with Horizontal(id="analytics-stats-row"):
            yield Vertical(id="analytics-activity-stats")
            yield Vertical(id="analytics-storage-stats")

        # Activity by category
        yield Static("[bold]Activity by Category[/bold]", id="analytics-cat-title")
        yield Static("", id="analytics-category-bars")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self._update_system_resources()
        self._update_activity_stats()
        self._update_storage_stats()
        self._update_category_bars()

    def _update_system_resources(self) -> None:
        import psutil

        cpu = psutil.cpu_percent(interval=0)
        cpu_count = psutil.cpu_count()
        mem = psutil.virtual_memory()
        disk = shutil.disk_usage("/")

        # Build system info text with progress bars
        ...

    def _update_activity_stats(self) -> None:
        activity = ActivityLog()
        stats = activity.get_stats()
        ...

    def _update_storage_stats(self) -> None:
        from max_cli.common.cache import get_default_cache
        from max_cli.core.engines.file_organizer import FileOrganizer
        ...

    def _update_category_bars(self) -> None:
        activity = ActivityLog()
        entries = activity.get_entries(limit=1000)
        # Count by category, render as text-based bars
        ...
```

#### CSS for Analytics Panel

```css
AnalyticsPanel {
    padding: 1 2;
}
#analytics-sys-info {
    height: auto;
    border: solid $accent;
    padding: 1;
    margin: 1 0;
}
#analytics-stats-row {
    height: auto;
    grid-size: 2;
    grid-gutter: 1;
}
#analytics-activity-stats, #analytics-storage-stats {
    height: auto;
    border: solid $accent;
    padding: 1;
}
#analytics-category-bars {
    height: auto;
    border: solid $accent;
    padding: 1;
    margin: 1 0;
}
```

### Phase 4: Register Analytics Tab in App

**File:** `src/max_cli/interface/tui/app.py`

```python
# Add import
from max_cli.interface.tui.widgets.analytics_panel import AnalyticsPanel

# In compose(), add between Files and Config:
with TabPane("Analytics", id="analytics"):
    yield AnalyticsPanel(id="analytics-panel")
```

Update auto-refresh panel map to include analytics:
```python
panel_map = {
    ...
    "analytics": "#analytics-panel",
}
```

### Phase 5: Use `format_size` from Common Instead of Duplicated Code

**File:** `src/max_cli/interface/tui/widgets/system_panel.py` + new `analytics_panel.py`

Replace `_format_bytes()` with `from max_cli.common.utils import format_size` to eliminate code duplication.

## Testing Strategy

### Unit Tests

1. **Analytics panel renders without psutil mock:**
   ```python
   @patch("max_cli.interface.tui.widgets.analytics_panel.psutil")
   async def test_analytics_panel_renders(mock_psutil):
       mock_psutil.cpu_percent.return_value = 45.0
       mock_psutil.cpu_count.return_value = 8
       mock_psutil.virtual_memory.return_value = MagicMock(
           total=16*1024**3, used=8*1024**3, percent=50.0
       )
       async with AnalyticsPanel().run_test() as pilot:
           assert pilot.app.query_one("#analytics-sys-info") is not None
   ```

2. **Home panel stats render correctly:**
   ```python
   async def test_home_panel_shows_stats():
       async with MaxDashboardApp().run_test() as pilot:
           home = pilot.app.query_one("#home-panel")
           assert home.query_one("#home-stats-row") is not None
           assert home.query_one("#home-status-bar") is not None
   ```

3. **Analytics tab switch works:**
   ```python
   async def test_analytics_tab_switch():
       async with MaxDashboardApp().run_test() as pilot:
           tabs = pilot.app.query_one(TabbedContent)
           tabs.active = "analytics"
           await pilot.pause()
           assert pilot.app.query_one("#analytics-panel") is not None
   ```

### Manual Testing Checklist

- [ ] `max dashboard` starts and Home tab shows system status bar
- [ ] CPU, Memory, Disk progress bars update every 2 seconds
- [ ] Stats cards show correct counts
- [ ] Quick actions grid is 2x4, clickable, routes to correct tabs
- [ ] Activity feed shows latest 10 entries with proper formatting
- [ ] Analytics tab shows live CPU/memory/disk numbers
- [ ] Activity by category bars reflect actual ActivityLog data
- [ ] Storage section shows correct cache/backup sizes
- [ ] Tab switch works without lag
- [ ] `psutil` not imported at module level (lazy inside methods)
- [ ] All existing tabs (Download, Queue, History, Files, Config, System, AI Chat) work as before

## Success Criteria

- [ ] `max dashboard` launches with new Home tab layout
- [ ] Home tab shows live CPU, memory, disk progress bars
- [ ] Home tab shows 4 stat cards with real data
- [ ] Home tab has 2x4 quick action grid
- [ ] Analytics tab exists between Files and Config
- [ ] Analytics tab shows live system resources
- [ ] Analytics tab shows activity stats and category breakdown
- [ ] Analytics tab shows storage info (cache, backups)
- [ ] All data auto-refreshes every 2 seconds
- [ ] `psutil` is only imported inside methods, not at module level
- [ ] `ruff check`, `mypy`, and `pytest` all pass
- [ ] `_format_bytes()` duplication replaced with `common.utils.format_size`

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `psutil` not available on some systems | Analytics panel shows "not available" instead of crashing | Wrap `import psutil` in try/except in each method; fall back to stdlib-only info |
| `psutil.cpu_percent(interval=0)` returns 0.0 on first call on some platforms | CPU shows 0% briefly | Call `psutil.cpu_percent(interval=0)` once during mount to warm up the counter |
| Frequent refresh (2s) causes flicker or high CPU | Poor UX or battery drain | Textual's reactive system only updates changed values; `psutil` calls are cheap (<1ms) |
| Large ActivityLog (500 entries) parsing every 2s | Slow refresh | Cache stats in `ActivityLog.get_stats()` or debounce to every 5s for slow metrics |
