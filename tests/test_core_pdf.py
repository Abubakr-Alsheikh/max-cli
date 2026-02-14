import pytest
from PIL import Image
from max_cli.core.pdf_engine import PDFEngine


class TestPDFEngine:
    """Tests for PDF manipulation operations."""

    def test_merge_pdfs(self, tmp_path):
        """Test merging multiple PDFs into one."""
        pdf1 = tmp_path / "doc1.pdf"
        pdf2 = tmp_path / "doc2.pdf"

        img1 = Image.new("RGB", (200, 200), color="red")
        img2 = Image.new("RGB", (200, 200), color="blue")

        img1.save(pdf1, "PDF")
        img2.save(pdf2, "PDF")

        output = tmp_path / "merged.pdf"

        engine = PDFEngine()
        result = engine.merge_pdfs([pdf1, pdf2], output)

        assert output.exists()
        assert result == 2

    def test_merge_pdfs_nonexistent_file(self, tmp_path):
        """Test that merging fails gracefully with missing files."""
        nonexistent = tmp_path / "missing.pdf"
        output = tmp_path / "output.pdf"

        engine = PDFEngine()

        with pytest.raises(FileNotFoundError):
            engine.merge_pdfs([nonexistent], output)

    def test_compress_pdf(self, dummy_pdf, tmp_path):
        """Test PDF compression."""
        output = tmp_path / "compressed.pdf"

        engine = PDFEngine()
        result = engine.compress_pdf(dummy_pdf, output, dpi=72, quality=50)

        assert output.exists()
        assert result == 1

    def test_compress_pdf_nonexistent(self, tmp_path):
        """Test compression with nonexistent file."""
        nonexistent = tmp_path / "missing.pdf"
        output = tmp_path / "output.pdf"

        engine = PDFEngine()

        with pytest.raises(FileNotFoundError):
            engine.compress_pdf(nonexistent, output)

    def test_split_pdf(self, dummy_pdf_multi, tmp_path):
        """Test splitting PDF by page ranges."""
        output = tmp_path / "split.pdf"

        engine = PDFEngine()
        result = engine.split_pdf(dummy_pdf_multi, output, "1-2")

        assert output.exists()
        assert result == 2

    def test_split_pdf_invalid_range(self, dummy_pdf_multi, tmp_path):
        """Test splitting with invalid page range."""
        output = tmp_path / "split.pdf"

        engine = PDFEngine()

        with pytest.raises(ValueError):
            engine.split_pdf(dummy_pdf_multi, output, "10-20")

    def test_get_page_count(self, dummy_pdf_multi):
        """Test getting page count from PDF."""
        engine = PDFEngine()
        count = engine.get_page_count(dummy_pdf_multi)

        assert count == 3

    def test_split_by_range(self, dummy_pdf_multi, tmp_path):
        """Test splitting by range."""
        output = tmp_path / "range.pdf"

        engine = PDFEngine()
        result = engine.split_by_range(dummy_pdf_multi, output, start=1, end=2)

        assert output.exists()
        assert result == 2

    def test_split_by_range_invalid(self, dummy_pdf, tmp_path):
        """Test splitting with invalid range."""
        output = tmp_path / "range.pdf"

        engine = PDFEngine()

        with pytest.raises(ValueError):
            engine.split_by_range(dummy_pdf, output, start=5, end=10)

    def test_split_into_chunks(self, dummy_pdf_multi, tmp_path):
        """Test splitting PDF into chunks."""
        output_dir = tmp_path / "chunks"
        output_dir.mkdir()

        engine = PDFEngine()
        result = engine.split_into_chunks(dummy_pdf_multi, output_dir, chunk_size=2)

        assert len(result) == 2
        assert all(p.exists() for p in result)

    def test_watermark_pdf(self, dummy_pdf, tmp_path):
        """Test adding watermark to PDF."""
        output = tmp_path / "watermarked.pdf"

        engine = PDFEngine()
        engine.watermark_pdf(dummy_pdf, output, text="DRAFT", opacity=0.5)

        assert output.exists()

    def test_set_password(self, dummy_pdf, tmp_path):
        """Test setting password protection on PDF."""
        output = tmp_path / "protected.pdf"

        engine = PDFEngine()
        engine.set_password(dummy_pdf, output, password="test123")

        assert output.exists()

    def test_extract_assets(self, dummy_pdf, tmp_path):
        """Test extracting images from PDF."""
        output_dir = tmp_path / "assets"
        output_dir.mkdir()

        engine = PDFEngine()
        result = engine.extract_assets(dummy_pdf, output_dir)

        assert isinstance(result, int)
