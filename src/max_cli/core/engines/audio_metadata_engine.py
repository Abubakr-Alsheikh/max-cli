from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from max_cli.common.transaction_log import TransactionLog


SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav"}


class AudioMetadataEngine:
    """
    Engine for reading, writing, and clearing audio file metadata.
    Supports MP3, FLAC, M4A/AAC, OGG, and WAV files.
    """

    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Retrieve all metadata from an audio file.
        Returns all raw frame keys plus convenience names for known fields.
        """
        from mutagen._file import File as MutagenFile

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

        ID3_CONVENIENCE = {
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TPE2": "albumartist",
            "TCON": "genre",
            "TDRC": "date",
            "TRCK": "tracknumber",
            "TPOS": "discnumber",
            "TCOM": "composer",
            "COMM": "comment",
        }

        for frame_id in sorted(audio.keys()):
            if frame_id.startswith("APIC"):
                continue
            try:
                value = audio.get(frame_id)
            except Exception:
                value = None
            if value is not None:
                val_str = str(value)
                short = frame_id.split(":")[0]
                if short in ID3_CONVENIENCE:
                    metadata[ID3_CONVENIENCE[short]] = val_str
                else:
                    metadata[frame_id] = val_str

        if hasattr(audio, "info"):
            metadata["duration"] = round(audio.info.length, 2)
            metadata["bitrate"] = getattr(audio.info, "bitrate", None)
            metadata["sample_rate"] = getattr(audio.info, "sample_rate", None)
            metadata["channels"] = getattr(audio.info, "channels", None)

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
        from mutagen._file import File as MutagenFile

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
        from mutagen._file import File as MutagenFile

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
            audio.info.length

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

    def organize(
        self,
        source_paths: List[Path],
        target_dir: Path,
        pattern: str = "artist",
        transaction_log: Optional["TransactionLog"] = None,
        filter_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Organize audio files into folders by metadata.

        Args:
            source_paths: List of audio files to organize
            target_dir: Root directory to organize into
            pattern: Folder structure - 'artist', 'album', 'artist-album', 'genre', 'contributing-artists'
            filter_value: If set, only move files whose destination folder name matches this value

        Returns:
            Dict with 'moved', 'skipped', 'errors' counts and details
        """
        moved: List[str] = []
        skipped: List[str] = []
        errors: List[str] = []

        for file_path in source_paths:
            try:
                if not file_path.exists():
                    errors.append(f"{file_path.name}: File not found")
                    continue

                metadata = self.get_metadata(file_path)

                artist = metadata.get("artist") or "Unknown Artist"
                album = metadata.get("album") or "Unknown Album"
                genre = metadata.get("genre") or "Unknown Genre"
                albumartist = metadata.get("albumartist") or ""
                title = metadata.get("title") or file_path.stem

                artist = self._sanitize_filename(artist)
                album = self._sanitize_filename(album)
                genre = self._sanitize_filename(genre)
                albumartist = self._sanitize_filename(albumartist)
                title = self._sanitize_filename(title)

                if pattern == "artist":
                    dest_dir = target_dir / artist
                elif pattern == "album":
                    dest_dir = target_dir / album
                elif pattern == "genre":
                    dest_dir = target_dir / genre
                elif pattern == "contributing-artists":
                    contrib = metadata.get("albumartist") or ""
                    if not contrib:
                        contrib = metadata.get("artist") or ""
                    if not contrib:
                        title_val = metadata.get("title") or ""
                        if " - " in title_val:
                            contrib = title_val.split(" - ")[0].strip()
                    if not contrib:
                        if " - " in file_path.stem:
                            contrib = file_path.stem.split(" - ")[0].strip()
                    if not contrib:
                        contrib = "Unknown Artist"
                    folder = self._sanitize_filename(contrib)
                    dest_dir = target_dir / folder
                else:
                    dest_dir = target_dir / artist / album

                if filter_value is not None and dest_dir.name != filter_value:
                    skipped.append(f"{file_path.name} (filter: {filter_value})")
                    continue

                dest_dir.mkdir(parents=True, exist_ok=True)

                new_name = f"{title}{file_path.suffix}"
                dest_path = dest_dir / new_name
                counter = 1
                while dest_path.exists():
                    new_name = f"{title} ({counter}){file_path.suffix}"
                    dest_path = dest_dir / new_name
                    counter += 1

                if transaction_log:
                    from max_cli.common.transaction_log import TransactionLog

                    transaction_log.record(
                        op_type=TransactionLog.OP_MOVE,
                        original_path=file_path,
                        new_path=dest_path,
                    )

                file_path.rename(dest_path)
                moved.append(f"{file_path.name} -> {dest_path}")

            except Exception as e:
                errors.append(f"{file_path.name}: {str(e)}")

        return {
            "moved": moved,
            "skipped": skipped,
            "errors": errors,
            "total_moved": len(moved),
            "total_skipped": len(skipped),
            "total_errors": len(errors),
        }

    def _sanitize_filename(self, name: str) -> str:
        """Remove invalid characters from folder/file names."""
        if not name:
            return "Unknown"

        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")

        name = name.strip()
        return name if name else "Unknown"
