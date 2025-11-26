import fitz  # PyMuPDF
from pathlib import Path
from typing import List 
from PIL import Image
import io


class PDFEngine:
    """
    Core logic for PDF manipulation using PyMuPDF and Pillow.
    """

    def merge_pdfs(self, input_paths: List[Path], output_path: Path) -> None:
        """
        Combines multiple PDF files into one.
        """
        result_pdf = fitz.open()

        for path in input_paths:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            # Open source PDF
            with fitz.open(path) as src:
                result_pdf.insert_pdf(src)

        # Garbage=4 removes unused objects to keep file size small
        result_pdf.save(output_path, garbage=4, deflate=True)
        result_pdf.close()

    def compress_pdf(
        self, input_path: Path, output_path: Path, dpi: int = 150, quality: int = 80
    ) -> int:
        """
        Compresses a PDF by rasterizing pages to JPEG and rebuilding the PDF.
        Returns the number of pages processed.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)
        page_count = len(doc)

        # We will store PIL Images in memory before saving
        # WARNING: For massive PDFs (500+ pages), this approach consumes RAM.
        # For a CLI tool, it's usually acceptable, but strictly scalable systems
        # might write temp files to disk. We'll use memory for speed here.
        img_list = []

        for page_index in range(page_count):
            page = doc.load_page(page_index)

            # 1. Render page to image (PixMap)
            pix = page.get_pixmap(dpi=dpi)

            # 2. Convert to PIL Image
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))

            # 3. Ensure RGB for JPEG
            if img.mode != "RGB":
                img = img.convert("RGB")

            img_list.append(img)

        doc.close()

        if not img_list:
            raise ValueError("PDF was empty or could not be read.")

        # 4. Save first image and append the rest as a PDF
        img_list[0].save(
            output_path,
            "PDF",
            resolution=float(dpi),
            save_all=True,
            append_images=img_list[1:],
            quality=quality,
            optimize=True,
        )

        return page_count
