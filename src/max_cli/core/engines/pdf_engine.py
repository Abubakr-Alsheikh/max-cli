from pathlib import Path
from typing import List, Dict, Any


class PDFEngine:
    """
    Core logic for PDF manipulation using PyMuPDF and Pillow.
    """

    def merge_pdfs(self, input_paths: List[Path], output_path: Path) -> int:
        """
        Combines multiple PDF files into one.
        Returns the total number of pages in the merged document.
        """
        import fitz  # type: ignore[import-untyped]

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
                raise RuntimeError(f"Failed to merge '{path.name}': {e}")

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
        import fitz  # type: ignore[import-untyped]
        from PIL import Image
        import io

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        try:
            doc = fitz.open(input_path)
        except Exception:
            raise ValueError(f"Could not open PDF: {input_path.name}")

        page_count = len(doc)
        img_list = []

        for page_index in range(page_count):
            page = doc.load_page(page_index)

            pix = page.get_pixmap(dpi=dpi)

            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))

            if img.mode != "RGB":
                img = img.convert("RGB")  # type: ignore[assignment]

            img_list.append(img)

        doc.close()

        if not img_list:
            raise ValueError(f"PDF '{input_path.name}' was empty or could not be read.")

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
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(input_path)
        new_doc = fitz.open()

        pages_to_keep: set[int] = set()
        parts = page_ranges.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-"))
                pages_to_keep.update(range(start - 1, end))
            else:
                pages_to_keep.add(int(part) - 1)

        sorted_pages = sorted(list(pages_to_keep))

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
        import fitz  # type: ignore[import-untyped]

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
        import fitz  # type: ignore[import-untyped]

        with fitz.open(input_path) as doc:
            total_pages = doc.page_count

            if end == -1 or end > total_pages:
                end = total_pages

            if start < 1 or start > end or end > total_pages:
                raise ValueError(
                    f"Invalid range: {start}-{end}. Document has {total_pages} pages."
                )

            start_idx = start - 1
            end_idx = end - 1

            new_doc = fitz.open()

            if keep:
                for p_idx in range(start_idx, end_idx + 1):
                    new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)
            else:
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
        import fitz  # type: ignore[import-untyped]

        with fitz.open(input_path) as doc:
            total_pages = doc.page_count
            stem = input_path.stem

            output_files = []

            for chunk_num in range(0, total_pages, chunk_size):
                new_doc = fitz.open()

                start_idx = chunk_num
                end_idx = min(chunk_num + chunk_size, total_pages)

                for p_idx in range(start_idx, end_idx):
                    new_doc.insert_pdf(doc, from_page=p_idx, to_page=p_idx)

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
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(input_path)

        for page in doc:
            rect = page.rect
            center = fitz.Point(rect.width / 2, rect.height / 2)

            page.insert_text(
                center,
                text,
                fontsize=60,
                fontname="helv",
                color=(0.5, 0.5, 0.5),
                fill_opacity=opacity,
                rotate=0,
            )

        doc.save(output_path)
        doc.close()

    def set_password(self, input_path: Path, output_path: Path, password: str) -> None:
        """
        Encrypts the PDF with a user password.
        """
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(input_path)
        perm = int(
            fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY
        )
        doc.save(
            output_path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
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
        import fitz  # type: ignore[import-untyped]

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

    def ocr_pdf(self, input_path: Path, output_path: Path, lang: str = "eng") -> str:
        """
        Extract text from PDF using OCR (requires pytesseract and Tesseract installed).

        Args:
            input_path: Input PDF file
            output_path: Output text file (or None to return text only)
            lang: Language code (e.g., 'eng', 'deu', 'fra', 'eng+deu')

        Returns:
            Extracted text
        """
        import fitz  # type: ignore[import-untyped]
        from PIL import Image
        import io

        try:
            import pytesseract
        except ImportError:
            raise RuntimeError(
                "pytesseract is not installed. Install with: pip install max-cli[ocr]\n"
                "Also requires Tesseract OCR installed on your system."
            )

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)
        full_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))

            text = pytesseract.image_to_string(img, lang=lang)
            full_text.append(f"--- Page {page_num + 1} ---\n{text}")

        doc.close()

        result_text = "\n\n".join(full_text)

        if output_path:
            output_path.write_text(result_text, encoding="utf-8")

        return result_text

    def extract_form_data(self, input_path: Path) -> Dict[str, str]:
        """
        Extract data from PDF form fields.

        Returns:
            Dictionary mapping field names to their values
        """
        import fitz  # type: ignore[import-untyped]

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)
        form_data: Dict[str, str] = {}

        for page in doc:
            widgets = page.widgets()
            for widget in widgets:
                if widget.field_name and widget.field_value:
                    form_data[widget.field_name] = widget.field_value

        doc.close()
        return form_data

    def fill_form(
        self, input_path: Path, output_path: Path, field_values: Dict[str, str]
    ) -> None:
        """
        Fill PDF form fields with provided values.

        Args:
            input_path: Source PDF with form
            output_path: Output PDF file
            field_values: Dictionary mapping field names to values
        """
        import fitz  # type: ignore[import-untyped]

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)

        for page in doc:
            widgets = page.widgets()
            for widget in widgets:
                if widget.field_name and widget.field_name in field_values:
                    widget.field_value = field_values[widget.field_name]
                    widget.update()

        doc.save(output_path)
        doc.close()

    def flatten_form(self, input_path: Path, output_path: Path) -> None:
        """
        Flatten PDF form (convert fields to regular content).
        """
        import fitz  # type: ignore[import-untyped]

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)

        for page in doc:
            widgets = page.widgets()
            for widget in widgets:
                if widget.field_type in (
                    fitz.PDF_WIDGET_TYPE_TEXT,
                    fitz.PDF_WIDGET_TYPE_CHECKBOX,
                    fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
                ):
                    widget.field_flags = fitz.PDF_FIELD_IS_READONLY

        doc.save(output_path)
        doc.close()

    def optimize_pdf(
        self,
        input_path: Path,
        output_path: Path,
        remove_unused: bool = True,
        compress_images: bool = True,
        linearize: bool = True,
    ) -> None:
        """
        Optimize PDF by removing unused objects, compressing images, and linearizing.

        Args:
            input_path: Source PDF
            output_path: Output PDF file
            remove_unused: Remove unused objects
            compress_images: Compress images
            linearize: Create web-optimized (linearized) PDF
        """
        import fitz  # type: ignore[import-untyped]

        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        doc = fitz.open(input_path)

        if remove_unused:
            garbage = 4
        else:
            garbage = 0

        deflate = compress_images
        clean = linearize

        doc.save(
            output_path,
            garbage=garbage,
            deflate=deflate,
            clean=clean,
        )
        doc.close()

    def compare_pdfs(self, path1: Path, path2: Path) -> Dict[str, Any]:
        """
        Compare two PDFs and generate a diff report.

        Returns:
            Dictionary with comparison results
        """
        import fitz  # type: ignore[import-untyped]

        if not path1.exists():
            raise FileNotFoundError(f"File not found: {path1}")
        if not path2.exists():
            raise FileNotFoundError(f"File not found: {path2}")

        doc1 = fitz.open(path1)
        doc2 = fitz.open(path2)

        result: Dict[str, Any] = {
            "file1": path1.name,
            "file2": path2.name,
            "pages_equal": True,
            "differences": [],
        }

        if len(doc1) != len(doc2):
            result["pages_equal"] = False
            result["differences"].append(
                f"Page count differs: {len(doc1)} vs {len(doc2)}"
            )

        min_pages = min(len(doc1), len(doc2))

        for i in range(min_pages):
            page1 = doc1[i]
            page2 = doc2[i]

            text1 = page1.get_text()
            text2 = page2.get_text()

            if text1 != text2:
                result["pages_equal"] = False
                result["differences"].append(f"Page {i + 1}: Text content differs")

            pix1 = page1.get_pixmap()
            pix2 = page2.get_pixmap()

            if pix1.width != pix2.width or pix1.height != pix2.height:
                result["differences"].append(
                    f"Page {i + 1}: Dimensions differ ({pix1.width}x{pix1.height} vs {pix2.width}x{pix2.height})"
                )

        doc1.close()
        doc2.close()

        return result


def _pdf_merge_executor(task: "TaskItem") -> Dict[str, Any]:
    from pathlib import Path

    engine = PDFEngine()
    payload = task.payload
    inputs = [Path(p) for p in payload.get("input_paths", [])]
    output = Path(payload["output_path"])

    pages = engine.merge_pdfs(inputs, output)
    return {
        "output_path": str(output),
        "output_files": [str(output)],
        "total_pages": pages,
        "message": f"Merged {len(inputs)} files ({pages} pages)",
    }


def _pdf_compress_executor(task: "TaskItem") -> Dict[str, Any]:
    from pathlib import Path

    engine = PDFEngine()
    payload = task.payload
    inp = Path(payload["input_path"])
    output = Path(payload.get("output_path", inp.parent / f"{inp.stem}_compressed.pdf"))
    dpi = payload.get("dpi", 150)
    quality = payload.get("quality", 75)

    pages = engine.compress_pdf(inp, output, dpi, quality)
    return {
        "output_path": str(output),
        "output_files": [str(output)],
        "page_count": pages,
        "message": f"Compressed: {inp.name} ({pages} pages)",
    }


from max_cli.core.engines.task_queue import TaskItem, TaskType, register_executor  # noqa: E402

register_executor(TaskType.PDF_MERGE, _pdf_merge_executor)
register_executor(TaskType.PDF_COMPRESS, _pdf_compress_executor)
