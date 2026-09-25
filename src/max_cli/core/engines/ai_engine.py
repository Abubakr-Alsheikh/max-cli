import json
import logging
from pathlib import Path
from typing import Any, Optional

from max_cli.common.atomic import atomic_write_json
from max_cli.common.cache import get_default_cache
from max_cli.common.exceptions import MaxError
from max_cli.common.utils import encode_image_to_base64
from max_cli.config import settings

LOCAL_CONTEXT_FILE_LIMIT = 30  # file names shared with the model per request
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 60
# Text formats semantic_search can read; other files are skipped.
SEARCHABLE_SUFFIXES = {".txt", ".md", ".py", ".json", ".yaml", ".yml"}
DOWNLOAD_CHUNK_SIZE = 8192

logger = logging.getLogger(__name__)


def find_searchable_files(folder: Path, extensions: list[str]) -> list[Path]:
    """Files under `folder` (recursive) whose suffix is in `extensions`.

    `extensions` are given without dots and matched case-insensitively.
    """
    suffixes = {f".{ext.strip().lower().lstrip('.')}" for ext in extensions if ext.strip()}
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
            url, stream=True, timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS
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
            from openai import OpenAI

            if self.ollama_mode:
                self._client = OpenAI(
                    api_key="ollama", base_url=f"{settings.OLLAMA_BASE_URL}/v1"
                )
            elif settings.OPENAI_API_KEY:
                self._client = OpenAI(
                    api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL
                )
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
                logger.warning("Ignoring unreadable chat history %s", self._history_file)
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

    def get_suggestions(self) -> list[str]:
        """Get context-aware suggestions based on conversation history."""
        if not self.history or not self.client:
            return [
                "Help me organize my files",
                "Compress these images",
                "Extract audio from this video",
            ]

        recent_topics = " ".join(
            [msg["content"] for msg in self.history[-4:] if msg.get("role") == "user"]
        )

        prompt = f"""Based on this conversation context: "{recent_topics}"

Suggest 3 relevant follow-up commands the user might want to run. 
Keep suggestions brief and related to file management, media processing, or AI features.
Return as a JSON array of strings."""

        try:
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=[{"role": "user", "content": prompt}],
            )
            result = json.loads(response.choices[0].message.content)
            return result if isinstance(result, list) else []
        except _ai_call_errors():
            logger.warning("AI suggestions failed; using defaults", exc_info=True)
            return [
                "Show me what you can do",
                "Help me with files",
                "Process some media",
            ]

    def _get_local_context(self) -> str:
        """Scans current directory to give AI 'eyes'."""
        try:
            cwd = Path.cwd()
            visible_files = sorted(
                entry.name for entry in cwd.iterdir() if not entry.name.startswith(".")
            )
        except OSError:
            return ""

        context = "\n[USER'S CURRENT ENVIRONMENT]\n"
        context += f"Path: {cwd}\n"
        context += (
            f"Files in Folder: {', '.join(visible_files[:LOCAL_CONTEXT_FILE_LIMIT])}\n"
        )
        hidden_count = len(visible_files) - LOCAL_CONTEXT_FILE_LIMIT
        if hidden_count > 0:
            context += f"(...and {hidden_count} more files)\n"
        return context

    def generate_cli_schema(self, app: Any, parent_name: str = "max") -> str:
        """
        Dynamically traverses the Typer app to build a documentation string.
        """

        schema_lines = ["Available Commands:"]

        for group in app.registered_groups:
            if group.hidden or not group.typer_instance:
                continue

            group_name = group.name

            for cmd_info in group.typer_instance.registered_commands:
                if cmd_info.hidden:
                    continue

                full_cmd = f"{parent_name} {group_name} {cmd_info.name}"
                description = cmd_info.help or "No description provided."

                description = description.split("\n")[0]

                schema_lines.append(f"- {full_cmd}: {description}")

        return "\n".join(schema_lines)

    def interpret_intent(
        self, user_prompt: str, app_instance: Any, explain: bool = False
    ) -> dict[str, Any]:
        """Translates natural language to CLI commands with local context."""
        if not self.client:
            if settings.OLLAMA_ENABLED:
                raise MaxError(
                    "Missing AI Configuration.\n"
                    "Please set OLLAMA_ENABLED=true in your .env file.\n"
                    "Or set OPENAI_API_KEY for cloud AI providers."
                )
            raise MaxError(
                "Missing AI Configuration.\n"
                "Please set OPENAI_API_KEY in your .env file."
            )

        tools = (
            self.generate_cli_schema(app_instance)
            if hasattr(app_instance, "registered_groups")
            else ""
        )
        context = self._get_local_context()

        system_msg = f"""
You are "Max", a CLI agent. 
TOOLS: {tools}
{context}

INSTRUCTIONS:
1. If the user asks a tool-related question, return the "command".
2. If the user is just chatting (e.g., "hello", "who are you?"), use the "thought" field for your response and leave "command" as null.
3. ALWAYS return a JSON object. No markdown. No outside text.

JSON STRUCTURE:
{{
    "thought": "Your conversational response or reasoning",
    "command": "The shell command or null",
    "explanation": "Briefly explain what the flags do (only if requested)",
    "dangerous": true/false
}}

If the request is unrelated to the tools or ambiguous, return:
{{ "error": "I cannot handle this request with current tools. (and you have to explain the reason why not)" }}
        """

        try:
            messages = [{"role": "system", "content": system_msg}]
            messages.extend(self.history)
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
            )

            raw_content = response.choices[0].message.content

            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError:
                result = {
                    "thought": raw_content.strip(),
                    "command": None,
                    "dangerous": False,
                }

            self.history.append({"role": "user", "content": user_prompt})
            self.history.append(
                {"role": "assistant", "content": result.get("thought", "")}
            )

            return result
        except Exception as e:
            raise MaxError(f"AI Interpretation Error: {e}") from e

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
            result = json.loads(response.choices[0].message.content)
            cache.set(cache_key, result, ttl=3600)
            return result
        except _ai_call_errors():
            logger.warning("AI categorization failed; using 'Other'", exc_info=True)
            return {f: "Other" for f in file_list}

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

    def run_pipeline(
        self, operations: list[dict[str, Any]], input_data: Any = None
    ) -> list[dict[str, Any]]:
        """
        Run a pipeline of AI operations.

        Args:
            operations: List of operation dicts with 'type' and 'params'
            input_data: Initial input data

        Returns:
            List of results from each operation
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        current_data = input_data
        results = []

        for i, op in enumerate(operations):
            op_type = op.get("type", "").lower()
            params = op.get("params", {})

            try:
                if op_type == "categorize":
                    files = params.get("files", [])
                    result = self.categorize_files(files)
                    results.append(
                        {"step": i + 1, "operation": "categorize", "result": result}
                    )

                elif op_type == "analyze_image":
                    image_path = params.get("image_path")
                    prompt = params.get("prompt", "Describe this image")
                    if image_path:
                        result = self.analyze_image_content(Path(image_path), prompt)
                        results.append(
                            {
                                "step": i + 1,
                                "operation": "analyze_image",
                                "result": result,
                            }
                        )

                elif op_type == "generate_image":
                    prompt = params.get("prompt", "")
                    if prompt:
                        result = self.generate_image(prompt)
                        results.append(
                            {
                                "step": i + 1,
                                "operation": "generate_image",
                                "result": result,
                            }
                        )

                elif op_type == "chat":
                    message = params.get("message", "")
                    if message:
                        result = self.interpret_intent(message, None)
                        results.append(
                            {"step": i + 1, "operation": "chat", "result": result}
                        )

                elif op_type == "transform":
                    transform_prompt = params.get("prompt", "")
                    input_text = params.get("input", current_data)
                    if transform_prompt and input_text:
                        response = self.client.chat.completions.create(
                            model=self.current_model,
                            messages=[
                                {
                                    "role": "user",
                                    "content": f"{transform_prompt}\n\n{input_text}",
                                }
                            ],
                        )
                        result = response.choices[0].message.content
                        current_data = result
                        results.append(
                            {"step": i + 1, "operation": "transform", "result": result}
                        )

                else:
                    results.append(
                        {
                            "step": i + 1,
                            "operation": op_type,
                            "error": f"Unknown operation: {op_type}",
                        }
                    )

            except Exception as e:
                results.append({"step": i + 1, "operation": op_type, "error": str(e)})

        return results

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
                file_content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )[:5000]

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
