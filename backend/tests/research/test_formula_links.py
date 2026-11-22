from hashlib import sha256
from io import BytesIO

import pytest

from backend.research.formula_links import formula_evidence
from backend.research.pdf_layout import from_path


def line(text, y, x=10):
    return {"kind": "text", "quote": text, "quote_sha256": sha256(text.encode()).hexdigest(),
            "bbox": [x, y, x + 70, y + 10], "locator": f"paper:p1:{x},{y}"}


def test_formula_source_slices_via_pdf_reader(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(400, 400)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(br"""BT /F1 10 Tf 50 310 Td (See Equation \(7\) and Eq.\(9\).) Tj ET
BT /F1 10 Tf 50 250 Td (s = v * t \(7\)) Tj ET
BT /F1 10 Tf 50 235 Td (where v denotes the mean velocity.) Tj ET""")
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    path = tmp_path / "motion.pdf"
    path.write_bytes(out.getvalue())
    result = from_path(path, "motion", 1)
    facts = result["formula_evidence"]
    eq, = facts["equations"]
    assert (eq["number"], eq["source"]["quote"]) == ("7", "s = v * t")
    definition, = eq["definitions"]
    assert definition["symbol"] == "v"
    assert definition["source"]["quote"] == "where v denotes the mean velocity."
    first, second = facts["mentions"]
    assert first["equation_locator"] == eq["source"]["locator"] and second["equation_locator"] is None
    for src in [eq["source"], definition["source"], first["source"], second["source"]]:
        original, = [i for i in result["items"] if i["locator"] == src["locator"]]
        assert original["quote"][src["start"]:src["end"]] == src["quote"]
        assert src["line_sha256"] == original["quote_sha256"]
        assert sha256(src["quote"].encode()).hexdigest() == src["quote_sha256"]
        assert result["source_version"] in src["locator"]


@pytest.mark.parametrize("other", ["z = ??? (1)", "s = y+1 (1)"])
def test_duplicate_number_does_not_resolve(other):
    data = formula_evidence([line("s = v*t (1)", 20), line(other, 40), line("See Eq.(1)", 100)])
    assert data["equations"] == [] and data["mentions"][0]["equation_locator"] is None


@pytest.mark.parametrize("near", [[line("where a represents the amplitude.", 32)],
                                   [line("where v represents the velocity.", 32, 230)],
                                   [line("where v denotes the velocity.", 31), line("Another line.", 42)]])
def test_unrelated_or_ambiguous_definition(near):
    eq, = formula_evidence([line("s = v*t (8)", 20), *near])["equations"]
    assert eq["definitions"] == []
