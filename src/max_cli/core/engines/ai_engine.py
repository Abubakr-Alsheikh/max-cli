import os
import json
import typer
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
from max_cli.config import settings
from max_cli.common.exceptions import MaxError
from max_cli.common.utils import encode_image_to_base64
from max_cli.common.cache import get_default_cache


class AIEngine:
    def __init__(self):
        self.client = None
        self.ollama_mode = False

        if settings.OLLAMA_ENABLED:
            self.ollama_mode = True
            self.client = OpenAI(
                api_key="ollama", base_url=f"{settings.OLLAMA_BASE_URL}/v1"
            )
        elif settings.OPENAI_API_KEY:
            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL
            )

        self.history: List[Dict[str, str]] = []
        self._history_file = Path.home() / ".max_cli" / "chat_history.json"
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()

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
            except Exception:
                self.history = []

    def _save_history(self) -> None:
        """Save conversation history to disk."""
        data = {"history": self.history}
        self._history_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def clear_history(self) -> None:
        """Clear conversation history from memory and disk."""
        self.history = []
        if self._history_file.exists():
            self._history_file.unlink()

    def export_history(self, output_path: Path) -> None:
        """Export conversation history to a JSON file."""
        data = {"history": self.history, "exported_at": str(Path.cwd())}
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def import_history(self, input_path: Path) -> None:
        """Import conversation history from a JSON file."""
        data = json.loads(input_path.read_text(encoding="utf-8"))
        self.history = data.get("history", [])
        self._save_history()

    def get_suggestions(self) -> List[str]:
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
        except Exception:
            return [
                "Show me what you can do",
                "Help me with files",
                "Process some media",
            ]

    def _get_local_context(self) -> str:
        """Scans current directory to give AI 'eyes'."""
        try:
            files = os.listdir(".")
            # Filter for non-hidden files and limit to 30 for token safety
            visible_files = [f for f in files if not f.startswith(".")][:30]

            context = "\n[USER'S CURRENT ENVIRONMENT]\n"
            context += f"Path: {os.getcwd()}\n"
            context += f"Files in Folder: {', '.join(visible_files)}\n"
            if len(files) > 30:
                context += f"(...and {len(files) - 30} more files)\n"
            return context
        except Exception:
            return ""

    def generate_cli_schema(self, app: typer.Typer, parent_name: str = "max") -> str:
        """
        Dynamically traverses the Typer app to build a documentation string.
        """
        schema_lines = ["Available Commands:"]

        # 1. Traverse Registered Groups (Sub-commands like 'max images ...')
        # Typer stores these in .registered_groups
        for group in app.registered_groups:
            if group.hidden or not group.typer_instance:
                continue

            group_name = group.name

            # Access the commands inside the sub-typer
            for cmd_info in group.typer_instance.registered_commands:
                if cmd_info.hidden:
                    continue

                full_cmd = f"{parent_name} {group_name} {cmd_info.name}"
                description = cmd_info.help or "No description provided."

                # We strip newlines to keep the prompt clean
                description = description.split("\n")[0]

                schema_lines.append(f"- {full_cmd}: {description}")

        return "\n".join(schema_lines)

    def interpret_intent(
        self, user_prompt: str, app_instance: Any, explain: bool = False
    ) -> Dict[str, Any]:
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

        # UPDATED PROMPT: Tell Max he CAN chat, but must use the JSON structure.
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

            # --- SAFETY CATCH ---
            try:
                result = json.loads(raw_content)
            except json.JSONDecodeError:
                # If AI fails to send JSON, wrap its text into a result dict manually
                result = {
                    "thought": raw_content.strip(),
                    "command": None,
                    "dangerous": False,
                }

            # Update history with the response
            self.history.append({"role": "user", "content": user_prompt})
            self.history.append(
                {"role": "assistant", "content": result.get("thought", "")}
            )

            return result
        except Exception as e:
            raise MaxError(f"AI Interpretation Error: {e}")

    def categorize_files(self, file_list: List[str]) -> Dict[str, str]:
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
        except Exception:
            return {f: "Other" for f in file_list}

    def analyze_image_content(self, image_path: Path, prompt: str) -> str:
        """
        Sends an image + prompt to the Vision Model (Gemini/GPT-4o).
        Returns the text description.
        """
        if not self.client:
            raise MaxError("Missing AI Configuration. Check your .env file.")

        # 1. Encode Image
        try:
            base64_image = encode_image_to_base64(image_path)
        except Exception as e:
            raise MaxError(f"Failed to process image: {e}")

        # 2. Build Payload
        # Note: We do NOT force JSON mode here, as we want natural language description.
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            # JPEG header usually works for PNG/WEBP in OpenAI/Gemini APIs
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ]

        # 3. Call API
        try:
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise MaxError(f"AI Vision Error: {str(e)}")

    def generate_image(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Generates an image. Uses the dedicated IMAGE_MODEL by default.
        """
        if not self.client:
            raise MaxError("AI Client not configured.")

        # If no specific model override is passed in the command, use the config value
        target_model = model or settings.AI_IMAGE_MODEL

        try:
            response = self.client.chat.completions.create(
                model=target_model, messages=[{"role": "user", "content": prompt}]
            )

            content = response.choices[0].message.content
            return self._extract_image_url(content, response)
        except Exception as e:
            raise MaxError(f"Image Generation Failed using {target_model}: {e}")

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
            raise MaxError(f"Image Editing Failed using {target_model}: {e}")

    def _extract_image_url(self, content: str, raw_response: Any) -> str:
        """
        Helper to find image URL in Nano Banana response.
        """
        # 1. Check for standard Markdown URL: ![alt text](url)
        import re

        match = re.search(r"\((https?://[^\s)]+)\)", content)
        if match:
            return match.group(1)

        # 2. Check for raw URL in text
        url_match = re.search(r"https?://[^\s]+", content)
        if url_match:
            return url_match.group(0)

        # 3. Check raw response dictionary (Advanced Google implementation)
        raw_dict = raw_response.model_dump()
        if "images" in raw_dict and raw_dict["images"]:
            return raw_dict["images"][0].get("url")

        raise MaxError("AI generated a response, but no image URL was found.")

    def run_pipeline(
        self, operations: List[Dict[str, Any]], input_data: Any = None
    ) -> List[Dict[str, Any]]:
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

    def semantic_search(self, query: str, files: List[Path]) -> List[Dict[str, Any]]:
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

        for file_path in files:
            try:
                if file_path.suffix.lower() in [
                    ".txt",
                    ".md",
                    ".py",
                    ".json",
                    ".yaml",
                    ".yml",
                ]:
                    file_content = file_path.read_text(
                        encoding="utf-8", errors="ignore"
                    )[:5000]
                elif file_path.suffix.lower() == ".pdf":
                    continue
                else:
                    continue

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

            except Exception:
                continue

        return results

    def extract_structured_data(
        self, image_path: Path, schema: Dict[str, str]
    ) -> Dict[str, Any]:
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
            import json

            try:
                data = json.loads(result)
                return data
            except json.JSONDecodeError:
                return {"raw_text": result, "error": "Could not parse as JSON"}
        except Exception as e:
            raise MaxError(f"Data extraction failed: {e}")
