# Deferred Tasks

> Last Updated: 2026-02-17

## Deferred

| Task | Reason |
|------|--------|
| **1.1.4** Add integration tests | End-to-end workflow tests - can be added later |
| **1.2.2** Add type hints to all untyped functions | Third-party libraries (PIL, fitz, yt_dlp) lack type stubs |

### Note on Type Hints (1.2.2)

Adding `# type: ignore` everywhere would make code harder to maintain. Waiting for official type stubs or consider using pyright with suppressions.

---

## Phase 5: Advanced Features (Deferred)

> These tasks were in the original PLAN.md Phase 5 but deferred by user decision.

### 5.1 Cloud Integration

- [D] **5.1.1** Add cloud storage support (AWS S3, Google Drive, Dropbox)
- [D] **5.1.2** Add remote processing (process files on remote servers, queue system)

### 5.2 Advanced AI Features

- [D] **5.2.1** Add voice commands (speech-to-text, text-to-speech)
- [D] **5.2.2** Add smart suggestions (learn from user behavior, predictive commands)
- [D] **5.2.3** Add custom AI workflows (define custom AI pipelines, template system)

### 5.3 System Integration

- [D] **5.3.1** Add system tray support (background processing, notifications)
- [D] **5.3.2** Add desktop shortcuts (.desktop files on Linux, start menu on Windows)
- [D] **5.3.3** Add hotkey support (global keyboard shortcuts, quick access commands)

### Why Deferred

These features require significant additional dependencies and platform-specific code. They can be revisited when there's a clearer need.
