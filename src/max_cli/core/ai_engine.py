import json
import typer
from typing import Dict, Any 
from openai import OpenAI
from max_cli.config import settings
from max_cli.common.exceptions import MaxError


class AIEngine:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            # We don't raise an error immediately, only if they try to use it
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def _extract_command_info(self, name: str, command_info: Any) -> dict:
        """Helper to extract details from a Typer command."""
        return {
            "command": name,
            "description": command_info.help or "No description",
            "usage": f"max {name} [OPTIONS] [ARGS]",  # Simplified for the prompt
        }

    def generate_cli_schema(self, app: typer.Typer, parent_name: str = "max") -> str:
        """
        Dynamically traverses the Typer app to build a documentation string
        for the AI.
        """
        schema_lines = []

        # Access internal Typer structure
        # Typer stores registered groups/commands in .registered_groups and .registered_commands

        # 1. List Sub-Groups (e.g., 'images', 'files', 'pdf')
        for group in app.registered_groups:
            group_name = group.name
            if group.hidden:
                continue

            # Recurse into the sub-typer
            if group.typer_instance:
                for cmd in group.typer_instance.registered_commands:
                    if cmd.hidden:
                        continue
                    full_cmd = f"{parent_name} {group_name} {cmd.name or cmd.callback.__name__}"

                    # Extract arguments roughly (parsing precise args dynamically is complex,
                    # so we rely on the help text which Typer auto-generates usually)
                    help_text = cmd.help or "No help text."
                    schema_lines.append(f"- Command: '{full_cmd}'")
                    schema_lines.append(f"  Description: {help_text}")

        return "\n".join(schema_lines)

    def interpret_intent(
        self, user_prompt: str, app_instance: typer.Typer
    ) -> Dict[str, Any]:
        """
        Sends the schema + user prompt to LLM and gets a JSON command back.
        """
        if not self.client:
            raise MaxError("OPENAI_API_KEY not found in configuration or .env file.")

        # 1. Get the dynamic capabilities of the tool
        available_tools = self.generate_cli_schema(app_instance)

        # 2. Build the System Prompt
        system_message = f"""
You are "Max", an intelligent CLI wrapper.
Your goal is to translate natural language user requests into a specific Shell Command based on the available tools below.

AVAILABLE TOOLS:
{available_tools}

INSTRUCTIONS:
1. Analyze the user's request.
2. Map it to the most appropriate 'Command' from the list above.
3. Extract arguments (like paths, numbers, booleans).
4. Return ONLY a JSON object. Do not write markdown or explanations.

JSON STRUCTURE:
{{
    "thought": "Brief reasoning of why you chose this command.",
    "command": "The exact shell command to run (e.g., 'max images compress ./pic -q 50')",
    "dangerous": true/false (true if it deletes/overwrites files, like 'order' or 'organize')
}}

If the request is unrelated to the tools, return:
{{ "error": "I cannot handle this request with current tools." }}
        """

        # 3. Call OpenAI
        try:
            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            raise MaxError(f"AI Communication failed: {str(e)}")
