from typing import Any, Literal, Optional, TypedDict

FieldType = Literal[
    "str",
    "int",
    "float",
    "bool",
    "select",
    "path",
    "path_output",
    "path_folder",
    "password",
]


class FieldSchema(TypedDict):
    name: str
    type: str
    label: str
    required: bool
    default: Any
    options: Optional[list[str]]
    help: str


class CommandSchema(TypedDict):
    label: str
    icon: str
    category: str
    engine: str
    method: str
    description: str
    fields: list[FieldSchema]
    has_queue_option: bool


def _f(
    name: str,
    type: str,
    label: str,
    required: bool = False,
    default: Any = None,
    options: Optional[list[str]] = None,
    help: str = "",
) -> FieldSchema:
    return {
        "name": name,
        "type": type,
        "label": label,
        "required": required,
        "default": default,
        "options": options,
        "help": help,
    }


COMMANDS: dict[str, dict[str, CommandSchema]] = {
    "ai": {
        "ask": {
            "label": "Ask AI",
            "icon": "\U0001f916",
            "category": "ai",
            "engine": "AIEngine",
            "method": "interpret_intent",
            "description": "Ask AI to generate a Max CLI command",
            "has_queue_option": False,
            "fields": [
                _f(
                    "prompt",
                    "str",
                    "Question",
                    required=True,
                    help="Describe what you want to do",
                ),
                _f("explain", "bool", "Explain Output", default=False),
            ],
        },
        "chat": {
            "label": "AI Chat",
            "icon": "\U0001f4ac",
            "category": "ai",
            "engine": "AIEngine",
            "method": "chat",
            "description": "Open interactive chat with AI",
            "has_queue_option": False,
            "fields": [],
        },
    },
}


# `video` and `grab` moved to the command catalog (core/catalog); the Tools
# and Download pages use it.
CATEGORIES: list[str] = ["audio", "ai"]


class CommandRegistry:
    @classmethod
    def get_categories(cls) -> list[str]:
        return list(CATEGORIES)

    @classmethod
    def get_commands(cls, category: str) -> dict[str, CommandSchema]:
        return COMMANDS.get(category, {})

    @classmethod
    def get_command(cls, category: str, command: str) -> Optional[CommandSchema]:
        return COMMANDS.get(category, {}).get(command)

    @classmethod
    def get_all_commands(cls) -> dict[str, dict[str, CommandSchema]]:
        return COMMANDS

    @classmethod
    def get_field_default(cls, field: FieldSchema) -> Any:
        return field.get("default")

    @classmethod
    def validate_fields(
        cls, command: CommandSchema, values: dict
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for field in command["fields"]:
            value = values.get(field["name"])
            if field["required"] and (
                value is None or (isinstance(value, str) and not value.strip())
            ):
                errors.append(f"Field '{field['label']}' is required")
            if value is not None:
                field_type = field["type"]
                if field_type == "int":
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors.append(f"Field '{field['label']}' must be an integer")
                elif field_type == "float":
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors.append(f"Field '{field['label']}' must be a number")
                elif field_type == "select" and field["options"]:
                    if value not in field["options"]:
                        errors.append(
                            f"Field '{field['label']}' must be one of: {', '.join(field['options'])}"
                        )
        return (len(errors) == 0, errors)
