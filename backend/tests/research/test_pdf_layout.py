"""Synthetic ruled table with known PDF cell, caption and equation positions."""
from hashlib import sha256
from io import BytesIO

import pytest

from backend.research.pdf_layout import page_evidence


def specimen():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(400, 400)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = ["10 300 m 210 300 l S", "10 260 m 210 260 l S", "10 220 m 210 220 l S"]
    content += [f"{x} 300 m {x} 220 l S" for x in (10, 110, 210)]
    for x, y, label in [(12, 280, "Model"), (112, 280, "Accuracy %"), (12, 240, "A"),
                         (112, 240, "87"), (10, 320, "Table 1. Test fixture")]:
        content.append(f"BT /F1 10 Tf {x} {y} Td ({label}) Tj ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(content).encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    handle = BytesIO()
    writer.write(handle)
    return handle.getvalue()


def test_verified_cell_and_region():
    pytest.importorskip("pdfplumber")
    raw = specimen()
    data = page_evidence(raw, "table-paper", 1)
    assert data["source_version"] == sha256(raw).hexdigest()
    cell = next(i for i in data["items"] if i["kind"] == "cell" and i["quote"] == "87")
    assert (cell["row"], cell["column"], cell["header_candidate"]) == (2, 2, "Accuracy %")
    assert cell["bbox"] == (110.0, 140.0, 210.0, 180.0)
    assert data["source_version"] in cell["locator"] and cell["quote_sha256"] == sha256(b"87").hexdigest()
    assert any(i["kind"] == "caption" for i in data["items"])
    with pytest.raises(ValueError, match="page_out_of_range"):
        page_evidence(raw, "table-paper", 2)
