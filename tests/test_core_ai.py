import pytest
from unittest.mock import patch, MagicMock
from max_cli.core.engines.ai_engine import AIEngine
from max_cli.common.exceptions import MaxError


class TestAIEngine:
    """Tests for AI operations."""

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_init_with_api_key(self, mock_settings, mock_openai):
        """Test initialization with API key."""
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False

        engine = AIEngine()
        assert engine._client is None
        client = engine.client
        assert client is not None

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_init_without_api_key(self, mock_settings, mock_openai):
        """Test initialization without API key."""
        mock_settings.OPENAI_API_KEY = None
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False

        engine = AIEngine()
        assert engine._client is None
        assert engine.client is None

    @patch("os.listdir")
    @patch("os.getcwd")
    def test_get_local_context(self, mock_getcwd, mock_listdir):
        """Test getting local context."""
        mock_getcwd.return_value = "/test/dir"
        mock_listdir.return_value = ["file1.txt", "file2.txt", "file3.py"]

        engine = AIEngine()
        context = engine._get_local_context()

        assert "/test/dir" in context
        assert "file1.txt" in context

    @patch("os.listdir")
    @patch("os.getcwd")
    def test_get_local_context_with_error(self, mock_getcwd, mock_listdir):
        """Test error handling in local context."""
        mock_getcwd.side_effect = Exception("Permission denied")

        engine = AIEngine()
        context = engine._get_local_context()

        assert context == ""

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_interpret_intent_no_client(self, mock_settings, mock_openai):
        """Test interpret intent without client."""
        mock_settings.OPENAI_API_KEY = None
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False
        mock_openai.return_value = None

        engine = AIEngine()
        mock_app = MagicMock()

        with pytest.raises(MaxError, match="Missing AI"):
            engine.interpret_intent("test prompt", mock_app)

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
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        mock_openai.return_value = mock_client

        engine = AIEngine()
        engine._client = mock_client

        result = engine.categorize_files(["file1.txt", "file2.txt"])

        assert result == {"file1.txt": "Other", "file2.txt": "Other"}

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_generate_image(self, mock_settings, mock_openai):
        """Test image generation."""
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
        ].message.content = "Test prompt\n![image](https://example.com/image.png)"

        mock_client.chat.completions.create.return_value = mock_response

        mock_openai.return_value = mock_client

        engine = AIEngine()
        engine._client = mock_client

        result = engine.generate_image("A test image")

        assert "https://example.com/image.png" in result

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_generate_image_no_client(self, mock_settings, mock_openai):
        """Test image generation without client."""
        mock_settings.OPENAI_API_KEY = None
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False
        mock_openai.return_value = None

        engine = AIEngine()

        with pytest.raises(MaxError, match="AI Client not configured"):
            engine.generate_image("A test image")

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_extract_image_url_markdown(self, mock_settings, mock_openai):
        """Test extracting image URL from markdown."""
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.AI_MODEL = "gpt-4"
        mock_settings.AI_IMAGE_MODEL = "dall-e-3"
        mock_settings.OLLAMA_ENABLED = False

        mock_client = MagicMock()

        mock_openai.return_value = mock_client

        engine = AIEngine()

        content = "Check this image: (https://example.com/img.png)"
        mock_response = MagicMock()

        result = engine._extract_image_url(content, mock_response)

        assert result == "https://example.com/img.png"

    @patch("openai.OpenAI")
    @patch("max_cli.core.engines.ai_engine.settings")
    def test_extract_image_url_not_found(self, mock_settings, mock_openai):
        """Test error when no image URL found."""
        mock_settings.OPENAI_API_KEY = "test-key"
        mock_settings.OLLAMA_ENABLED = False

        mock_openai.return_value = MagicMock()

        engine = AIEngine()

        mock_response = MagicMock()
        mock_response.model_dump.return_value = {}

        with pytest.raises(MaxError, match="no image URL was found"):
            engine._extract_image_url("No URL here", mock_response)
