"""core/operations/pdf.py, and the catalog features the pdf group added:
list parameters (`multiple`) and masked ones (SECRET)."""

from pathlib import Path
from unittest.mock import MagicMock

import fitz
import pytest

from max_cli.common.events import EventEmitter
from max_cli.common.exceptions import (
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from max_cli.core.catalog import actions_for, get_action
from max_cli.core.catalog.runner import coerce_args
from max_cli.core.catalog.schema import action_schema
from max_cli.core.catalog.spec import Surface
from max_cli.core.operations import pdf


def _pages(path: Path) -> int:
    with fitz.open(path) as doc:
        return doc.page_count


@pytest.fixture
def pdf_folder(dummy_pdf, dummy_pdf_multi) -> Path:
    """test.pdf (1 page) and multi.pdf (3 pages) in one folder."""
    return dummy_pdf.parent


class TestMerge:
    def test_folder_merges_in_natural_order_into_the_folder(self, tmp_path):
        for name in ["10.pdf", "2.pdf", "_temp.pdf", "notes.txt"]:
            (tmp_path / name).write_bytes(b"")
        assert [path.name for path in pdf.resolve_pdfs([tmp_path])] == [
            "2.pdf",
            "10.pdf",
        ]

    def test_running_twice_does_not_merge_the_old_result(self, pdf_folder):
        first = pdf.merge([pdf_folder])
        second = pdf.merge([pdf_folder])

        merged = pdf_folder / f"{pdf_folder.name}_merged.pdf"
        assert first.output_files == second.output_files == [merged]
        assert second.details["file_count"] == 2
        assert _pages(merged) == 4

    def test_no_pdfs(self, tmp_path):
        with pytest.raises(ValidationError, match="No PDF files"):
            pdf.merge([tmp_path])


class TestCompress:
    def test_folder_goes_into_a_compressed_subfolder(self, pdf_folder):
        emitter = EventEmitter()
        seen = []
        emitter.subscribe(seen.append)

        result = pdf.compress(pdf_folder, dpi=50, quality=50, emitter=emitter)

        assert result.ok
        assert sorted(path.name for path in result.output_files) == [
            "multi.pdf",
            "test.pdf",
        ]
        assert {path.parent.name for path in result.output_files} == {"compressed"}
        assert any(event.type == "file_complete" for event in seen)

    def test_one_failure_is_reported_and_the_rest_run(self, pdf_folder):
        engine = MagicMock()

        def compress_pdf(source, output, dpi, quality):
            if source.name == "test.pdf":
                raise RuntimeError("bad image")
            output.write_bytes(b"x")

        engine.compress_pdf.side_effect = compress_pdf

        result = pdf.compress(pdf_folder, engine=engine)

        assert result.ok
        assert result.details["failed"] == [{"file": "test.pdf", "error": "bad image"}]
        assert result.message == "Finished! Processed 1/2 files."

    def test_quality_range(self, dummy_pdf):
        with pytest.raises(ValidationError, match="between 1 and 100"):
            pdf.compress(dummy_pdf, quality=0)


class TestSplit:
    def test_range_and_names(self, dummy_pdf_multi):
        kept = pdf.split(dummy_pdf_multi, start=2)
        removed = pdf.split(dummy_pdf_multi, start=1, end=1, remove=True)

        assert kept.output_files[0].name == "multi_p2-3.pdf"
        assert removed.output_files[0].name == "multi_without_p1-1.pdf"
        assert _pages(removed.output_files[0]) == 2

    def test_list_pages_writes_nothing(self, dummy_pdf_multi):
        result = pdf.split(dummy_pdf_multi, list_pages=True)

        assert result.details == {"page_count": 3} and result.output_files == []

    @pytest.mark.parametrize("start, end", [(0, 2), (3, 2)])
    def test_bad_range(self, dummy_pdf_multi, start, end):
        with pytest.raises(ValidationError, match="Invalid range"):
            pdf.split(dummy_pdf_multi, start=start, end=end)

    def test_unreadable_file(self, tmp_path):
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"not a pdf")

        with pytest.raises(ProcessingError, match="Failed to read PDF"):
            pdf.split(broken)


class TestOthers:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ResourceNotFoundError):
            pdf.stamp(tmp_path / "gone.pdf")

    def test_lock_needs_a_password(self, dummy_pdf):
        with pytest.raises(ValidationError, match="password"):
            pdf.lock(dummy_pdf, password="")

    def test_form_fill_parses_fields(self, dummy_pdf):
        engine = MagicMock()

        pdf.form_fill(dummy_pdf, ["name=John", "note=a=b"], engine=engine)

        assert engine.fill_form.call_args.args[2] == {"name": "John", "note": "a=b"}

    @pytest.mark.parametrize("entry", ["novalue", "=value"])
    def test_form_fill_rejects_bad_fields(self, dummy_pdf, entry):
        with pytest.raises(ValidationError, match="Invalid field format"):
            pdf.form_fill(dummy_pdf, [entry], engine=MagicMock())

    def test_compare_identical(self, dummy_pdf):
        result = pdf.compare(dummy_pdf, dummy_pdf)

        assert result.details["identical"] and result.message == "PDFs are identical!"


class TestListAndSecretParams:
    def test_form_text_splits_on_semicolons(self, dummy_pdf, dummy_pdf_multi):
        action = get_action("pdf.merge")

        args = coerce_args(action, {"inputs": f"{dummy_pdf}; {dummy_pdf_multi} ;"})

        assert args["inputs"] == [dummy_pdf, dummy_pdf_multi]

    def test_agent_list_and_empty_list(self, dummy_pdf):
        action = get_action("pdf.merge")

        assert coerce_args(action, {"inputs": [str(dummy_pdf)]})["inputs"] == [
            dummy_pdf
        ]
        assert coerce_args(action, {"inputs": []})["inputs"] is None

    def test_required_list_must_not_be_empty(self, dummy_pdf):
        with pytest.raises(ValidationError, match="'field' is required"):
            coerce_args(get_action("pdf.form-fill"), {"target": str(dummy_pdf)})

    def test_schema_describes_a_list_as_an_array(self):
        schema = action_schema(get_action("pdf.form-fill"))
        field = schema["parameters"]["properties"]["field"]

        assert field["type"] == "array" and field["items"]["type"] == "string"

    def test_the_agent_never_gets_the_password_action(self):
        agent_actions = {action.name for action in actions_for("pdf", Surface.AGENT)}

        assert "lock" not in agent_actions and "merge" in agent_actions
