"""What kind of file a path is, from its suffix: video, audio, image, PDF ...

One table for every part of Max that sorts files by kind: the dashboard's
Files page counts a folder's files with it, Browse shows a page's own files,
and a page offers to open a file of another kind on that kind's page.
"""

from pathlib import Path

VIDEO = "video"
AUDIO = "audio"
IMAGE = "image"
PDF = "pdf"
DOCUMENT = "document"
ARCHIVE = "archive"
OTHER = "other"

KIND_SUFFIXES: dict[str, frozenset[str]] = {
    VIDEO: frozenset({".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}),
    AUDIO: frozenset(
        {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
    ),
    IMAGE: frozenset(
        {
            ".jpg",
            ".jpeg",
            ".jfif",
            ".png",
            ".bmp",
            ".gif",
            ".webp",
            ".avif",
            ".tiff",
            ".tif",
            ".ico",
            ".svg",
            ".heic",
            ".heif",
            ".tga",
            ".psd",
        }
    ),
    PDF: frozenset({".pdf"}),
    DOCUMENT: frozenset(
        {
            ".doc",
            ".docx",
            ".odt",
            ".rtf",
            ".txt",
            ".md",
            ".xls",
            ".xlsx",
            ".csv",
            ".ppt",
            ".pptx",
        }
    ),
    ARCHIVE: frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}),
}
_KIND_OF_SUFFIX = {
    suffix: kind for kind, suffixes in KIND_SUFFIXES.items() for suffix in suffixes
}


def kind_of(path: Path) -> str:
    """The kind of file `path` names, or OTHER. Reads only the name."""
    return _KIND_OF_SUFFIX.get(path.suffix.lower(), OTHER)
