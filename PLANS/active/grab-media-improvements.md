# Plan: Grab Media Improvements

> Status: Draft
> Priority: P0

## Overview

Major improvements to the grab media feature for better UX, flexibility, and automation.

## Code Quality Requirement

**MUST use existing utilities from `max_cli.common`:**
- `retry` decorator from `common/retry.py` - for retry logic
- `console`, `log_success`, `log_error` from `common/logger.py` - for output
- Custom exceptions from `common/exceptions.py` - for error handling
- `format_size` from `common/utils.py` - for human-readable sizes

This keeps code clean, consistent, and professional.

## Current State

- `max grab <url>` requires URL as argument with quotes
- Downloads to current directory by default
- No queue system - waits for each download to finish
- Basic progress display

## Goals

- [ ] **G1** Add default download path config (e.g., "Max Downloads" in home)
- [ ] **G2** Add default download type (video/audio) config
- [ ] **G3** Add `-v` flag to force video download
- [ ] **G4** Make URL optional - interactive mode prompts for URL
- [ ] **G5** URL input without quotes (handle spaces automatically)
- [ ] **G6** Queue system - add URLs to queue, process in background
- [ ] **G7** Better progress display - show all downloads in a table
- [ ] **G8** Persist queue info to disk (resume after restart)

---

## Implementation Notes

### Configuration Additions (config.py)

```python
# New settings to add:
GRAB_DEFAULT_PATH: Path = Path.home() / "Max Downloads"
GRAB_DEFAULT_TYPE: str = "video"  # "video" or "audio"
GRAB_QUEUE_ENABLED: bool = True
```

### New CLI Behavior

```bash
# Interactive mode - prompts for URL
max grab

# With URL (no quotes needed)
max grab https://youtube.com/watch?v=...

# Force video (overrides audio default)
max grab -v https://...

# Force audio
max grab -a https://...

# Check queue status
max grab queue

# Clear queue
max grab clear

# Queue continues in background after adding URLs
```

### Queue System Design

1. **Queue Manager** - Background thread/process that processes downloads
2. **Persistent Queue** - JSON file storing pending downloads
3. **Rich Table Display** - Show all downloads with status:
   - Status: pending, downloading, completed, failed
   - URL, title, progress, speed, ETA

### Architecture Changes

```
src/max_cli/
├── core/
│   ├── network_engine.py    # Existing - keep as is
│   └── queue_manager.py    # NEW - handles queue processing
├── interface/
│   ├── cli_network.py      # Modify - add interactive + queue
│   └── cli_config.py       # Modify - add new config options
└── config.py               # Modify - add new settings
```

---

## Detailed Tasks

> **Important:** Use `max_cli.common` utilities throughout (retry, logger, exceptions, utils)

### T1: Add Config Settings
- [ ] Add `GRAB_DEFAULT_PATH` to config.py
- [ ] Add `GRAB_DEFAULT_TYPE` to config.py  
- [ ] Update `max config grab` wizard to include these

### T2: Interactive Mode & URL Handling
- [ ] Make URL argument optional in CLI
- [ ] If no URL provided, prompt for input
- [ ] Remove need for quotes - use `shlex.split()` or custom parsing
- [ ] Add `-v` flag for video override

### T3: Queue System Core
- [ ] Create `QueueManager` class in queue_manager.py
- [ ] Add queue persistence (JSON file)
- [ ] Implement background processing thread
- [ ] Add queue CLI commands: `queue`, `clear`, `status`

### T4: Enhanced Progress Display
- [ ] Replace single progress bar with table view
- [ ] Show: URL, Title, Status, Progress %, Speed, ETA
- [ ] Real-time updates for all active downloads
- [ ] Color-coded status (green=complete, yellow=downloading, red=failed)

### T5: Integration
- [ ] Connect queue manager to CLI
- [ ] Test queue persistence
- [ ] Test background processing

---

## Suggested Improvements (Bonus)

1. **Batch URL input** - Allow pasting multiple URLs (one per line)
2. **Retry failed downloads** - Auto-retry with exponential backoff
3. **Download history** - Keep log of all past downloads
4. **Thumbnail preview** - Show video thumbnail in queue
5. **Notifications** - Desktop notification on completion
