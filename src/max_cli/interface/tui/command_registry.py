from typing import Any, Literal, Optional, TypedDict

from max_cli.config import settings
from max_cli.core import presets

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
    "grab": {
        "download": {
            "label": "Download Media",
            "icon": "\u2b07",
            "category": "grab",
            "engine": "NetworkEngine",
            "method": "download_media",
            "description": "Download video or audio from a URL",
            "has_queue_option": True,
            "fields": [
                _f(
                    "url",
                    "str",
                    "URL",
                    required=True,
                    help="YouTube, Vimeo, or other supported URL",
                ),
                _f("audio_only", "bool", "Audio Only", default=False),
                _f(
                    "quality",
                    "select",
                    "Quality",
                    default="h",
                    options=["ss", "s", "m", "h", "x"],
                ),
                _f("resolution", "int", "Resolution", help="Custom height in pixels"),
                _f("subtitles", "bool", "Subtitles", default=False),
                _f("include_metadata", "bool", "Include Metadata", default=True),
                _f(
                    "output_path",
                    "path_folder",
                    "Output Directory",
                    default="~/Max Downloads",
                ),
                _f("queue", "bool", "Add to Queue", default=False),
            ],
        },
    },
    "images": {
        "compress": {
            "label": "Compress Image",
            "icon": "\U0001f5bc",
            "category": "images",
            "engine": "ImageEngine",
            "method": "process_single_image",
            "description": "Compress a single image",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input Image", required=True),
                _f("output", "path_output", "Output Image"),
                _f("quality", "int", "Quality", default=settings.DEFAULT_QUALITY),
                _f("scale", "int", "Scale (%)", help="Resize percentage"),
                _f(
                    "max_dim",
                    "int",
                    "Max Dimension",
                    help="Maximum width/height in pixels",
                ),
                _f("force_jpeg", "bool", "Force JPEG", default=False),
                _f("quantize", "bool", "Quantize Colors", default=False),
                _f(
                    "strip",
                    "bool",
                    "Strip Metadata",
                    default=presets.STRIP_IMAGE_METADATA,
                ),
            ],
        },
        "resize": {
            "label": "Resize Image",
            "icon": "\U0001f4d0",
            "category": "images",
            "engine": "ImageEngine",
            "method": "process_single_image",
            "description": "Resize a single image",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input Image", required=True),
                _f("output", "path_output", "Output Image"),
                _f("width", "int", "Width (px)"),
                _f("height", "int", "Height (px)"),
                _f("scale", "int", "Scale (%)"),
            ],
        },
        "convert": {
            "label": "Convert Image",
            "icon": "\U0001f504",
            "category": "images",
            "engine": "ImageEngine",
            "method": "process_single_image",
            "description": "Convert image to a different format",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input Image", required=True),
                _f("output", "path_output", "Output Image"),
                _f(
                    "to_format",
                    "select",
                    "Output Format",
                    required=True,
                    options=["webp", "jpg", "png"],
                ),
            ],
        },
        "strip": {
            "label": "Strip EXIF",
            "icon": "\U0001f9f9",
            "category": "images",
            "engine": "ImageEngine",
            "method": "process_single_image",
            "description": "Remove EXIF metadata from image",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input Image", required=True),
                _f("strip_exif", "bool", "Strip EXIF", default=True),
            ],
        },
    },
    "files": {
        "order": {
            "label": "Order Files",
            "icon": "\U0001f522",
            "category": "files",
            "engine": "FileOrganizer",
            "method": "order_files",
            "description": "Rename files with sequential numbers",
            "has_queue_option": False,
            "fields": [
                _f("folder", "path_folder", "Target Directory", required=True),
                _f("dry_run", "bool", "Dry Run", default=True),
                _f("start", "int", "Start Number", default=1),
            ],
        },
        "smart_sort": {
            "label": "Smart Sort Files",
            "icon": "\U0001f4c1",
            "category": "files",
            "engine": "FileOrganizer",
            "method": "smart_sort",
            "description": "Organize files into categorized folders",
            "has_queue_option": False,
            "fields": [
                _f("path", "path_folder", "Target Directory", required=True),
                _f("dry_run", "bool", "Dry Run", default=True),
            ],
        },
        "duplicates": {
            "label": "Find Duplicates",
            "icon": "\U0001f50d",
            "category": "files",
            "engine": "FileOrganizer",
            "method": "find_duplicates",
            "description": "Find duplicate files by content hash",
            "has_queue_option": False,
            "fields": [
                _f("folder", "path_folder", "Target Directory", required=True),
                _f("recursive", "bool", "Search Subdirectories", default=False),
                _f("delete", "bool", "Delete Duplicates", default=False),
            ],
        },
        "shred": {
            "label": "Secure Delete",
            "icon": "\U0001f512",
            "category": "files",
            "engine": "FileOrganizer",
            "method": "secure_delete",
            "description": "Securely delete files with multiple overwrite passes",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Target File", required=True),
                _f("passes", "int", "Overwrite Passes", default=3),
            ],
        },
        "backup": {
            "label": "Create Backup",
            "icon": "\U0001f4be",
            "category": "files",
            "engine": "FileOrganizer",
            "method": "create_backup",
            "description": "Create a backup of a file",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Target File", required=True),
                _f("label", "str", "Backup Label", default="manual"),
            ],
        },
    },
    "pdf": {
        "merge": {
            "label": "Merge PDFs",
            "icon": "\U0001f4c4",
            "category": "pdf",
            "engine": "PDFEngine",
            "method": "merge_pdfs",
            "description": "Combine multiple PDFs into one",
            "has_queue_option": False,
            "fields": [
                _f("inputs", "path_folder", "Input PDFs", required=True),
                _f("output", "path_output", "Output PDF", required=True),
            ],
        },
        "compress": {
            "label": "Compress PDF",
            "icon": "\U0001f4e6",
            "category": "pdf",
            "engine": "PDFEngine",
            "method": "compress_pdf",
            "description": "Compress PDF by rasterizing pages",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input PDF", required=True),
                _f("dpi", "int", "DPI", default=presets.PDF_COMPRESS_DPI),
                _f(
                    "quality",
                    "int",
                    "JPEG Quality",
                    default=presets.PDF_COMPRESS_QUALITY,
                ),
            ],
        },
        "split": {
            "label": "Split PDF",
            "icon": "\u2702",
            "category": "pdf",
            "engine": "PDFEngine",
            "method": "split_pdf",
            "description": "Extract specific pages from a PDF",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Input PDF", required=True),
                _f("start", "int", "Start Page"),
                _f("end", "int", "End Page"),
                _f("output", "path_output", "Output PDF"),
            ],
        },
        "split_range": {
            "label": "Split PDF by Range",
            "icon": "\u2702",
            "category": "pdf",
            "engine": "PDFEngine",
            "method": "split_by_range",
            "description": "Extract or remove a page range from a PDF",
            "has_queue_option": False,
            "fields": [
                _f("input_path", "path", "Input PDF", required=True),
                _f("start", "int", "Start Page", required=True),
                _f("end", "int", "End Page", required=True),
                _f("keep", "bool", "Keep Range (uncheck to remove)", default=True),
                _f("output_path", "path_output", "Output PDF"),
            ],
        },
    },
    "audio": {
        "set": {
            "label": "Set Audio Metadata",
            "icon": "\U0001f3f7",
            "category": "audio",
            "engine": "AudioMetadataEngine",
            "method": "set_metadata",
            "description": "Set ID3/metadata tags on audio files",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Audio File", required=True),
                _f("title", "str", "Title"),
                _f("artist", "str", "Artist"),
                _f("album", "str", "Album"),
                _f("genre", "str", "Genre"),
                _f("date", "str", "Year"),
                _f("track", "int", "Track Number"),
                _f("composer", "str", "Composer"),
                _f("comment", "str", "Comment"),
            ],
        },
        "organize": {
            "label": "Organize Audio Files",
            "icon": "\U0001f4c2",
            "category": "audio",
            "engine": "AudioMetadataEngine",
            "method": "organize",
            "description": "Organize audio files by metadata tags",
            "has_queue_option": False,
            "fields": [
                _f("targets", "path_folder", "Input Folder", required=True),
                _f("output", "path_folder", "Output Folder"),
                _f(
                    "pattern",
                    "select",
                    "Naming Pattern",
                    default=presets.TUI_AUDIO_ORGANIZE_PATTERN,
                    options=["artist", "album", "genre", "artist-album"],
                ),
            ],
        },
        "get": {
            "label": "Get Audio Metadata",
            "icon": "\U0001f4cb",
            "category": "audio",
            "engine": "AudioMetadataEngine",
            "method": "get_metadata",
            "description": "Display metadata from audio file",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Audio File", required=True),
            ],
        },
        "clear": {
            "label": "Clear Audio Metadata",
            "icon": "\U0001f9f9",
            "category": "audio",
            "engine": "AudioMetadataEngine",
            "method": "clear_metadata",
            "description": "Remove all metadata from audio file",
            "has_queue_option": False,
            "fields": [
                _f("target", "path", "Audio File", required=True),
            ],
        },
        "batch": {
            "label": "Batch Set Metadata",
            "icon": "\U0001f3f7",
            "category": "audio",
            "engine": "AudioMetadataEngine",
            "method": "set_metadata",
            "description": "Set metadata on multiple audio files",
            "has_queue_option": False,
            "fields": [
                _f("targets", "path_folder", "Input Folder", required=True),
                _f("title", "str", "Title"),
                _f("artist", "str", "Artist"),
                _f("album", "str", "Album"),
            ],
        },
    },
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


# `video` moved to the command catalog (core/catalog); the Tools page shows it.
CATEGORIES: list[str] = ["grab", "images", "files", "pdf", "audio", "ai"]


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
