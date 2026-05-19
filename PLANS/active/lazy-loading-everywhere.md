# Plan: Lazy Loading Everywhere (Startup Time Optimization)

> Status: Completed
> Priority: P0
> Related: Architecture & System Design (Feature 3)
> Depends on: None (can be implemented independently)

## Overview

Python CLI tools suffer from slow startup times when they import heavy libraries (`PIL`, `fitz`, `yt_dlp`, `openai`, `torch`, `pandas`) at the top of files. Currently, **every single engine is imported at startup** regardless of which command the user runs. This means `max --help` takes hundreds of milliseconds (or seconds on slow machines) because it loads Pillow, PyMuPDF, yt-dlp, and OpenAI before rendering help text.

This plan moves all heavy imports to lazy-loading patterns, ensuring the CLI renders `--help` in < 50ms and only initializes engines when a specific command is actually invoked.

## Problem Analysis

### Current Import Chain at Startup

```
main.py
  └─ register(app)
       └─ commands/media.py
            ├─ cli_images.py
            │    └─ from max_cli.core.engines.image_processor import ImageEngine
            │         └─ from PIL import Image, ImageOps  ← LOADED AT STARTUP
            └─ cli_media.py
                 └─ from max_cli.core.engines.media_engine import MediaEngine
                      └─ import subprocess, shutil  ← LOADED AT STARTUP
       └─ commands/network.py
            └─ cli_network.py
                 ├─ from max_cli.core.engines.network_engine import NetworkEngine
                 │    └─ import yt_dlp  ← LOADED AT STARTUP (very heavy)
                 └─ from max_cli.core.engines.queue_manager import get_queue_manager
                      └─ from max_cli.core.engines.network_engine import NetworkEngine  ← AGAIN
       └─ commands/ai.py
            └─ cli_ai.py
                 └─ from max_cli.core.engines.ai_engine import AIEngine
                      └─ from openai import OpenAI  ← LOADED AT STARTUP
       └─ commands/audio.py
            └─ cli_audio.py
                 ├─ from max_cli.core.engines.audio_metadata_engine import AudioMetadataEngine
                 │    └─ from mutagen.mp3 import MP3  ← LOADED AT STARTUP
                 └─ from max_cli.core.engines.media_engine import MediaEngine
       └─ commands/files.py
            └─ cli_files.py
                 └─ from max_cli.core.engines.file_organizer import FileOrganizer
       └─ commands/tools.py
            └─ cli_tools.py
       └─ commands/config.py
            └─ cli_config.py
       └─ commands/plugin_commands.py
            └─ from max_cli.plugins.manager import PluginManager
```

### Heavy Import Impact

| Import | Approx. Load Time | Size |
|--------|-------------------|------|
| `yt_dlp` | 200-500ms | Very large |
| `openai` | 100-300ms | Large |
| `PIL` (Pillow) | 50-150ms | Medium |
| `fitz` (PyMuPDF) | 50-100ms | Medium |
| `mutagen` | 20-50ms | Small |
| `ffmpeg` (subprocess check) | 10-30ms | N/A |

**Total estimated startup time: 500ms - 1.5s** (depending on hardware and installed packages).

### Where the Problem Exists

1. **Engine files import heavy libs at module level**:
   - `image_processor.py` line 1: `from PIL import Image, ImageOps`
   - `pdf_engine.py` line 1: `import fitz`
   - `network_engine.py` line 1: `import yt_dlp`
   - `ai_engine.py` line 1: `from openai import OpenAI`
   - `audio_metadata_engine.py` line 1: `from mutagen.mp3 import MP3`

2. **Interface files import engines at module level**:
   - `cli_images.py` line 7: `from max_cli.core.engines.image_processor import ImageEngine`
   - `cli_pdf.py` line 7: `from max_cli.core.engines.pdf_engine import PDFEngine`
   - `cli_ai.py` line 7: `from max_cli.core.engines.ai_engine import AIEngine`
   - `cli_network.py` line 7: `from max_cli.core.engines.network_engine import NetworkEngine`

3. **Module-level engine instantiation**:
   - `cli_images.py` line 11: `engine = ImageEngine()`
   - `cli_media.py` line 12: `engine = MediaEngine()`
   - `cli_pdf.py` line 11: `engine = PDFEngine()`
   - `cli_ai.py` line 11: `engine = AIEngine()`
   - `cli_network.py` line 11: `engine = NetworkEngine()`

4. **Cross-interface imports**:
   - `cli_files.py` line 9: `from max_cli.interface.cli_ai import engine` — imports the entire `cli_ai` module (and thus `openai`) just to use AI for file renaming.

5. **Command registry imports all command modules at startup**:
   - `registry.py` calls `commands.media.register(app)` which imports `cli_images.py` and `cli_media.py` at module load time.

---

## Goals

- [ ] Reduce `max --help` startup time to < 50ms
- [ ] Move all heavy third-party imports inside functions (lazy imports)
- [ ] Remove module-level engine instantiation from interface files
- [ ] Implement lazy import proxies for engine access
- [ ] Fix cross-interface imports (`cli_files.py` → `cli_ai.py`)
- [ ] Ensure no regression in command execution time (lazy import should only affect first call)
- [ ] Add startup time benchmarks to prevent regression
- [ ] Maintain backward compatibility — all commands work exactly the same

---

## Implementation Details

### Phase 1: Lazy Import Proxy (`common/lazy.py`)

Create a lazy import utility that defers module loading until first attribute access:

```python
# src/max_cli/common/lazy.py

import importlib
import sys
from typing import Any, Optional


class LazyModule:
    """Proxy that defers module import until first attribute access.
    
    Usage:
        PIL = LazyModule("PIL")
        # Nothing imported yet
        img = PIL.Image.open("test.jpg")  # Now PIL is imported
    """

    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module: Optional[Any] = None

    def _load(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        module = self._load()
        return getattr(module, name)

    def __dir__(self) -> list[str]:
        """Support autocomplete in IDEs and dir()."""
        module = self._load()
        return dir(module)


class LazyClass:
    """Proxy that defers class import until instantiation or attribute access.
    
    Usage:
        ImageEngine = LazyClass("max_cli.core.engines.image_processor", "ImageEngine")
        engine = ImageEngine()  # Now the module is imported
    """

    def __init__(self, module_name: str, class_name: str):
        self._module_name = module_name
        self._class_name = class_name
        self._cls: Optional[Any] = None

    def _load(self) -> Any:
        if self._cls is None:
            module = importlib.import_module(self._module_name)
            self._cls = getattr(module, self._class_name)
        return self._cls

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        cls = self._load()
        return cls(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        cls = self._load()
        return getattr(cls, name)


class LazyTyperApp:
    """Proxy that defers Typer app import until the app is accessed.
    
    Used for lazy-loading CLI sub-apps in the command registry.
    
    Usage:
        lazy_app = LazyTyperApp("max_cli.interface.cli_images", "app")
        app.add_typer(lazy_app, name="images")  # Typer handles this
    """

    def __init__(self, module_name: str, app_name: str = "app"):
        self._module_name = module_name
        self._app_name = app_name
        self._app: Optional[Any] = None

    def _load(self) -> Any:
        if self._app is None:
            module = importlib.import_module(self._module_name)
            self._app = getattr(module, self._app_name)
        return self._app

    def __getattr__(self, name: str) -> Any:
        app = self._load()
        return getattr(app, name)

    # Typer needs these methods to register the app
    def _rich_help(self, *args: Any, **kwargs: Any) -> Any:
        return self._load()._rich_help(*args, **kwargs)

    def callback(self, *args: Any, **kwargs: Any) -> Any:
        return self._load().callback(*args, **kwargs)

    def command(self, *args: Any, **kwargs: Any) -> Any:
        return self._load().command(*args, **kwargs)
```

**Design decisions:**
- **`LazyModule`**: For deferring third-party library imports (PIL, yt_dlp, openai).
- **`LazyClass`**: For deferring engine class imports. Used in interface files.
- **`LazyTyperApp`**: For deferring CLI module imports in the command registry.
- **Transparent proxy**: `__getattr__` forwards all attribute access to the real module/class.
- **`__dir__` support**: Enables IDE autocomplete after the module is loaded.

---

### Phase 2: Refactor Engine Files (Lazy Third-Party Imports)

Move heavy imports inside methods:

#### `image_processor.py`

```python
# Before:
from PIL import Image, ImageOps

class ImageEngine:
    def compress_image(self, input_path, output_path, quality=85):
        img = Image.open(input_path)
        img.save(output_path, quality=quality)

# After:
from typing import Any, Dict
from pathlib import Path


class ImageEngine:
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}

    def compress_image(
        self, input_path: Path, output_path: Path, quality: int = 85
    ) -> Dict[str, Any]:
        from PIL import Image, ImageOps  # ← Imported only when called

        img = Image.open(input_path)
        original_size = input_path.stat().st_size
        img.save(output_path, quality=quality, optimize=True)
        compressed_size = output_path.stat().st_size

        return {
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_pct": ((original_size - compressed_size) / original_size) * 100,
        }
```

#### `pdf_engine.py`

```python
# Before:
import fitz

class PDFEngine:
    def merge_pdfs(self, input_paths, output_path):
        result = fitz.open()
        for path in input_paths:
            doc = fitz.open(path)
            result.insert_pdf(doc)
        result.save(output_path)

# After:
class PDFEngine:
    def merge_pdfs(self, input_paths, output_path):
        import fitz  # ← Imported only when called

        result = fitz.open()
        for path in input_paths:
            doc = fitz.open(path)
            result.insert_pdf(doc)
        result.save(output_path)
```

#### `network_engine.py`

```python
# Before:
import yt_dlp

class NetworkEngine:
    def download_media(self, url, output_path, ...):
        ydl_opts = {...}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

# After:
class NetworkEngine:
    def download_media(self, url, output_path, ...):
        import yt_dlp  # ← Imported only when called

        ydl_opts = {...}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
```

#### `ai_engine.py`

```python
# Before:
from openai import OpenAI
import typer

class AIEngine:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

# After:
class AIEngine:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # ← Imported only when first accessed
            from max_cli.config import settings
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client
```

#### `audio_metadata_engine.py`

```python
# Before:
from mutagen.mp3 import MP3
from mutagen.id3 import ID3

class AudioMetadataEngine:
    def get_metadata(self, file_path):
        audio = MP3(file_path)
        return audio.tags

# After:
class AudioMetadataEngine:
    def get_metadata(self, file_path):
        from mutagen.mp3 import MP3  # ← Imported only when called
        audio = MP3(file_path)
        return audio.tags
```

**Files to refactor:**
1. `core/engines/image_processor.py` — `from PIL import ...`
2. `core/engines/pdf_engine.py` — `import fitz`
3. `core/engines/network_engine.py` — `import yt_dlp`
4. `core/engines/ai_engine.py` — `from openai import OpenAI`, `import typer`
5. `core/engines/audio_metadata_engine.py` — `from mutagen...`
6. `core/engines/media_engine.py` — `import subprocess` (lightweight, but still)

---

### Phase 3: Refactor Interface Files (Lazy Engine Access)

Remove module-level engine instantiation and use lazy proxies:

#### `cli_images.py`

```python
# Before:
import typer
from max_cli.core.engines.image_processor import ImageEngine
from max_cli.common.logger import console

app = typer.Typer()
engine = ImageEngine()  # ← Instantiated at module import time

@app.command("compress")
def compress_images(...):
    engine.compress_image(...)

# After:
import typer
from max_cli.common.lazy import LazyClass
from max_cli.common.logger import console

app = typer.Typer()

# Lazy — ImageEngine is not imported or instantiated until first use
ImageEngineProxy = LazyClass(
    "max_cli.core.engines.image_processor", "ImageEngine"
)


@app.command("compress")
def compress_images(...):
    engine = ImageEngineProxy()  # ← Only now is the module imported
    engine.compress_image(...)
```

**Alternative approach — lazy instantiation inside a function:**

```python
# Even simpler — no proxy needed:
import typer
from max_cli.common.logger import console

app = typer.Typer()


def _get_engine():
    from max_cli.core.engines.image_processor import ImageEngine
    return ImageEngine()


@app.command("compress")
def compress_images(...):
    engine = _get_engine()
    engine.compress_image(...)
```

**Design decision**: The `_get_engine()` function approach is simpler, more readable, and doesn't require a new `LazyClass` utility. It's the recommended approach for interface files. The `LazyClass` proxy is useful for the command registry (Phase 4).

---

### Phase 4: Refactor Command Registry (Lazy App Loading)

The command registry currently imports all CLI modules at startup:

```python
# Current registry.py:
def register(app: "Typer") -> None:
    commands.media.register(app)    # Imports cli_images.py, cli_media.py
    commands.files.register(app)    # Imports cli_files.py
    commands.network.register(app)  # Imports cli_network.py
    commands.ai.register(app)       # Imports cli_ai.py
    commands.tools.register(app)    # Imports cli_tools.py
    commands.config.register(app)   # Imports cli_config.py
    commands.plugin_commands.register(app)
    commands.audio.register(app)    # Imports cli_audio.py
```

#### Option A: Lazy Typer App Registration

Typer supports lazy app registration via `add_typer()` with a proxy:

```python
# Refactored registry.py:
from max_cli.common.lazy import LazyTyperApp


def register(app: "Typer") -> None:
    """Register all CLI commands with lazy loading."""

    # Images — lightweight (Pillow), register eagerly
    from max_cli.interface import cli_images
    app.add_typer(cli_images.app, name="images", help="Image processing")

    # Tools — lightweight (stdlib), register eagerly
    from max_cli.interface import cli_tools
    app.add_typer(cli_tools.app, name="tools", help="Utilities")

    # Config — lightweight (stdlib), register eagerly
    from max_cli.interface import cli_config
    app.add_typer(cli_config.app, name="config", help="Configuration")

    # Plugin management — lightweight (stdlib), register eagerly
    from max_cli.interface import cli_plugin_commands
    app.add_typer(cli_plugin_commands.app, name="plugins", help="Plugins")

    # Heavy apps — lazy load
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_media", "app"),
        name="video",
        help="Video processing (FFmpeg)",
    )
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_pdf", "app"),
        name="pdf",
        help="PDF manipulation (PyMuPDF)",
    )
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_network", "app"),
        name="grab",
        help="Download media (yt-dlp)",
    )
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_ai", "app"),
        name="ai",
        help="AI-powered commands",
    )
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_files", "app"),
        name="files",
        help="File operations",
    )
    app.add_typer(
        LazyTyperApp("max_cli.interface.cli_audio", "app"),
        name="audio",
        help="Audio metadata",
    )
```

**Problem**: Typer's `add_typer()` expects a real `Typer` instance, not a proxy. The proxy approach may not work cleanly with Typer's internal inspection.

#### Option B: Typer's Built-in `rich_help_panel` + Callback Lazy Loading (Recommended)

Use Typer's callback mechanism to lazy-load:

```python
# Refactored registry.py — recommended approach:
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer


def register(app: "Typer") -> None:
    """Register all CLI commands with lazy loading."""

    # Lightweight apps — register eagerly
    from max_cli.interface import cli_images, cli_tools, cli_config
    from max_cli.interface import cli_plugin_commands

    app.add_typer(cli_images.app, name="images", help="Image processing")
    app.add_typer(cli_tools.app, name="tools", help="Utilities")
    app.add_typer(cli_config.app, name="config", help="Configuration")
    app.add_typer(cli_plugin_commands.app, name="plugins", help="Plugins")

    # Heavy apps — register via lazy sub-apps
    _register_lazy_app(app, "video", "Video processing (FFmpeg)")
    _register_lazy_app(app, "pdf", "PDF manipulation (PyMuPDF)")
    _register_lazy_app(app, "grab", "Download media (yt-dlp)")
    _register_lazy_app(app, "ai", "AI-powered commands")
    _register_lazy_app(app, "files", "File operations")
    _register_lazy_app(app, "audio", "Audio metadata")


def _register_lazy_app(app: "Typer", name: str, help_text: str) -> None:
    """Register a Typer sub-app that lazy-loads its module on first access."""
    import typer

    lazy_app = typer.Typer(help=help_text)

    @lazy_app.callback(invoke_without_command=True)
    def _lazy_load(ctx: typer.Context):
        """Lazy-load the actual CLI module when any command is invoked."""
        module = __import__(
            f"max_cli.interface.cli_{name}",
            fromlist=["app"],
        )
        # Replace this lazy app's commands with the real ones
        ctx.typer_instance.add_typer(module.app, name=name, help=help_text)

    app.add_typer(lazy_app, name=name, help=help_text)
```

**Problem**: This approach has issues with Typer's command routing. The lazy app won't have the real commands until the callback fires, which is too late.

#### Option C: Dynamic Import in Command Callbacks (Simplest & Most Reliable)

The most reliable approach is to keep `add_typer()` but make the CLI modules themselves lazy:

```python
# registry.py — keep it simple:
def register(app: "Typer") -> None:
    """Register all CLI commands."""
    # All imports are now lazy (Phase 2 + 3 changes)
    # The modules import fast because engines use lazy imports
    from max_cli.interface import (
        cli_images,
        cli_media,
        cli_pdf,
        cli_network,
        cli_ai,
        cli_files,
        cli_tools,
        cli_config,
        cli_audio,
        cli_plugin_commands,
    )

    app.add_typer(cli_images.app, name="images", help="Image processing")
    app.add_typer(cli_media.app, name="video", help="Video processing (FFmpeg)")
    app.add_typer(cli_pdf.app, name="pdf", help="PDF manipulation (PyMuPDF)")
    app.add_typer(cli_network.app, name="grab", help="Download media (yt-dlp)")
    app.add_typer(cli_ai.app, name="ai", help="AI-powered commands")
    app.add_typer(cli_files.app, name="files", help="File operations")
    app.add_typer(cli_tools.app, name="tools", help="Utilities")
    app.add_typer(cli_config.app, name="config", help="Configuration")
    app.add_typer(cli_audio.app, name="audio", help="Audio metadata")
    app.add_typer(cli_plugin_commands.app, name="plugins", help="Plugins")
```

**Why this works**: After Phase 2 and Phase 3, importing `cli_images.py` is fast because:
1. It no longer imports `ImageEngine` at module level (uses `_get_engine()` function).
2. `ImageEngine` no longer imports `PIL` at module level (imports inside methods).
3. The module only contains lightweight imports: `typer`, `pathlib`, `typing`, `rich.progress`.

**This is the recommended approach.** It's the simplest, most reliable, and doesn't require complex proxy patterns.

---

### Phase 5: Fix Cross-Interface Imports

#### `cli_files.py` → `cli_ai.py`

Currently, `cli_files.py` imports the AI engine from `cli_ai.py`:

```python
# Before (cli_files.py line 9):
from max_cli.interface.cli_ai import engine  # Imports entire cli_ai module + openai!

# After:
def _get_ai_engine():
    from max_cli.core.engines.ai_engine import AIEngine
    return AIEngine()
```

Then in the smart-sort or rename command:

```python
@app.command("smart-sort")
def smart_sort_files(...):
    if use_ai:
        engine = _get_ai_engine()  # ← Only imports openai when AI is actually needed
        # ... use engine ...
```

---

### Phase 6: Fix QueueManager Lazy Loading

`QueueManager` imports `NetworkEngine` at module level:

```python
# Before (queue_manager.py):
from max_cli.core.engines.network_engine import NetworkEngine

class QueueManager:
    def __init__(self):
        self._engine = NetworkEngine()  # ← Imports yt_dlp at init time

# After:
class QueueManager:
    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from max_cli.core.engines.network_engine import NetworkEngine
            self._engine = NetworkEngine()
        return self._engine
```

---

### Phase 7: Add Startup Time Benchmark

Create a simple benchmark to measure and prevent startup regression:

```python
# tests/test_startup_time.py

import subprocess
import sys
import time


def test_help_startup_time():
    """Ensure 'max --help' starts in under 100ms."""
    start = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "max_cli", "--help"],
        capture_output=True, text=True,
        timeout=10,
    )
    elapsed = time.time() - start

    assert result.returncode == 0, f"max --help failed: {result.stderr}"
    assert elapsed < 0.1, f"Startup took {elapsed:.3f}s (target: <0.1s)"


def test_no_heavy_imports_at_startup():
    """Verify heavy modules are not imported during 'max --help'."""
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
sys.modules_before = set(sys.modules.keys())

# Simulate what main.py does
from max_cli.core.cli.registry import register
import typer
app = typer.Typer()
register(app)

# Check what was imported
heavy = {'yt_dlp', 'openai', 'PIL', 'fitz', 'mutagen', 'torch', 'pandas'}
imported_heavy = heavy & set(sys.modules.keys())
if imported_heavy:
    print(f"HEAVY IMPORTS: {imported_heavy}")
    sys.exit(1)
"""],
        capture_output=True, text=True,
        timeout=10,
    )

    assert result.returncode == 0, (
        f"Heavy modules imported at startup:\n{result.stdout}\n{result.stderr}"
    )
```

---

## Migration Path

1. **Step 1**: Add `common/lazy.py` utility (optional, for advanced lazy loading).
2. **Step 2**: Refactor `image_processor.py` — move `PIL` imports inside methods.
3. **Step 3**: Refactor `pdf_engine.py` — move `fitz` imports inside methods.
4. **Step 4**: Refactor `network_engine.py` — move `yt_dlp` imports inside methods.
5. **Step 5**: Refactor `ai_engine.py` — move `openai` imports inside `__init__` or lazy property.
6. **Step 6**: Refactor `audio_metadata_engine.py` — move `mutagen` imports inside methods.
7. **Step 7**: Refactor all interface files — remove module-level engine instantiation, use `_get_engine()` pattern.
8. **Step 8**: Fix `cli_files.py` cross-interface import.
9. **Step 9**: Fix `QueueManager` lazy loading.
10. **Step 10**: Add startup time benchmark tests.
11. **Step 11**: Measure and verify startup time improvement.
12. **Step 12**: Run full test suite to verify no regressions.

---

## Expected Impact

### Before (Current)
```
$ time max --help
real    0m0.850s
user    0m0.620s
sys     0m0.180s
```

### After (Target)
```
$ time max --help
real    0m0.045s
user    0m0.035s
sys     0m0.010s
```

**~20x faster startup.**

### Command Execution (First Call)
```
$ time max images compress test.jpg
# First call: +50-150ms for PIL import (one-time cost)
# Subsequent calls: no additional overhead
```

The one-time import cost is negligible compared to actual processing time (compressing an image takes seconds, not milliseconds).

---

## Testing Strategy

### Startup Time Tests

```python
# tests/test_startup_time.py (see Phase 7 above)
```

### Functional Tests (No Changes Needed)

All existing tests should pass without modification because:
- Commands still work the same way.
- Engines still return the same data.
- Only the timing of imports has changed.

### Edge Case Tests

```python
# tests/test_lazy_imports.py

def test_engine_lazy_import_on_first_use():
    """Engine should not import heavy libs until a method is called."""
    from max_cli.core.engines.image_processor import ImageEngine
    import sys

    # Engine class exists but PIL is not imported
    assert "PIL" not in sys.modules

    engine = ImageEngine()
    # Still not imported (no method called)
    assert "PIL" not in sys.modules

    # Call a method — now PIL is imported
    # (Need a real file for this test, so use a mock)
    # engine.compress_image(...)
    # assert "PIL" in sys.modules


def test_ai_engine_lazy_client():
    """AIEngine should not create OpenAI client until first API call."""
    from max_cli.core.engines.ai_engine import AIEngine

    engine = AIEngine()
    # Client should be None until first access
    assert engine._client is None

    # Access client — now openai is imported
    # client = engine.client
    # assert client is not None
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| First command call is slower (import cost) | Acceptable trade-off. Import cost is < 200ms vs. 800ms+ startup savings. |
| Import errors surface at runtime instead of startup | Add `try/except ImportError` in lazy import functions with friendly error messages. |
| IDE autocomplete breaks for lazy imports | IDEs analyze static code. Lazy imports inside functions are still analyzable. `LazyModule` with `__dir__` helps. |
| Circular imports from lazy loading | Lazy imports actually *reduce* circular import risk because imports happen at call time, not module load time. |
| `typer` inspection fails for lazy apps | Option C (simple module imports with lazy engines) avoids this entirely. |
| Type checker complains about lazy imports | Type checkers analyze static code. Runtime imports are invisible to them. Add `# type: ignore` only if needed. |

---

## Success Criteria

- [ ] `max --help` starts in < 100ms (measured with `time` command)
- [ ] `yt_dlp`, `openai`, `PIL`, `fitz`, `mutagen` are NOT in `sys.modules` after `register(app)`
- [ ] All existing tests pass without modification
- [ ] `max images compress test.jpg` works correctly (PIL imported at call time)
- [ ] `max ai ask "hello"` works correctly (openai imported at call time)
- [ ] `max grab download <url>` works correctly (yt_dlp imported at call time)
- [ ] Startup time benchmark test passes in CI
- [ ] No `ImportError` at runtime for any command
