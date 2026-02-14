import fitz  # PyMuPDF  # type: ignore[import-untyped]
from pathlib import Path
from typing import List
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
                img = img.convert("RGB")  # type: ignore[assignment]

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

    def split_pdf(self, input_path: Path, output_path: Path, page_ranges: str) -> int:
        """
        Extracts specific pages from a PDF.
        page_ranges example: "1-5,8,11-15" (1-based indexing for user, converted to 0-based).
        """
        doc = fitz.open(input_path)
        new_doc = fitz.open()

        # Parse logic: "1-3, 5" -> [0, 1, 2, 4]
        pages_to_keep: set[int] = set()
        parts = page_ranges.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-"))
                # Adjust 1-based to 0-based
                pages_to_keep.update(range(start - 1, end))
            else:
                pages_to_keep.add(int(part) - 1)

        sorted_pages = sorted(list(pages_to_keep))

        # Validate
        if any(p >= len(doc) or p < 0 for p in sorted_pages):
            raise ValueError(f"Page range out of bounds. Doc has {len(doc)} pages.")

        for p_idx in sorted_pages:
            new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)

        new_doc.save(output_path)
        count = len(new_doc)
        new_doc.close()
        doc.close()
        return count

    def get_page_count(self, input_path: Path) -> int:
        """Returns the total number of pages in a PDF."""
        with fitz.open(input_path) as doc:
            return doc.page_count

    def split_by_range(
        self,
        input_path: Path,
        output_path: Path,
        start: int = 1,
        end: int = -1,
        keep: bool = True,
    ) -> int:
        """
        Extract or remove a range of pages.

        Args:
            input_path: Source PDF
            output_path: Destination PDF
            start: Start page (1-based, inclusive)
            end: End page (1-based, inclusive, -1 for last page)
            keep: If True, keep the range; If False, remove the range

        Returns:
            Number of pages in output
        """
        with fitz.open(input_path) as doc:
            total_pages = doc.page_count

            # Resolve end to last page if -1
            if end == -1 or end > total_pages:
                end = total_pages

            # Validate range
            if start < 1 or start > end or end > total_pages:
                raise ValueError(
                    f"Invalid range: {start}-{end}. Document has {total_pages} pages."
                )

            # Convert to 0-based indices
            start_idx = start - 1
            end_idx = end - 1

            new_doc = fitz.open()

            if keep:
                # Keep only the specified range
                for p_idx in range(start_idx, end_idx + 1):
                    new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)
            else:
                # Remove the specified range, keep everything else
                for p_idx in range(total_pages):
                    if p_idx < start_idx or p_idx > end_idx:
                        new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)

            new_doc.save(output_path)
            count = len(new_doc)
            new_doc.close()

        return count

    def split_into_chunks(
        self,
        input_path: Path,
        output_dir: Path,
        chunk_size: int = 10,
    ) -> List[Path]:
        """
        Split a PDF into multiple files of chunk_size pages each.

        Args:
            input_path: Source PDF
            output_dir: Directory for output files
            chunk_size: Number of pages per chunk

        Returns:
            List of output file paths
        """
        with fitz.open(input_path) as doc:
            total_pages = doc.page_count
            stem = input_path.stem

            output_files = []

            for chunk_num in range(0, total_pages, chunk_size):
                new_doc = fitz.open()

                # Calculate chunk range
                start_idx = chunk_num
                end_idx = min(chunk_num + chunk_size, total_pages)

                for p_idx in range(start_idx, end_idx):
                    new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)

                # Generate output filename
                chunk_start = chunk_num + 1
                chunk_end = end_idx
                output_name = f"{stem}_p{chunk_start}-{chunk_end}.pdf"
                output_path = output_dir / output_name

                new_doc.save(output_path)
                new_doc.close()
                output_files.append(output_path)

        return output_files

    def watermark_pdf(
        self,
        input_path: Path,
        output_path: Path,
        text: str = "DRAFT",
        opacity: float = 0.3,
        rotation: int = 45,
    ) -> None:
        """
        Overlays text on the center of every page.
        """
        doc = fitz.open(input_path)

        for page in doc:
            # Calculate center
            rect = page.rect
            center = fitz.Point(rect.width / 2, rect.height / 2)

            # Insert Text
            page.insert_text(
                center,
                text,
                fontsize=60,
                fontname="helv",
                color=(0.5, 0.5, 0.5),  # Grey
                fill_opacity=opacity,
                rotate=0,
            )

        doc.save(output_path)
        doc.close()

    def set_password(self, input_path: Path, output_path: Path, password: str) -> None:
        """
        Encrypts the PDF with a user password.
        """
        doc = fitz.open(input_path)
        # permit functionality: print, copy, etc.
        perm = int(
            fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY
        )
        doc.save(
            output_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,  # Strong encryption
            user_pw=password,
            permissions=perm,
        )
        doc.close()

    def extract_assets(
        self, input_path: Path, output_dir: Path, extract_images: bool = True
    ) -> int:
        """
        Rips images out of the PDF and saves them to a folder.
        Returns count of extracted items.
        """
        doc = fitz.open(input_path)
        count = 0

        if extract_images:
            for page_index in range(len(doc)):
                page = doc[page_index]
                image_list = page.get_images()

                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image["ext"]

                    filename = f"page{page_index + 1}_img{img_index + 1}.{ext}"
                    (output_dir / filename).write_bytes(image_bytes)
                    count += 1

        doc.close()
        return count
