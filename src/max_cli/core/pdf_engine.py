import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple
from PIL import Image
import io

class PDFEngine:
    """
    Core logic for PDF manipulation using PyMuPDF and Pillow.
    """

    def merge_pdfs(self, input_paths: List[Path], output_path: Path) -> int:
        """
        Combines multiple PDF files into one.
        Returns the total number of pages in the merged document.
        """
        result_pdf = fitz.open()
        total_pages = 0

        for path in input_paths:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            try:
                with fitz.open(path) as src:
                    result_pdf.insert_pdf(src)
                    total_pages += src.page_count
            except Exception as e:
                # We log/raise here depending on strictness. 
                # For now, let's propagate the error to the CLI to handle.
                raise RuntimeError(f"Failed to merge '{path.name}': {e}")

        # Garbage=4 removes unused objects to keep file size small
        result_pdf.save(output_path, garbage=4, deflate=True)
        result_pdf.close()
      
        return total_pages

    def compress_pdf(
        self, input_path: Path, output_path: Path, dpi: int = 150, quality: int = 80
    ) -> int:
        """
        Compresses a PDF by rasterizing pages to JPEG and rebuilding the PDF.
        Returns the number of pages processed.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        try:
            doc = fitz.open(input_path)
        except Exception:
            raise ValueError(f"Could not open PDF: {input_path.name}")

        page_count = len(doc)
        img_list = []

        # Process pages
        for page_index in range(page_count):
            page = doc.load_page(page_index)
          
            # Render page to image (PixMap)
            pix = page.get_pixmap(dpi=dpi)
          
            # Convert to PIL Image
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))

            # Ensure RGB for JPEG
            if img.mode != "RGB":
                img = img.convert("RGB")
          
            img_list.append(img)

        doc.close()

        if not img_list:
            raise ValueError(f"PDF '{input_path.name}' was empty or could not be read.")

        # Save logic
        try:
            img_list[0].save(
                output_path,
                "PDF",
                resolution=float(dpi),
                save_all=True,
                append_images=img_list[1:],
                quality=quality,
                optimize=True,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to save compressed PDF: {e}")

        return page_count