import segno
import pyperclip
from pathlib import Path


class SystemEngine:
    """
    Handles System interactions: Clipboard and QR generation.
    """

    def generate_qr(self, data: str) -> None:
        """
        Generates a compact ASCII QR code and prints it directly to stdout.
        """
        qr = segno.make(data)
        # 'compact=True' makes it render nicely in most terminals (black/white blocks)
        print("")  # Add spacing
        qr.terminal(compact=True)
        print("")

    def save_clipboard_image(self, output_path: Path) -> None:
        """
        Grabs image data from the system clipboard and saves it to disk.
        """
        from PIL import ImageGrab

        content = ImageGrab.grabclipboard()

        if content is None:
            raise ValueError("Clipboard is empty.")

        # Check if it's an actual Image object (pixel data)
        if hasattr(content, "save"):
            content.save(output_path)
        else:
            raise ValueError(
                "Clipboard does not contain image data (maybe text or files?)."
            )

    def copy_file_to_clipboard(self, input_path: Path) -> None:
        """
        Reads a text file and copies its content to the system clipboard.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        try:
            # Attempt to read as text
            text = input_path.read_text(encoding="utf-8")
            pyperclip.copy(text)
        except UnicodeDecodeError:
            raise ValueError(
                "File appears to be binary (not text). Cannot copy to clipboard."
            )
        except Exception as e:
            raise RuntimeError(f"Clipboard error: {e}")
