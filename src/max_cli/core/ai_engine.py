import os
import json
import typer
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
from max_cli.config import settings
from max_cli.common.exceptions import MaxError
from max_cli.common.utils import encode_image_to_base64


class AIEngine:
    def __init__(self):
        self.client = None
        if settings.OPENAI_API_KEY:

            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL
            )
        # Session history for the 'chat' command
        self.history: List[Dict[str, str]] = []

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
                context += f"(...and {len(files)-30} more files)\n"
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
            raise MaxError(
                "Missing AI Configuration.\n"
                "Please set OPENAI_API_KEY in your .env file."
            )

        tools = (
            app_instance.generate_cli_schema(app_instance)
            if hasattr(app_instance, "registered_groups")
            else ""
        )
        context = self._get_local_context()

        system_msg = f"""
You are "Max", a CLI agent. 
TOOLS:
{tools}
{context}

INSTRUCTIONS:
- Map user requests to the TOOLS provided.
- Use the filenames in [USER'S CURRENT ENVIRONMENT] to resolve vague names.
- Return ONLY a JSON object.

JSON STRUCTURE:
{{
    "thought": "Reasoning",
    "command": "The shell command",
    "explanation": "Briefly explain what the flags do (only if requested)",
    "dangerous": true/false
}}

If the request is unrelated to the tools or ambiguous, return:
{{ "error": "I cannot handle this request with current tools." }}
        """

        try:
            messages = [{"role": "system", "content": system_msg}]
            # Add history if we are in a chat session
            messages.extend(self.history)
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=messages,
            )

            result = json.loads(response.choices[0].message.content)

            # Save to history for future context in this session
            self.history.append({"role": "user", "content": user_prompt})
            self.history.append(
                {
                    "role": "assistant",
                    "content": result.get("command", "I couldn't find a command."),
                }
            )

            return result
        except Exception as e:
            raise MaxError(f"AI Interpretation Error: {e}")

    def categorize_files(self, file_list: List[str]) -> Dict[str, str]:
        """AI-powered semantic grouping of files."""
        prompt = f"Categorize these files into logical folders (e.g., Invoices, Photos, Scripts). Return a JSON map: {{filename: category_name}}\nFiles: {file_list}"

        try:
            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            # Fallback to 'Other' if AI fails
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
                model=settings.AI_MODEL,
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
