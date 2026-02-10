import json
import typer
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from max_cli.config import settings
from max_cli.common.exceptions import MaxError
from max_cli.common.utils import encode_image_to_base64
import requests


class AIEngine:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            # We don't raise an error immediately, only if they try to use it
            self.client = None
        else:
            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL
            )

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
        self, user_prompt: str, app_instance: typer.Typer
    ) -> Dict[str, Any]:
        """
        Sends the schema + user prompt to LLM and gets a JSON command back.
        """
        if not self.client:
            raise MaxError(
                "Missing AI Configuration.\n"
                "Please set OPENAI_API_KEY in your .env file."
            )

        # 1. Get the dynamic capabilities of the tool
        available_tools = self.generate_cli_schema(app_instance)

        # 2. Build the System Prompt
        # We explicitly ask for JSON and use 'response_format' in the API call
        system_message = f"""
You are "Max", an intelligent CLI wrapper.
Your goal is to translate natural language user requests into a specific Shell Command based on the available tools below.

{available_tools}

INSTRUCTIONS:
1. Analyze the user's request.
2. Map it to the most appropriate 'Command' from the list above.
3. Extract arguments (like paths, numbers, booleans).
4. Return ONLY a valid JSON object.

JSON STRUCTURE:
{{
    "thought": "Brief reasoning of why you chose this command.",
    "command": "The exact shell command to run (e.g., 'max images compress ./pic -q 50')",
    "dangerous": true/false (true if it deletes/overwrites/renames files)
}}

If the request is unrelated to the tools or ambiguous, return:
{{ "error": "I cannot handle this request with current tools." }}
        """

        # 3. Call LLM
        try:
            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ],
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            # Handle specific API errors if needed, but generic catch is safer for CLI
            raise MaxError(f"AI Provider Error: {str(e)}")

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
