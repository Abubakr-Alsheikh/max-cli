"""CliRunner tests for `max pdf` (src/max_cli/interface/cli_pdf.py).

Merge, split, bundle, stamp, lock and compare run the real PDFEngine on the
small conftest PDFs; error paths patch `_get_engine`.
"""

from unittest.mock import patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from max_cli.common import logger
from max_cli.common.exceptions import MaxError
from max_cli.interface import cli_pdf
from max_cli.interface.cli_pdf import app as pdf_app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})

ENGINE_PATH = "max_cli.interface.cli_pdf._get_engine"


@pytest.fixture(autouse=True)
def plain_console(monkeypatch):
    """Swap the shared Rich console for a wide, colorless one.

    The logger console is built at import time, so the runner's NO_COLOR and
    COLUMNS never reach it; without this it emits ANSI codes and wraps paths.
    """
    plain = Console(
        theme=logger.custom_theme,
        width=300,
        height=1000,
        color_system=None,
        force_terminal=False,
        legacy_windows=False,
    )
    monkeypatch.setattr(logger, "console", plain)
    monkeypatch.setattr(cli_pdf, "console", plain)


def _page_count(pdf_path):
    import fitz

    with fitz.open(pdf_path) as doc:
        return len(doc)


@pytest.mark.parametrize(
    "command",
    [
        None,
        "merge",
        "compress",
        "bundle",
        "split",
        "stamp",
        "lock",
        "rip",
        "ocr",
        "form-data",
        "form-fill",
        "form-flatten",
        "optimize",
        "compare",
    ],
)
def test_help(command):
    args = [command, "--help"] if command else ["--help"]
    result = runner.invoke(pdf_app, args)
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


class TestMerge:
    def test_merges_files_into_output(self, dummy_pdf, dummy_pdf_multi, tmp_path):
        output_path = tmp_path / "combined.pdf"

        result = runner.invoke(
            pdf_app,
            ["merge", str(dummy_pdf), str(dummy_pdf_multi), "-o", str(output_path)],
        )

        assert result.exit_code == 0, result.output
        assert "Merging 2 files" in result.output
        assert "Merged 4 pages" in result.output
        assert _page_count(output_path) == 4

    def test_folder_input_uses_folder_name(self, dummy_pdf, dummy_pdf_multi):
        folder = dummy_pdf.parent

        result = runner.invoke(pdf_app, ["merge", str(folder)])

        assert result.exit_code == 0, result.output
        merged_path = folder / f"{folder.name}_merged.pdf"
        assert _page_count(merged_path) == 4

    @patch(ENGINE_PATH)
    def test_engine_error_is_reported(self, mock_get_engine, dummy_pdf, tmp_path):
        mock_get_engine.return_value.merge_pdfs.side_effect = MaxError("disk full")
        output_path = tmp_path / "combined.pdf"

        result = runner.invoke(
            pdf_app, ["merge", str(dummy_pdf), "-o", str(output_path)]
        )

        assert result.exception is None
        assert result.exit_code == 0
        assert "Error: Merge failed: disk full" in result.output
        assert not output_path.exists()

    def test_no_pdfs_is_reported(self, tmp_path):
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()

        result = runner.invoke(pdf_app, ["merge", str(empty_folder)])

        assert result.exit_code == 1
        assert not isinstance(result.exception, ValueError)
        assert "No PDF files found" in result.output


class TestSplit:
    def test_list_shows_page_count(self, dummy_pdf_multi):
        result = runner.invoke(pdf_app, ["split", str(dummy_pdf_multi), "--list"])
        assert result.exit_code == 0, result.output
        assert "'multi.pdf' has 3 pages." in result.output

    def test_extracts_range(self, dummy_pdf_multi):
        result = runner.invoke(
            pdf_app, ["split", str(dummy_pdf_multi), "-s", "2", "-e", "3"]
        )

        assert result.exit_code == 0, result.output
        assert "Extracted 2 pages -> multi_p2-3.pdf" in result.output
        assert _page_count(dummy_pdf_multi.parent / "multi_p2-3.pdf") == 2

    def test_remove_drops_range(self, dummy_pdf_multi):
        result = runner.invoke(
            pdf_app, ["split", str(dummy_pdf_multi), "--remove", "-s", "1", "-e", "1"]
        )

        assert result.exit_code == 0, result.output
        output_path = dummy_pdf_multi.parent / "multi_without_p1-1.pdf"
        assert _page_count(output_path) == 2

    def test_chunks_create_one_file_per_chunk(self, dummy_pdf_multi, tmp_path):
        chunk_dir = tmp_path / "chunks"
        chunk_dir.mkdir()

        result = runner.invoke(
            pdf_app, ["split", str(dummy_pdf_multi), "-c", "1", "-o", str(chunk_dir)]
        )

        assert result.exit_code == 0, result.output
        assert "Split into 3 chunks" in result.output
        assert len(list(chunk_dir.glob("*.pdf"))) == 3

    def test_invalid_range_fails(self, dummy_pdf_multi):
        result = runner.invoke(
            pdf_app, ["split", str(dummy_pdf_multi), "-s", "3", "-e", "2"]
        )
        assert result.exit_code == 1
        assert "Invalid range: 3-2" in result.output

    def test_missing_file_fails(self, tmp_path):
        result = runner.invoke(pdf_app, ["split", str(tmp_path / "nope.pdf")])
        assert result.exit_code == 1
        assert "File not found" in result.output

    @patch(ENGINE_PATH)
    def test_unreadable_pdf_is_reported(self, mock_get_engine, dummy_pdf):
        mock_get_engine.return_value.get_page_count.side_effect = MaxError("corrupt")

        result = runner.invoke(pdf_app, ["split", str(dummy_pdf)])

        assert result.exit_code == 1
        assert "Failed to read PDF: corrupt" in result.output
        assert "Traceback" not in result.output


class TestCompress:
    def test_single_file(self, dummy_pdf):
        result = runner.invoke(pdf_app, ["compress", str(dummy_pdf)])

        assert result.exit_code == 0, result.output
        assert "Processed 1/1 files" in result.output
        assert (dummy_pdf.parent / "test_compressed.pdf").exists()

    @patch(ENGINE_PATH)
    def test_engine_error_is_reported_per_file(self, mock_get_engine, dummy_pdf):
        mock_get_engine.return_value.compress_pdf.side_effect = MaxError("bad image")

        result = runner.invoke(pdf_app, ["compress", str(dummy_pdf)])

        assert result.exception is None
        assert "Failed to compress test.pdf: bad image" in result.output
        assert "Processed 0/1 files" in result.output

    def test_missing_target_fails(self, tmp_path):
        result = runner.invoke(pdf_app, ["compress", str(tmp_path / "nope.pdf")])
        assert result.exit_code == 1
        assert "Target not found" in result.output


class TestBundle:
    def test_merge_only(self, dummy_pdf, dummy_pdf_multi, tmp_path):
        output_path = tmp_path / "bundle.pdf"

        result = runner.invoke(
            pdf_app,
            [
                "bundle",
                str(dummy_pdf),
                str(dummy_pdf_multi),
                "--no-compress",
                "-o",
                str(output_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Bundle created successfully!" in result.output
        assert "Pages: 4" in result.output
        assert _page_count(output_path) == 4

    @patch(ENGINE_PATH)
    def test_engine_error_exits_1(self, mock_get_engine, dummy_pdf, tmp_path):
        mock_get_engine.return_value.bundle_pdfs.side_effect = MaxError("no space")

        result = runner.invoke(
            pdf_app, ["bundle", str(dummy_pdf), "-o", str(tmp_path / "b.pdf")]
        )

        assert result.exit_code == 1
        assert "Bundle operation failed: no space" in result.output
        assert "Traceback" not in result.output


class TestOtherCommands:
    def test_stamp_writes_output(self, dummy_pdf):
        result = runner.invoke(pdf_app, ["stamp", str(dummy_pdf), "SECRET"])

        assert result.exit_code == 0, result.output
        assert "Stamping 'SECRET' onto test.pdf" in result.output
        assert (dummy_pdf.parent / "test_stamped.pdf").exists()

    def test_lock_encrypts_output(self, dummy_pdf):
        import fitz

        result = runner.invoke(pdf_app, ["lock", str(dummy_pdf), "-p", "hunter2"])

        assert result.exit_code == 0, result.output
        locked_path = dummy_pdf.parent / "test_locked.pdf"
        with fitz.open(locked_path) as doc:
            assert doc.needs_pass

    def test_compare_identical(self, dummy_pdf):
        result = runner.invoke(pdf_app, ["compare", str(dummy_pdf), str(dummy_pdf)])
        assert result.exit_code == 0, result.output
        assert "PDFs are identical!" in result.output

    @patch(ENGINE_PATH)
    def test_compare_error_is_reported(self, mock_get_engine, dummy_pdf):
        mock_get_engine.return_value.compare_pdfs.side_effect = MaxError("unreadable")

        result = runner.invoke(pdf_app, ["compare", str(dummy_pdf), str(dummy_pdf)])

        assert result.exception is None
        assert "Comparison failed: unreadable" in result.output

    def test_form_data_without_fields(self, dummy_pdf):
        result = runner.invoke(pdf_app, ["form-data", str(dummy_pdf)])
        assert result.exit_code == 0, result.output
        assert "No form fields found" in result.output

    def test_form_fill_rejects_bad_field(self, dummy_pdf):
        result = runner.invoke(pdf_app, ["form-fill", str(dummy_pdf), "-f", "x"])
        assert result.exit_code == 1
        assert "Invalid field format: x" in result.output

    @patch(ENGINE_PATH)
    def test_form_fill_passes_fields(self, mock_get_engine, dummy_pdf):
        result = runner.invoke(
            pdf_app,
            ["form-fill", str(dummy_pdf), "-f", "name=John", "-f", "age=30"],
        )

        assert result.exit_code == 0, result.output
        filled_values = mock_get_engine.return_value.fill_form.call_args.args[2]
        assert filled_values == {"name": "John", "age": "30"}

    @patch(ENGINE_PATH)
    def test_ocr_runtime_error_shows_install_tip(self, mock_get_engine, dummy_pdf):
        mock_get_engine.return_value.ocr_pdf.side_effect = RuntimeError(
            "pytesseract missing"
        )

        result = runner.invoke(pdf_app, ["ocr", str(dummy_pdf)])

        assert result.exception is None
        assert "Error: pytesseract missing" in result.output
        assert "Tip: Install OCR dependencies" in result.output

    @patch(ENGINE_PATH)
    def test_ocr_install_tip_keeps_extra_name(self, mock_get_engine, dummy_pdf):
        mock_get_engine.return_value.ocr_pdf.side_effect = RuntimeError("missing")

        result = runner.invoke(pdf_app, ["ocr", str(dummy_pdf)])

        assert "pip install max-cli[ocr]" in result.output
