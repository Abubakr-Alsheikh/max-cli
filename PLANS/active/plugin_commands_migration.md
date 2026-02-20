# Plan: Convert CLI Commands to Optional Plugins

## Overview

This plan outlines which CLI commands should be moved from built-in to optional plugins, allowing users to install only the features they need.

## Current Command Groups

| Group | Commands | Dependencies |
|-------|----------|--------------|
| `images` | compress, resize, convert, strip | Pillow |
| `video` | compress, convert, to-audio, gif, cut, snap, louder, mute, concat, brightness, color, stabilize, normalize, audio-convert, record, stream, preview | FFmpeg |
| `files` | order, smart-sort, duplicates, shred, preview, backup, backups, backup-cleanup | Standard library |
| `pdf` | merge, compress, bundle, split, stamp, lock, rip, ocr, form-data, form-fill, form-flatten, optimize, compare | PyMuPDF |
| `net`/`grab` | download, queue, clear, status, history | yt-dlp |
| `ai` | ask, analyze, create, edit, chat, search, extract | OpenAI API |
| `tools` | share, paste, copy | Standard library |
| `config` | setup, grab, show, save, reset, validate, export, import | Standard library |
| `plugins` | list, info, enable, disable | Standard library |

---

## Classification

### CORE (Stay Built-in)

| Command Group | Reason |
|---------------|--------|
| `config` | Required for setup and API key management |
| `plugins` | Required for plugin management |
| `images` | Core image processing - fundamental to CLI identity |
| `tools` | Lightweight utilities, no heavy dependencies |

### OPTIONAL (Move to Plugins)

| Priority | Command Group | Dependencies | Justification |
|----------|---------------|--------------|---------------|
| **High** | `ai` | OpenAI API | Requires API key; not all users need AI |
| **High** | `video` | FFmpeg | Heavy external dependency; not all users process video |
| **High** | `net`/`grab` | yt-dlp | Heavy dependency; not all users download media |
| **Medium** | `pdf` | PyMuPDF | Heavy dependency; not all users process PDFs |
| **Medium** | `files` (advanced) | Standard library | `smart-sort`, `duplicates`, `shred`, `backup` are advanced features |

---

## Migration Strategy

### Phase 1: Create Plugin Templates

Create base plugin templates for each optional command group:

```
plugins/
├── max-ai/           # AI commands plugin
│   ├── __init__.py
│   ├── plugin.py
│   └── pyproject.toml
├── max-video/        # Video processing plugin
│   ├── __init__.py
│   ├── plugin.py
│   └── pyproject.toml
├── max-media/        # Network download plugin
│   ├── __init__.py
│   ├── plugin.py
│   └── pyproject.toml
├── max-pdf/          # PDF processing plugin
│   ├── __init__.py
│   ├── plugin.py
│   └── pyproject.toml
└── max-advanced-files/ # Advanced file tools plugin
    ├── __init__.py
    ├── plugin.py
    └── pyproject.toml
```

### Phase 2: Implement Plugin Structure

Each plugin should:

1. **Extend `CLIPlugin`** base class
2. **Validate dependencies** in `validate()` method
3. **Lazy-load engines** to avoid import errors if dependencies missing
4. **Provide clear error messages** when dependencies missing
5. **Support auto-discovery** via plugin manager

Example structure:

```python
# max-ai/plugin.py
class AIPlugin(CLIPlugin):
    name = "max-ai"
    version = "1.0.0"
    description = "AI-powered commands (ask, analyze, create, edit, chat, search, extract)"
    author = "Max CLI Team"
    dependencies = ["openai"]

    def validate(self) -> tuple[bool, Optional[str]]:
        try:
            from max_cli.core.engines.ai_engine import AIEngine
            return True, None
        except ImportError:
            return False, "OpenAI package not installed. Run: pip install max-cli[ai]"

    def register(self, app: Typer) -> None:
        from max_cli.interface import cli_ai
        app.add_typer(cli_ai.app, name="ai", help="AI-powered commands")
```

### Phase 3: Update Package Installation

Update `pyproject.toml` to support optional extras:

```toml
[project.optional-dependencies]
ai = ["openai", "pillow"]
video = ["ffmpeg-python"]
media = ["yt-dlp"]
pdf = ["pymupdf"]
all = ["openai", "ffmpeg-python", "yt-dlp", "pymupdf"]
```

### Phase 4: Handle Existing Users

- Detect if dependencies exist and auto-load plugins
- Show friendly message when plugin command used but not installed
- Keep backward compatibility during transition period

---

## Implementation Order

| Step | Task | Status |
|------|------|--------|
| 1 | Create `max-ai` plugin structure | [ ] |
| 2 | Create `max-video` plugin structure | [ ] |
| 3 | Create `max-media` (net/grab) plugin structure | [ ] |
| 4 | Create `max-pdf` plugin structure | [ ] |
| 5 | Create `max-advanced-files` plugin structure | [ ] |
| 6 | Update pyproject.toml with optional deps | [ ] |
| 7 | Test plugin auto-discovery | [ ] |
| 8 | Add migration guide to documentation | [ ] |

---

## Benefits

1. **Lighter core**: Base installation only includes essential features
2. **User choice**: Install only what you need
3. **Faster installs**: No unnecessary heavy dependencies
4. **Easier updates**: Update plugins independently
5. **Community plugins**: Third-party developers can add features

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing users | Keep commands working during transition; add deprecation warnings |
| Plugin discovery issues | Test thoroughly; provide clear error messages |
| Dependency conflicts | Use optional dependencies in pyproject.toml |
