import json
import logging
from pathlib import Path
from typing import Any, Optional

from max_cli.common.atomic import atomic_write_json
from max_cli.common.cache import get_default_cache
from max_cli.common.exceptions import MaxError
from max_cli.common.utils import encode_image_to_base64
from max_cli.config import settings

# Text formats semantic_search can read; other files are skipped.
SEARCHABLE_SUFFIXES = {".txt", ".md", ".py", ".json", ".yaml", ".yml"}
DOWNLOAD_CHUNK_SIZE = 8192

logger = logging.getLogger(__name__)


def make_client(ollama: Optional[bool] = None) -> Optional[Any]:
    """An OpenAI-compatible client for the configured provider.

    Ollama when OLLAMA_ENABLED (or `ollama`) is on, else the API key with its
    base URL (OpenAI, OpenRouter, Gemini ...). None when there's no key.
    """
    from openai import OpenAI

    use_ollama = settings.OLLAMA_ENABLED if ollama is None else ollama
    if use_ollama:
        return OpenAI(api_key="ollama", base_url=f"{settings.OLLAMA_BASE_URL}/v1")
    if settings.OPENAI_API_KEY:
        return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    return None


def chat_model() -> str:
    """The model for chat and the agent: Ollama's or AI_MODEL."""
    return settings.OLLAMA_MODEL if settings.OLLAMA_ENABLED else settings.AI_MODEL


def find_searchable_files(folder: Path, extensions: list[str]) -> list[Path]:
    """Files under `folder` (recursive) whose suffix is in `extensions`.

    `extensions` are given without dots and matched case-insensitively.
    """
    suffixes = {
        f".{ext.strip().lower().lstrip('.')}" for ext in extensions if ext.strip()
    }
    return [
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    ]


def download_image(url: str, destination: Path) -> Path:
    """Save the image at `url` to `destination` without leaving a partial file."""
    import requests

    temp_path = destination.with_name(f".{destination.name}.part")
    try:
        with requests.get(
            url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT
        ) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as image_file:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    image_file.write(chunk)
        temp_path.replace(destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return destination


def _ai_call_errors() -> tuple[type[BaseException], ...]:
    """Errors from an AI request or from parsing its reply."""
    import openai

    return (
        openai.OpenAIError,
        json.JSONDecodeError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
    )


# Folder for a file the AI didn't place, by its kind (common/file_kinds).
KIND_FOLDERS = {
    "video": "Videos",
    "audio": "Music",
    "image": "Images",
    "pdf": "PDFs",
    "document": "Documents",
    "archive": "Archives",
}
FALLBACK_FOLDER = "Other"


def kind_folder(file_name: str) -> str:
    """Where a file goes when the AI can't say: its kind's folder."""
    from max_cli.common.file_kinds import kind_of

    return KIND_FOLDERS.get(kind_of(Path(file_name)), FALLBACK_FOLDER)


def json_object(text: str) -> dict[str, Any]:
    """The JSON object in a model's reply, even inside a ```json fence or
    with words around it. Raises json.JSONDecodeError when there's none."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise json.JSONDecodeError("No JSON object in the reply", text, 0)
    found = json.loads(text[start : end + 1])
    if not isinstance(found, dict):
        raise json.JSONDecodeError("The reply's JSON isn't an object", text, 0)
    return found


class AIEngine:
    def __init__(self):
        self._client = None
        self.ollama_mode = False
        self._client_initialized = False

        if settings.OLLAMA_ENABLED:
            self.ollama_mode = True

        self.history: list[dict[str, str]] = []
        self._history_file = Path.home() / ".max_cli" / "chat_history.json"
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def _get_client(self):
        """Lazily create OpenAI client on first access."""
        if self._client is None:
            self._client = make_client(ollama=self.ollama_mode)
        return self._client

    @property
    def client(self):
        return self._get_client()

    @property
    def current_model(self) -> str:
        """Get the current model based on provider mode."""
        if self.ollama_mode:
            return settings.OLLAMA_MODEL
        return settings.AI_MODEL

    def _load_history(self) -> None:
        """Load conversation history from disk."""
        if self._history_file.exists():
            try:
                data = json.loads(self._history_file.read_text(encoding="utf-8"))
                self.history = data.get("history", [])
            except (OSError, ValueError, AttributeError):
                logger.warning(
                    "Ignoring unreadable chat history %s", self._history_file
                )
                self.history = []

    def _save_history(self) -> None:
        """Save conversation history to disk."""
        atomic_write_json(self._history_file, {"history": self.history})

    def clear_history(self) -> None:
        """Clear conversation history from memory and disk."""
        self.history = []
        if self._history_file.exists():
            self._history_file.unlink()

    def export_history(self, output_path: Path) -> None:
        """Export conversation history to a JSON file."""
        from datetime import datetime

        data = {"history": self.history, "exported_at": datetime.now().isoformat()}
        atomic_write_json(output_path, data)

    def import_history(self, input_path: Path) -> None:
        """Import conversation history from a JSON file."""
        data = json.loads(input_path.read_text(encoding="utf-8"))
        self.history = data.get("history", [])
        self._save_history()

    def categorize_files(self, file_list: list[str]) -> dict[str, str]:
        """AI-powered semantic grouping of files."""
        cache = get_default_cache()
        cache_key = f"categorize:{','.join(sorted(file_list))}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        prompt = f"Categorize these files into logical folders (e.g., Invoices, Photos, Scripts). Return a JSON map: {{filename: category_name}}\nFiles: {file_list}"

        try:
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = json_object(response.choices[0].message.content or "")
        except _ai_call_errors() as e:
            # One line, not a traceback: the sort still works, by kind.
            logger.warning("AI categories unavailable (%s); sorting by file kind", e)
            return {name: kind_folder(name) for name in file_list}
        result = {
            name: str(answer.get(name) or kind_folder(name)) for name in file_list
        }
        cache.set(cache_key, result, ttl=3600)
        return result

    def analyze_image_content(self, image_path: Path, prompt: str) -> str:
        """
        Sends an image + prompt to the Vision Model (Gemini/GPT-4o).
        Returns the text description.
        """
        if not self.client:
            raise MaxError("Missing AI Configuration. Check your .env file.")

        try:
            base64_image = encode_image_to_base64(image_path)
        except Exception as e:
            raise MaxError(f"Failed to process image: {e}") from e

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise MaxError(f"AI Vision Error: {str(e)}") from e

    def generate_image(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Generates an image. Uses the dedicated IMAGE_MODEL by default.
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        target_model = model or settings.AI_IMAGE_MODEL

        try:
            response = self.client.chat.completions.create(
                model=target_model, messages=[{"role": "user", "content": prompt}]
            )

            content = response.choices[0].message.content
            return self._extract_image_url(content, response)
        except Exception as e:
            raise MaxError(f"Image Generation Failed using {target_model}: {e}") from e

    def edit_image(
        self, image_path: Path, prompt: str, model: Optional[str] = None
    ) -> str:
        """
        Edits an image. Uses the dedicated IMAGE_MODEL by default.
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        target_model = model or settings.AI_IMAGE_MODEL
        base64_img = encode_image_to_base64(image_path)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"},
                    },
                ],
            }
        ]

        try:
            response = self.client.chat.completions.create(
                model=target_model, messages=messages
            )
            content = response.choices[0].message.content
            return self._extract_image_url(content, response)
        except Exception as e:
            raise MaxError(f"Image Editing Failed using {target_model}: {e}") from e

    def _extract_image_url(self, content: str, raw_response: Any) -> str:
        """
        Helper to find image URL in Nano Banana response.
        """
        import re

        match = re.search(r"\((https?://[^\s)]+)\)", content)
        if match:
            return match.group(1)

        url_match = re.search(r"https?://[^\s]+", content)
        if url_match:
            return url_match.group(0)

        raw_dict = raw_response.model_dump()
        if "images" in raw_dict and raw_dict["images"]:
            return raw_dict["images"][0].get("url")

        raise MaxError("AI generated a response, but no image URL was found.")

    def semantic_search(self, query: str, files: list[Path]) -> list[dict[str, Any]]:
        """
        Search files by content using AI.

        Args:
            query: Natural language search query
            files: List of files to search

        Returns:
            List of matching results with relevance scores
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        results = []

        skippable_errors: tuple[type[BaseException], ...] = (
            OSError,
            *_ai_call_errors(),
        )
        for file_path in files:
            try:
                if file_path.suffix.lower() not in SEARCHABLE_SUFFIXES:
                    continue
                file_content = file_path.read_text(encoding="utf-8", errors="ignore")[
                    :5000
                ]

                prompt = f"""Search Query: {query}

File: {file_path.name}

Content:
{file_content}

Does this file match the query? Reply with YES or NO followed by a brief explanation."""

                response = self.client.chat.completions.create(
                    model=self.current_model,
                    messages=[{"role": "user", "content": prompt}],
                )

                answer = response.choices[0].message.content or ""

                if answer.strip().upper().startswith("YES"):
                    results.append(
                        {"file": str(file_path), "match": True, "reasoning": answer}
                    )

            except skippable_errors:
                logger.warning("Skipped %s during AI search", file_path, exc_info=True)
                continue

        return results

    def extract_structured_data(
        self, image_path: Path, schema: dict[str, str]
    ) -> dict[str, Any]:
        """
        Extract structured data from an image using AI vision.

        Args:
            image_path: Path to image file
            schema: Dict mapping field names to descriptions

        Returns:
            Extracted structured data
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        schema_text = "\n".join(
            [f"- {field}: {desc}" for field, desc in schema.items()]
        )

        prompt = f"""Extract structured data from this image. 

Schema:
{schema_text}

Return a JSON object with the extracted data."""

        try:
            result = self.analyze_image_content(image_path, prompt)
            try:
                data = json.loads(result)
                return data
            except json.JSONDecodeError:
                return {"raw_text": result, "error": "Could not parse as JSON"}
        except Exception as e:
            raise MaxError(f"Data extraction failed: {e}") from e
