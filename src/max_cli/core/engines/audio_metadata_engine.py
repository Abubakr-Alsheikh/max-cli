from pathlib import Path
from typing import Dict, Optional, Any, List
from mutagen import File as MutagenFile


SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav"}


class AudioMetadataEngine:
    """
    Engine for reading, writing, and clearing audio file metadata.
    Supports MP3, FLAC, M4A/AAC, OGG, and WAV files.
    """

    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Retrieve all metadata from an audio file.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {file_path.suffix}. "
                f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        audio = MutagenFile(file_path)

        if audio is None:
            raise ValueError(f"Unable to read metadata from: {file_path}")

        metadata: Dict[str, Any] = {}

        metadata["title"] = audio.get("title", [None])[0]
        metadata["artist"] = audio.get("artist", [None])[0]
        metadata["album"] = audio.get("album", [None])[0]
        metadata["albumartist"] = audio.get("albumartist", [None])[0]
        metadata["genre"] = audio.get("genre", [None])[0]
        metadata["date"] = audio.get("date", [None])[0]
        metadata["tracknumber"] = audio.get("tracknumber", [None])[0]
        metadata["discnumber"] = audio.get("discnumber", [None])[0]
        metadata["composer"] = audio.get("composer", [None])[0]
        metadata["comment"] = audio.get("comment", [None])[0]

        if hasattr(audio, "info"):
            metadata["duration"] = round(audio.info.length, 2)
            metadata["bitrate"] = getattr(audio.info, "bitrate", None)
            metadata["sample_rate"] = getattr(audio.info, "sample_rate", None)
            metadata["channels"] = getattr(audio.info, "channels", None)

        for key in list(metadata.keys()):
            if metadata[key] is None:
                del metadata[key]

        return metadata

    def set_metadata(
        self,
        file_path: Path,
        output_path: Optional[Path] = None,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        albumartist: Optional[str] = None,
        genre: Optional[str] = None,
        date: Optional[str] = None,
        tracknumber: Optional[str] = None,
        discnumber: Optional[str] = None,
        composer: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Path:
        """
        Set metadata on an audio file.
        If output_path is provided, writes to a new file; otherwise modifies in place.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        target = output_path if output_path else file_path

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {file_path.suffix}. "
                f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        audio = MutagenFile(file_path)

        if audio is None:
            raise ValueError(f"Unable to read file: {file_path}")

        if title is not None:
            audio["title"] = title
        if artist is not None:
            audio["artist"] = artist
        if album is not None:
            audio["album"] = album
        if albumartist is not None:
            audio["albumartist"] = albumartist
        if genre is not None:
            audio["genre"] = genre
        if date is not None:
            audio["date"] = date
        if tracknumber is not None:
            audio["tracknumber"] = tracknumber
        if discnumber is not None:
            audio["discnumber"] = discnumber
        if composer is not None:
            audio["composer"] = composer
        if comment is not None:
            audio["comment"] = comment

        audio.save(target)
        return target

    def clear_metadata(
        self,
        file_path: Path,
        output_path: Optional[Path] = None,
        keep_duration: bool = True,
    ) -> Path:
        """
        Clear all metadata from an audio file.
        If keep_duration is True, preserves audio info (duration, bitrate, etc.).
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        target = output_path if output_path else file_path

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {file_path.suffix}. "
                f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        audio = MutagenFile(file_path)

        if audio is None:
            raise ValueError(f"Unable to read file: {file_path}")

        if keep_duration and hasattr(audio, "info"):
            audio.info.length  # Verify we can read info without storing

        tags_to_remove = list(audio.keys())
        for key in tags_to_remove:
            del audio[key]

        audio.save(target)

        return target

    def batch_set_metadata(
        self,
        file_paths: List[Path],
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        albumartist: Optional[str] = None,
        genre: Optional[str] = None,
        date: Optional[str] = None,
        tracknumber: Optional[str] = None,
        discnumber: Optional[str] = None,
        composer: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> List[Path]:
        """
        Set the same metadata on multiple audio files.
        Useful for organizing a batch of files under the same album/artist.
        """
        results: List[Path] = []

        for path in file_paths:
            try:
                result = self.set_metadata(
                    path,
                    title=title,
                    artist=artist,
                    album=album,
                    albumartist=albumartist,
                    genre=genre,
                    date=date,
                    tracknumber=tracknumber,
                    discnumber=discnumber,
                    composer=composer,
                    comment=comment,
                )
                results.append(result)
            except Exception as e:
                raise RuntimeError(f"Failed to set metadata on {path}: {e}")

        return results

    def auto_tag_from_filename(
        self,
        file_path: Path,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Attempt to extract metadata from filename patterns.
        Common pattern: "Artist - Title.ext" or "Track - Artist - Title.ext"
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        stem = file_path.stem
        parts = stem.split(" - ")

        title = None
        artist = None

        if len(parts) >= 2:
            artist = parts[0].strip()
            title = parts[1].strip()
        elif len(parts) == 1:
            title = parts[0].strip()

        return self.set_metadata(
            file_path,
            output_path,
            title=title,
            artist=artist,
        )
