# Max CLI - Improvement Plan

> **Status**: Planning  
> **Version**: 0.1.0 → 1.0.0 (Major Upgrade)  
> **Last Updated**: 2026-02-16

---

## About This Plan

This plan is the **single source of truth** for all project improvements. It serves as the task list for AI agents working on this codebase.

### Key Directories

- **`PLAN.md`** - This file, containing all improvement tasks
- **`tasks/implementation/`** - Implementation guides for complex tasks
- **`tasks/`** - Contains task-specific notes and progress tracking

### Task ID Format

Tasks use the format: `TASK-XXX` (e.g., `TASK-001`, `TASK-002`)

### How Tasks Are Tracked

1. Tasks start as `[ ]` (pending)
2. When an agent starts working, it updates to `[~]` (in progress)
3. When complete, it becomes `[x]` (completed)
4. Complex tasks may be marked `[D]` (deferred) or `[S]` (skipped)

---

## Completed Tasks

- [x] **TASK-001** Create comprehensive improvement plan (PLAN.md)
- [x] **TASK-002** Update AGENTS.md with continuous improvement system

---

## Phase 1 Progress (Completed: 2026-02-14)

### 1.1 Testing Infrastructure ✅

- [x] **1.1.1** Add pytest fixtures for common test scenarios
- [x] **1.1.2** Expand test coverage for existing engines  
- [x] **1.1.3** Add CLI interface tests

### 1.2 Type Safety & Linting ✅

- [x] **1.2.1** Create mypy.ini configuration
- [x] **1.2.3** Enhance ruff configuration
- [x] **1.2.4** Add pre-commit hooks
- [ ] **1.2.2** Add type hints to all untyped functions [DEFERRED - Third-party libraries lack type stubs]

### 1.3 Error Handling & Logging ✅

- [x] **1.3.1** Expand exception hierarchy
- [x] **1.3.2** Add logging module
- [x] **1.3.3** Add retry logic for network operations

**Note**: Full mypy strict mode is not feasible due to third-party libraries (PIL, fitz, yt_dlp, etc.) lacking proper type stubs. Basic mypy.ini is in place for future type improvements when stubs become available.

---

## Phase 2 Progress (Completed: 2026-02-14)

### 2.1 Parallel Processing ✅

- [x] **2.1.1** Add concurrent processing utilities
  - Created `src/max_cli/common/concurrent.py` with `process_batch_parallel()` and `process_batch_sequential()` functions

- [x] **2.1.2** Update batch operations to use parallel processing
  - Updated `cli_images.py` with `--workers` flag for all image commands (compress, resize, convert, strip)
  - Added parallel processing support with configurable workers

### 2.2 Configuration System Enhancement ✅

- [x] **2.2.1** Enhance Settings class
  - Added `MAX_WORKERS`, `BATCH_SIZE`, `DOWNLOAD_TIMEOUT`, `MAX_RETRIES`, `PROGRESS_BAR`, `VERBOSE`, `CONFIRM_DESTRUCTIVE`
  - Used pydantic Field for validation (ge, le constraints)

- [x] **2.2.2** Add configuration commands
  - `max config reset` - Reset global/local config to defaults
  - `max config validate` - Validate current configuration
  - `max config export` - Export config to JSON file
  - `max config import` - Import config from JSON file

### 2.3 Caching System ✅

- [x] **2.3.1** Add caching utilities
  - Created `src/max_cli/common/cache.py` with `Cache` class supporting TTL
  - Added `cached()` decorator for function result caching

- [x] **2.3.2** Implement caching for operations
  - Added caching to `AIEngine.categorize_files()` with 1-hour TTL

---

## Phase 4 Progress (Completed: 2026-02-16)

### 4.1 Documentation ✅

- [x] **4.1.1** Create CONTRIBUTING.md
- [x] **4.1.2** Create API documentation (Sphinx)
- [x] **4.1.3** Add inline documentation improvements

### 4.2 CI/CD Pipeline ✅

- [x] **4.2.1** Enhance GitHub Actions (multi-OS, coverage, type check)
- [x] **4.2.2** Add automated release workflow

### 4.3 Plugin System ✅

- [x] **4.3.1** Create plugin interface
- [x] **4.3.2** Add plugin discovery
- [x] **4.3.3** Create example plugin

---

## Executive Summary

This document outlines a comprehensive improvement plan for max-cli, transforming it from a solid utility into a production-grade, professional CLI framework. The plan addresses technical debt, adds significant features, improves code quality, and establishes proper development workflows.

---

## Phase 1: Foundation & Code Quality (Weeks 1-2)

### 1.1 Testing Infrastructure

**Current State**: Only 2 tests exist (test_core_images.py)  
**Target**: Comprehensive test coverage (>80%)

#### Actions

- [x] **1.1.1** Add pytest fixtures for common test scenarios
  - Create `tests/conftest.py` with shared fixtures
  - Fixtures: dummy_image, dummy_pdf, dummy_video, temp_directory
  
- [x] **1.1.2** Expand test coverage for existing engines
  - `tests/test_core_pdf.py` - PDF engine tests (merge, split, compress, watermark, password)
  - `tests/test_core_media.py` - Media engine tests (mock FFmpeg calls)
  - `tests/test_core_network.py` - Network download tests
  - `tests/test_core_ai.py` - AI engine tests (mock OpenAI calls)
  - `tests/test_core_file_organizer.py` - File organization tests
  
- [x] **1.1.3** Add CLI interface tests
  - `tests/test_cli_images.py` - CLI argument parsing and validation
  
- [ ] **1.1.4** Add integration tests
  - End-to-end workflow tests
  - Batch processing tests

#### Testing Tools to Add

```toml
# pyproject.toml additions
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/.venv/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

---

### 1.2 Type Safety & Linting

**Current State**: Basic ruff configuration, no mypy config  
**Target**: Full type safety with mypy (deferred due to third-party stubs)

#### Actions

- [x] **1.2.1** Create `mypy.ini` configuration

```ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_incomplete_defs = True
check_untyped_defs = True
disallow_untyped_decorators = True
no_implicit_optional = True
warn_redundant_casts = True
warn_unused_ignores = True
warn_no_return = True
warn_unreachable = True
strict_equality = True

[mypy-tests.*]
ignore_errors = True

[mypy-PIL.*]
ignore_missing_imports = True

[mypy-yt_dlp.*]
ignore_missing_imports = True

[mypy-pymupdf.*]
ignore_missing_imports = True
```

- [ ] **1.2.2** Add type hints to all untyped functions
  - Add return types to all engine methods
  - Add parameter types to all CLI commands
  - Fix existing type issues in:
    - `core/image_processor.py` - Add proper Dict returns
    - `core/media_engine.py` - Add Optional[] for optional params
    - `core/ai_engine.py` - Fix Any types
  - **Status**: DEFERRED - Third-party libraries lack type stubs

- [x] **1.2.3** Enhance ruff configuration

```toml
[tool.ruff]
line-length = 88
target-version = "py39"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
]
ignore = [
    "E501",   # line too long (handled by formatter)
    "B008",   # do not perform function call in argument defaults
]

[tool.ruff.lint.isort]
known-first-party = ["max_cli"]
```

- [x] **1.2.4** Add pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
        
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        args: [--config-file=mypy.ini]
```

---

### 1.3 Error Handling & Logging

**Current State**: Basic error handling with custom exceptions  
**Target**: Comprehensive error handling with logging

#### Actions

- [x] **1.3.1** Expand exception hierarchy

```python
# src/max_cli/common/exceptions.py additions
class ConfigurationError(MaxError):
    """Raised when configuration is invalid or missing."""
    pass

class ProcessingError(MaxError):
    """Raised when file processing fails."""
    pass

class NetworkError(MaxError):
    """Raised when network operations fail."""
    pass

class AIError(MaxError):
    """Raised when AI operations fail."""
    pass
```

- [x] **1.3.2** Add logging module

```python
# src/max_cli/common/logging.py
import logging
from pathlib import Path

def setup_logging(log_level: str = "INFO", log_file: Path = None):
    """Configure logging for the application."""
    format_str = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=format_str,
        handlers=handlers
    )
```

- [x] **1.3.3** Add retry logic for network operations

```python
# src/max_cli/common/retry.py
from functools import wraps
import time

def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retrying failed operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        raise
                    logging.warning(f"Attempt {attempt} failed: {e}. Retrying...")
                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1
        return wrapper
    return decorator
```

---

## Phase 2: Performance & Architecture (Weeks 3-4)

### 2.1 Parallel Processing

**Current State**: Sequential batch processing  
**Target**: Parallel processing with progress tracking

#### Actions

- [x] **2.1.1** Add concurrent processing utilities

```python
# src/max_cli/common/concurrent.py
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Any, Dict
from rich.progress import Progress, TaskID

def process_batch_parallel(
    items: List[Any],
    processor: Callable,
    max_workers: int = 4,
    progress: Progress = None,
    task_id: TaskID = None
) -> List[Dict]:
    """Process items in parallel with optional progress tracking."""
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(processor, item): item for item in items}
        
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "item": item})
            
            if progress and task_id:
                progress.advance(task_id)
    
    return results
```

- [x] **2.1.2** Update batch operations to use parallel processing
  - `cli_images.py` - Parallel image compression
  - `cli_pdf.py` - Parallel PDF compression
  - Add `--workers` flag to control parallelism

---

### 2.2 Configuration System Enhancement

**Current State**: Basic pydantic-settings  
**Target**: Full-featured configuration with validation

#### Actions

- [x] **2.2.1** Enhance Settings class

```python
# src/max_cli/config.py additions
from pydantic import Field, validator
from typing import Literal

class Settings(BaseSettings):
    # ... existing fields ...
    
    # Performance settings
    MAX_WORKERS: int = Field(default=4, ge=1, le=16)
    BATCH_SIZE: int = Field(default=10, ge=1)
    
    # Network settings
    DOWNLOAD_TIMEOUT: int = Field(default=300, ge=30)
    MAX_RETRIES: int = Field(default=3, ge=0)
    
    # UI settings
    PROGRESS_BAR: bool = True
    VERBOSE: bool = False
    
    # Security
    CONFIRM_DESTRUCTIVE: bool = True
    
    @validator("AI_MODEL", "AI_IMAGE_MODEL")
    def validate_model_names(cls, v):
        # Add model validation logic
        return v
    
    class Config:
        env_file = [str(Path.home() / ".max_config.env"), ".env"]
        env_file_encoding = "utf-8"
        case_sensitive = True
```

- [x] **2.2.2** Add configuration commands
  - `max config reset` - Reset to defaults
  - `max config validate` - Validate current config
  - `max config export` - Export config to file
  - `max config import` - Import config from file

---

### 2.3 Caching System

**Current State**: No caching  
**Target**: Intelligent caching for repeated operations

#### Actions

- [x] **2.3.1** Add caching utilities

```python
# src/max_cli/common/cache.py
import hashlib
import json
from pathlib import Path
from functools import lru_cache

class Cache:
    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path.home() / ".max_cli" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str) -> Any:
        cache_file = self.cache_dir / f"{self._hash(key)}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None
    
    def set(self, key: str, value: Any):
        cache_file = self.cache_dir / f"{self._hash(key)}.json"
        with open(cache_file, 'w') as f:
            json.dump(value, f)
    
    def _hash(self, key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()
    
    def clear(self):
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
```

- [x] **2.3.2** Implement caching for:
  - AI intent interpretation (context-aware)
  - File categorization results
  - Video thumbnail generation
  - YouTube metadata (with TTL)

---

## Phase 3: Feature Enhancements (Weeks 5-6)

### 3.1 Media Processing Enhancements

**Current State**: Basic video operations  
**Target**: Professional-grade media toolkit

#### Actions

- [x] **3.1.1** Add video concatenation
  - Added `concatenate_videos()` method to MediaEngine with two methods: concat demuxer (fast) and filter (safe/re-encode)
  - Added `max media concat` command supporting glob patterns (e.g., `*.mp4`) or text file input

```python
def concatenate_videos(self, input_paths: List[Path], output_path: Path) -> None:
    """Merge multiple video files into one."""
    # Implementation using FFmpeg concat demuxer
```

- [x] **3.1.2** Add video filters
  - Added `adjust_brightness()` for brightness/contrast adjustment
  - Added `apply_color_preset()` with presets: vivid, vintage, noir, warm, cool, fade
  - Added `stabilize_video()` for video stabilization using vidstab
  - CLI commands: `max media brightness`, `max media color`, `max media stabilize`
  
- [x] **3.1.3** Add audio processing
  - Added `normalize_audio()` for audio normalization (loudness)
  - Added `convert_audio()` for format conversion between audio formats
  - Existing: `extract_audio()`, `adjust_volume()`, `mute_video()`
  - CLI commands: `max media normalize`, `max media audio-convert`
  
- [x] **3.1.4** Add screen recording capture
  - Added `screen_record()` to MediaEngine (platform-specific: Windows gdigrab, macOS/Linux x11grab)
  - CLI command: `max media record` (supports --duration, --fps, --audio flags)

- [x] **3.1.5** Add streaming/remote processing
   - Added RTMP streaming (max media stream)
   - Added HLS live preview (max media preview)

---

### 3.2 PDF Processing Enhancements

**Current State**: Basic operations  
**Target**: Complete PDF toolkit

#### Actions

- [x] **3.2.1** Add OCR capabilities
  - Added `ocr_pdf()` to PDFEngine (requires pytesseract and Tesseract installed)
  - Added optional `ocr` extra to pyproject.toml
  - CLI command: `max pdf ocr`

```python
def ocr_pdf(self, input_path: Path, output_path: Path, lang: str = "eng") -> str:
    """Extract text from PDF using OCR (requires pytesseract)."""
    # Implementation
```

- [x] **3.2.2** Add PDF forms support
  - Added `extract_form_data()` to extract form field values
  - Added `fill_form()` to fill forms with provided values
  - Added `flatten_form()` to convert form fields to regular content
  - CLI commands: `max pdf form-data`, `max pdf form-fill`, `max pdf form-flatten`

- [x] **3.2.3** Add PDF comparison
  - Added `compare_pdfs()` to PDFEngine (compares page count, text content, dimensions)
  - CLI command: `max pdf compare file1.pdf file2.pdf`

- [x] **3.2.4** Add PDF optimization
  - Added `optimize_pdf()` with options: remove_unused, compress_images, linearize
  - CLI command: `max pdf optimize`

---

### 3.3 AI & Automation Enhancements

**Current State**: Basic AI integration  
**Target**: Advanced AI-powered workflows

#### Actions

- [x] **3.3.1** Add AI pipeline builder
  - Added `run_pipeline()` to AIEngine to chain multiple AI operations
  - Supports: categorize, analyze_image, generate_image, chat, transform

- [x] **3.3.2** Add semantic search
  - Added `semantic_search()` to AIEngine for natural language file search
  - CLI command: `max ai search "query" /path`

- [x] **3.3.3** Add AI-powered data extraction
  - Added `extract_structured_data()` to AIEngine for extracting structured data from images
  - CLI command: `max ai extract image.jpg -s "field:description"`

- [x] **3.3.4** Enhance chat mode
   - Added persistent conversation history with disk persistence
   - Added conversation export/import (max chat --export, --import)
   - Added context-aware suggestions based on conversation history

---

### 3.4 File Management Enhancements

**Current State**: Basic organization  
**Target**: Advanced file management

#### Actions

- [x] **3.4.1** Add duplicate finder
  - Added `find_duplicates()` to FileOrganizer using MD5 hash
  - CLI command: `max files duplicates` (supports --recursive, --delete)

- [x] **3.4.2** Add file recovery
   - Added backup management (max files backup)
   - Added list/restore backups (max files backups)
   - Added cleanup old backups (max files backup-cleanup)

- [x] **3.4.3** Add secure deletion
  - Added `secure_delete()` to FileOrganizer (overwrites with random data)
  - CLI command: `max files shred` (supports --passes)

- [x] **3.4.4** Add file preview
   - Added metadata viewer (size, dates, type)
   - Added quick preview for text files, images, and PDFs

---

## Phase 4: Developer Experience (Weeks 7-8)

### 4.1 Documentation

**Current State**: README only  
**Target**: Comprehensive documentation

#### Actions

- [ ] **4.1.1** Create CONTRIBUTING.md

```markdown
# Contributing to Max CLI

## Development Setup
1. Fork and clone the repository
2. Create a virtual environment
3. Install dev dependencies: `pip install -e .[dev]`

## Code Style
- Follow PEP 8 with 88 character line length
- Use type hints
- Write tests for new features

## Submitting PRs
- Run tests: `pytest`
- Run linters: `ruff check . && ruff format .`
- Run type checks: `mypy src/`
```

- [x] **4.1.2** Create API documentation
  - Generate from docstrings using Sphinx
  - Host on GitHub Pages
  
- [x] **4.1.3** Add inline documentation
  - Improve docstrings
  - Add code comments where complex

---

### 4.2 CI/CD Pipeline

**Current State**: Basic GitHub Actions  
**Target**: Comprehensive CI/CD

#### Actions

- [x] **4.2.1** Enhance GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.9', '3.10', '3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -e .[dev]
      
      - name: Run tests
        run: pytest --cov=max_cli
      
      - name: Type check
        run: mypy src/
      
      - name: Lint
        run: ruff check .

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build package
        run: python -m build
      
      - name: Publish to PyPI
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: pypa/gh-action-pypi-publish@release
```

- [x] **4.2.2** Add automated release workflow
  - Semantic versioning
  - Changelog generation
  - PyPI automatic publishing

---

### 4.3 Plugin System

**Current State**: Monolithic  
**Target**: Extensible plugin architecture

#### Actions

- [x] **4.3.1** Create plugin interface

```python
# src/max_cli/plugins/base.py
from abc import ABC, abstractmethod

class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        pass
    
    @abstractmethod
    def register(self, app: typer.Typer):
        pass
```

- [x] **4.3.2** Add plugin discovery
  - Auto-discover plugins in `~/.max_cli/plugins/`
  - Plugin configuration
  
- [x] **4.3.3** Create example plugin
  - Community plugin template
  - Documentation for plugin authors

---

## Phase 5: Advanced Features (Weeks 9-10)

### 5.1 Cloud Integration

**Current State**: Local only  
**Target**: Cloud-connected workflows

#### Actions

- [ ] **5.1.1** Add cloud storage support
  - AWS S3 integration
  - Google Drive integration
  - Dropbox integration
  
- [ ] **5.1.2** Add remote processing
  - Process files on remote servers
  - Queue system for heavy tasks

---

### 5.2 Advanced AI Features

**Current State**: Basic AI  
**Target**: AI-powered assistant

#### Actions

- [ ] **5.2.1** Add voice commands
  - Speech-to-text input
  - Text-to-speech output
  
- [ ] **5.2.2** Add smart suggestions
  - Learn from user behavior
  - Predictive commands
  
- [ ] **5.2.3** Add custom AI workflows
  - Define custom AI pipelines
  - Template system for AI tasks

---

### 5.3 System Integration

**Current State**: Basic CLI  
**Target**: Deep system integration

#### Actions

- [ ] **5.3.1** Add system tray support
  - Background processing
  - Notifications
  
- [ ] **5.3.2** Add desktop shortcuts
  - Create .desktop files on Linux
  - Start menu entries on Windows
  
- [ ] **5.3.3** Add hotkey support
  - Global keyboard shortcuts
  - Quick access commands

---

## Priority Matrix

| Priority | Item | Impact | Effort | Timeline |
|----------|------|--------|--------|----------|
| P0 | Expand test coverage | High | Medium | Week 1-2 |
| P0 | Type hints & mypy | High | Medium | Week 1-2 |
| P0 | Pre-commit hooks | High | Low | Week 1-2 |
| P1 | Parallel processing | High | Medium | Week 3-4 |
| P1 | Enhanced config | Medium | Low | Week 3-4 |
| P1 | Retry logic | Medium | Low | Week 3-4 |
| P2 | Video concatenation | High | Medium | Week 5-6 |
| P2 | PDF OCR | High | Medium | Week 5-6 |
| P2 | Plugin system | High | High | Week 7-8 |
| P3 | Cloud integration | Medium | High | Week 9-10 |
| P3 | Voice commands | Medium | High | Week 9-10 |

---

## Success Metrics

### Code Quality

- [ ] >80% test coverage
- [ ] mypy strict mode passes
- [ ] ruff linting passes with no warnings

### Features

- [ ] All Phase 2+ features implemented
- [ ] Plugin system functional
- [ ] Documentation complete

### Developer Experience

- [ ] CI/CD pipeline fully automated
- [ ] <5 minute onboarding for new contributors
- [ ] Automated releases working

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Feature creep | High | Strict priority matrix, phase gates |
| Test maintenance | Medium | Use fixtures, parametrized tests |
| Plugin security | High | Sandboxed execution, signing |
| Dependency bloat | Medium | Regular audit, optional deps |

---

## Next Steps

1. **Immediate**: Set up pre-commit hooks and mypy config
2. **Week 1**: Expand test coverage to >50%
3. **Week 2**: Complete type hints, run mypy strict
4. **Week 3**: Implement parallel processing
5. **Week 4**: Enhance configuration system

### Quality Checks Before Completing Tasks

Before marking any task as complete, always run:

```bash
# 1. Run tests
pytest tests/

# 2. Run linter
ruff check .
ruff format .

# 3. Run type checker
mypy src/

# 4. Verify no regressions
pytest tests/ -v
```

### Checking Existing Implementation Guides

Before starting a new task, always check if an implementation guide already exists:

```bash
# List existing implementation guides
ls tasks/implementation/
```

If a guide exists for your task, read it first and continue from where it left off.

---

*This plan is a living document and should be updated as priorities shift and new insights emerge.*
