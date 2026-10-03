from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from max_cli.common.exceptions import MaxError
from max_cli.config import settings
from max_cli.core.engines.ai_engine import AIEngine, image_source, save_image


class TestAIEngine:
    """Tests for AI operations."""

    def test_the_client_comes_from_the_providers(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")

        engine = AIEngine()

        assert engine._client is None
        assert engine.client is not None

    def test_without_a_key_there_is_no_client(self, monkeypatch):
        monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
        monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
        monkeypatch.setattr(settings, "AI_FALLBACK_PROVIDER", "")

        assert AIEngine().client is None

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_categorize_files(self, mock_settings, mock_openai):
        """Test file categorization."""
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = '{"file1.txt": "Documents", "file2.txt": "Images"}'
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai.return_value = mock_client

        engine = AIEngine()
        engine._client = mock_client

        result = engine.categorize_files(["file1.txt", "file2.txt"])

        assert "file1.txt" in result

    @patch("max_cli.core.engines.ai_engine.get_default_cache")
    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_categorize_files_fallback(self, mock_settings, mock_openai, mock_cache):
        """Test file categorization fallback on error."""
        mock_cache.return_value.get.return_value = None

        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False

        mock_client = MagicMock()
        import openai

        mock_client.chat.completions.create.side_effect = openai.OpenAIError(
            "API Error"
        )

        mock_openai.return_value = mock_client

        engine = AIEngine()
        engine._client = mock_client

        result = engine.categorize_files(["file1.txt", "file2.txt"])

        # By kind when the AI can't answer: .txt is a document.
        assert result == {"file1.txt": "Documents", "file2.txt": "Documents"}

    @pytest.mark.parametrize(
        "reply, expected",
        [
            (
                'Here you go:\n```json\n{"a.mp3": "Chill"}\n```',
                {"a.mp3": "Chill", "b.jpg": "Images"},
            ),
            ("", {"a.mp3": "Music", "b.jpg": "Images"}),
        ],
    )
    @patch("max_cli.core.engines.ai_engine.get_default_cache")
    def test_categorize_reads_fenced_json_and_falls_back_by_kind(
        self, mock_cache, reply, expected
    ):
        """A free model wrapped its JSON in a fence, or sent nothing at all."""
        mock_cache.return_value.get.return_value = None
        engine = AIEngine()
        engine._client = MagicMock()
        engine._client.chat.completions.create.return_value.choices = [MagicMock()]
        engine._client.chat.completions.create.return_value.choices[
            0
        ].message.content = reply

        assert engine.categorize_files(["a.mp3", "b.jpg"]) == expected

    @staticmethod
    def _image_setup(monkeypatch) -> MagicMock:
        """Gemini as the main AI with an image model; its client is a mock
        whose images endpoint sends back a base64 PNG."""
        from max_cli.core.engines import ai_providers

        for name, value in {
            "AI_PROVIDER": "gemini",
            "AI_FALLBACK_PROVIDER": "",
            "GEMINI_API_KEY": "g-key",
            "GEMINI_MODEL": "gemini-flash-latest",
            "GEMINI_IMAGE_MODEL": "gemini-3.1-flash-image",
        }.items():
            monkeypatch.setattr(settings, name, value)
        client = MagicMock()
        picture = SimpleNamespace(b64_json="aGVsbG8=", url=None, media_type="image/png")
        client.images.generate.return_value = SimpleNamespace(data=[picture])
        monkeypatch.setattr(ai_providers, "_openai_client", lambda *args: client)
        return client

    def test_generate_image_uses_the_main_ais_image_model(self, monkeypatch):
        client = self._image_setup(monkeypatch)

        result = AIEngine().generate_image("A test image")

        assert result == "data:image/png;base64,aGVsbG8="
        sent = client.images.generate.call_args.kwargs
        assert sent["model"] == "gemini-3.1-flash-image"
        assert sent["prompt"] == "A test image"

    def test_a_named_model_wins(self, monkeypatch):
        client = self._image_setup(monkeypatch)

        AIEngine().generate_image("A test image", model="gemini-3-pro-image")

        sent = client.images.generate.call_args.kwargs
        assert sent["model"] == "gemini-3-pro-image"

    def test_without_an_image_model_says_so(self, monkeypatch):
        self._image_setup(monkeypatch)
        monkeypatch.setattr(settings, "GEMINI_IMAGE_MODEL", "")

        with pytest.raises(
            MaxError, match="No image model is set up for Google Gemini"
        ):
            AIEngine().generate_image("A test image")

    def test_image_source_prefers_a_link_then_the_data(self):
        link = SimpleNamespace(
            data=[SimpleNamespace(url="https://x/y.png", b64_json=None)]
        )
        data = SimpleNamespace(
            data=[SimpleNamespace(url=None, b64_json="aGk=", media_type="image/webp")]
        )

        assert image_source(link) == "https://x/y.png"
        assert image_source(data) == "data:image/webp;base64,aGk="
        with pytest.raises(MaxError, match="sent no image"):
            image_source(SimpleNamespace(data=[]))

    def test_save_image_decodes_a_data_url(self, tmp_path):
        target = tmp_path / "out.png"

        save_image("data:image/png;base64,aGVsbG8=", target)

        assert target.read_bytes() == b"hello"
        assert not list(tmp_path.glob(".*.part"))

    def test_save_image_downloads_a_link(self, tmp_path):
        with patch("max_cli.core.engines.ai_engine.download_image") as download:
            save_image("https://x/y.png", tmp_path / "out.png")

        download.assert_called_once_with("https://x/y.png", tmp_path / "out.png")
