"""pdf.describe: what a PDF holds, for the dashboard's PDF page."""

import fitz
import pytest

from max_cli.common.exceptions import ProcessingError, ResourceNotFoundError
from max_cli.core.operations import pdf

A4 = (595, 842)
LETTER = (612, 792)


def _pdf(path, *, size=A4, pages=1, text="Hello", metadata=None):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        if text:
            page.insert_text((72, 72), text)
    if metadata:
        doc.set_metadata(metadata)
    doc.save(path)
    doc.close()
    return path


def test_pages_paper_and_metadata(tmp_path):
    path = _pdf(
        tmp_path / "report.pdf",
        pages=3,
        metadata={"title": "Q3 report", "author": "Ana"},
    )

    facts = pdf.describe(path)

    assert (facts.pages, facts.page_size) == (3, "A4 portrait")
    assert (facts.title, facts.author) == ("Q3 report", "Ana")
    assert facts.size_bytes == path.stat().st_size
    assert not facts.encrypted and not facts.scanned and facts.note == ""


def test_a_page_with_no_text_looks_scanned(dummy_pdf):
    facts = pdf.describe(dummy_pdf)

    assert facts.scanned
    assert "OCR" in facts.note


@pytest.mark.parametrize(
    "size, expected",
    [
        ((LETTER[1], LETTER[0]), "Letter landscape"),
        ((283, 425), "100 x 150 mm"),
    ],
)
def test_paper_size_names_and_millimetres(tmp_path, size, expected):
    facts = pdf.describe(_pdf(tmp_path / "page.pdf", size=size))

    assert facts.page_size == expected


def test_form_fields_are_counted(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    for number in range(2):
        widget = fitz.Widget()
        widget.field_name = f"name{number}"
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(72, 72 + number * 40, 300, 100 + number * 40)
        page.add_widget(widget)
    path = tmp_path / "form.pdf"
    doc.save(path)
    doc.close()

    assert pdf.describe(path).form_fields == 2


def test_a_locked_pdf_says_so(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret")
    path = tmp_path / "locked.pdf"
    doc.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    doc.close()

    facts = pdf.describe(path)

    assert facts.encrypted and facts.pages is None
    assert "password" in facts.note


def test_a_file_that_isnt_a_pdf_is_an_error(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")

    with pytest.raises(ProcessingError, match="Couldn't read this PDF"):
        pdf.describe(broken)


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(ResourceNotFoundError):
        pdf.describe(tmp_path / "gone.pdf")
