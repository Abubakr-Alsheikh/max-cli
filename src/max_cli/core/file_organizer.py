from pathlib import Path
import shutil


class FileOrganizer:
    def order_files(self, folder: Path) -> int:
        """
        Renames files 1_file, 2_file. Returns count of renamed files.
        """
        if not folder.is_dir():
            raise NotADirectoryError(f"{folder} is not a directory")

        # Filter files only and sort alphabetically
        files = sorted([f for f in folder.iterdir() if f.is_file()])

        count = 0
        for i, file_path in enumerate(files, start=1):
            # Skip if already matches pattern "digit_"
            parts = file_path.name.split("_")
            if parts[0].isdigit():
                continue

            new_name = f"{i}_{file_path.name}"
            new_path = folder / new_name

            file_path.rename(new_path)
            count += 1

        return count
