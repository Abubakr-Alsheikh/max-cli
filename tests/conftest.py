import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path_factory, monkeypatch):
    """Keep every TaskManager, and its legacy-file migration, out of ~/.max_cli."""
    from max_cli.core.engines import task_manager

    store_root = tmp_path_factory.mktemp("max_cli_home")
    queue_dir = store_root / "tasks"
    monkeypatch.setattr(task_manager.TaskManager, "QUEUE_DIR", queue_dir)
    monkeypatch.setattr(
        task_manager.TaskManager, "QUEUE_FILE", queue_dir / "queue.json"
    )
    monkeypatch.setattr(
        task_manager.TaskManager, "HISTORY_FILE", queue_dir / "history.json"
    )
    monkeypatch.setattr(task_manager.TaskManager, "LEGACY_DIR", store_root)
    task_manager.reset_task_manager()
    yield store_root
    task_manager.reset_task_manager()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    """Point Path.home() and every home-based constant at a temp folder.

    Tests used to write into the real ~/.max_cli (the FFmpeg path cache and
    the AI categorize cache). Code that calls Path.home() at run time gets
    the fake home; constants computed at import time are patched here.
    """
    from pathlib import Path

    from max_cli.common import cache, ffmpeg_resolver
    from max_cli.core.engines import audio_engine
    from max_cli.interface.config import grab, manage, setup

    fake_home = tmp_path_factory.mktemp("home")
    max_cli_dir = fake_home / ".max_cli"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(ffmpeg_resolver, "MAX_CLI_BIN_DIR", max_cli_dir / "bin")
    monkeypatch.setattr(
        ffmpeg_resolver,
        "RESOLUTION_CACHE_FILE",
        max_cli_dir / ".ffmpeg_resolved_path",
    )
    monkeypatch.setattr(audio_engine, "RNNOISE_MODEL_DIR", max_cli_dir / "rnnoise")
    for config_module in (grab, manage, setup):
        monkeypatch.setattr(
            config_module, "GLOBAL_CONFIG_PATH", fake_home / ".max_config.env"
        )
    monkeypatch.setattr(cache, "_default_cache", None)
    yield fake_home
    monkeypatch.setattr(cache, "_default_cache", None)


@pytest.fixture
def temp_directory(tmp_path):
    """Provides a temporary directory for file operations."""
    return tmp_path


@pytest.fixture
def dummy_image(tmp_path):
    """Creates a temporary 100x100 red JPEG image for testing."""
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_path, "JPEG")
    return img_path


@pytest.fixture
def dummy_image_png(tmp_path):
    """Creates a temporary 100x100 blue PNG image for testing."""
    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_path, "PNG")
    return img_path


@pytest.fixture
def dummy_pdf(tmp_path):
    """Creates a temporary single-page PDF for testing."""
    pdf_path = tmp_path / "test.pdf"
    img = Image.new("RGB", (200, 200), color="white")
    img.save(pdf_path, "PDF")
    return pdf_path


@pytest.fixture
def dummy_pdf_multi(tmp_path):
    """Creates a temporary 3-page PDF for testing."""
    pdf_path = tmp_path / "multi.pdf"
    images = []
    for color in ["red", "green", "blue"]:
        img = Image.new("RGB", (200, 200), color=color)
        images.append(img)
    images[0].save(
        pdf_path,
        "PDF",
        save_all=True,
        append_images=images[1:],
    )
    return pdf_path


@pytest.fixture
def dummy_video(tmp_path):
    """Creates a dummy video file for testing (mock)."""
    video_path = tmp_path / "test.mp4"
    video_path.write_text("mock video content")
    return video_path


@pytest.fixture
def dummy_audio(tmp_path):
    """Creates a dummy audio file for testing (mock)."""
    audio_path = tmp_path / "test.mp3"
    audio_path.write_text("mock audio content")
    return audio_path


@pytest.fixture
def sample_files(tmp_path):
    """Creates multiple sample files for batch testing."""
    files = []
    for i in range(3):
        file_path = tmp_path / f"file_{i}.txt"
        file_path.write_text(f"Content {i}")
        files.append(file_path)
    return files


@pytest.fixture
def sample_directory(tmp_path):
    """Creates a directory with various files for organization testing."""
    dir_path = tmp_path / "sample_dir"
    dir_path.mkdir()

    (dir_path / "document.pdf").write_text("pdf content")
    (dir_path / "photo.jpg").write_text("jpg content")
    (dir_path / "script.py").write_text("python content")
    (dir_path / "data.json").write_text("json content")

    return dir_path


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Sets up mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return monkeypatch
