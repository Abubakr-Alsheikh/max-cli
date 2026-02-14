import pytest
from PIL import Image


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
