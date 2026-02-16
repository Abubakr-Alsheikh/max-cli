from pathlib import Path
from typing import List, Dict, Any
from max_cli.common.exceptions import ResourceNotFoundError


class FileOrganizer:
    """
    Core logic for organizing and renaming files.
    """

    def scan_directory(self, folder: Path) -> List[Path]:
        """Returns a sorted list of files in the folder (excluding subfolders)."""
        if not folder.exists() or not folder.is_dir():
            raise ResourceNotFoundError(f"Folder '{folder}' not found.")

        # Get all files, exclude directories
        files = [f for f in folder.iterdir() if f.is_file()]

        # Sort alphabetically so the ordering is deterministic
        files.sort(key=lambda f: f.name.lower())
        return files

    def order_files(
        self, folder: Path, dry_run: bool = False, start_index: int = 1
    ) -> Dict[str, Any]:
        """
        Renames files by prepending numbers (1_file.txt, 2_file.txt).
        Returns statistics about the operation.
        """
        files = self.scan_directory(folder)
        renamed_count = 0
        skipped_count = 0
        actions = []  # Log of what happened/would happen

        current_index = start_index

        for file_path in files:
            original_name = file_path.name

            # 1. Safety Check: Skip if already numbered (e.g., "1_document.pdf")
            # We check if the bit before the first underscore is a digit
            parts = original_name.split("_")
            if len(parts) > 1 and parts[0].isdigit():
                skipped_count += 1
                continue

            # 2. Construct new name
            new_name = f"{current_index}_{original_name}"
            new_path = folder / new_name

            # 3. Perform Rename (or Simulate)
            if dry_run:
                actions.append(
                    f"[DRY RUN] Would rename '{original_name}' -> '{new_name}'"
                )
            else:
                try:
                    file_path.rename(new_path)
                    actions.append(f"Renamed '{original_name}' -> '{new_name}'")
                except OSError as e:
                    actions.append(f"[Error] Could not rename '{original_name}': {e}")
                    continue

            renamed_count += 1
            current_index += 1

        return {
            "total_files": len(files),
            "renamed": renamed_count,
            "skipped": skipped_count,
            "actions": actions,
        }

    def find_duplicates(
        self, folder: Path, recursive: bool = False
    ) -> Dict[str, List[Path]]:
        """
        Find duplicate files based on content hash.

        Returns:
            Dictionary mapping hash to list of duplicate file paths
        """
        import hashlib

        if not folder.exists() or not folder.is_dir():
            raise ResourceNotFoundError(f"Folder '{folder}' not found.")

        hash_map: Dict[str, List[Path]] = {}

        if recursive:
            files = [f for f in folder.rglob("*") if f.is_file()]
        else:
            files = [f for f in folder.iterdir() if f.is_file()]

        for file_path in files:
            try:
                with open(file_path, "rb") as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                if file_hash in hash_map:
                    hash_map[file_hash].append(file_path)
                else:
                    hash_map[file_hash] = [file_path]
            except OSError:
                continue

        duplicates = {k: v for k, v in hash_map.items() if len(v) > 1}
        return duplicates

    def secure_delete(self, path: Path, passes: int = 3) -> bool:
        """
        Securely delete a file by overwriting with random data.

        Args:
            path: File to securely delete
            passes: Number of overwrite passes (default 3)

        Returns:
            True if successful
        """
        import os

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if path.is_dir():
            raise ValueError("Cannot securely delete directories")

        file_size = path.stat().st_size

        try:
            with open(path, "ba+") as f:
                for _ in range(passes):
                    f.seek(0)
                    f.write(os.urandom(file_size))
                    f.flush()
                    os.fsync(f.fileno())

            path.unlink()
            return True
        except OSError as e:
            raise OSError(f"Secure delete failed: {e}")
