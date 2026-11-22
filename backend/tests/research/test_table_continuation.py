"""Two real PDF pages with synthetic ruled tables, captions and physical cells."""
from io import BytesIO

import pytest

from backend.research.pdf_layout import page_evidence
from backend.research.table_continuation import link_tables
from backend.tests.research.test_pdf_layout import specimen


def two_page_pdf(label='Table 1. Continued', header='Accuracy %', shift=0, with_figure=False):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    writer = PdfWriter()
    for continued in (False, True):
        page = writer.add_page(PdfReader(BytesIO(specimen(with_figure=with_figure and not continued))).pages[0])
        if continued:
            stream = DecodedStreamObject()
            content = page.get_contents().get_data().replace(b'Table 1. Test fixture', label.encode())
            content = content.replace(b'Accuracy %', header.encode()).replace(b'(87)', b'(64)')
            stream.set_data(f'q 1 0 0 1 {shift} 0 cm\n'.encode() + content + b'\nQ')
            page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def read(raw, page):
    pytest.importorskip('pdfplumber')
    return page_evidence(raw, 'paired-tables-fixture', page)


def test_explicit_continuation_preserves_page_evidence():
    raw = two_page_pdf()
    first, second = read(raw, 1), read(raw, 2)
    assert first['table_continuations'] == []
    assert second['cross_page_table_links'] == 'source_matched'
    link, = second['table_continuations']
    assert link['number'] == 1 and link['headers'] == ['Model', 'Accuracy %']
    for key, page, value in [('previous', first, '87'), ('current', second, '64')]:
        ref = link[key]
        by_locator = {i['locator']: i for i in page['items']}
        assert ref['page'] == page['page'] and by_locator[ref['table_locator']]['kind'] == 'table'
        assert by_locator[ref['caption_locator']]['quote_sha256'] == ref['caption_quote_sha256']
        assert any(i['kind'] == 'cell' and i['quote'] == value for i in page['items'])
    assert not link_tables({**first, 'source_version': 'other-edition'}, second)
    assert not link_tables({**first, 'paper_id': 'another-paper'}, second)
    assert not link_tables(first, {**second, 'page': 4})
    duplicate = next(i for i in first['items'] if i['kind'] == 'table')
    assert not link_tables({**first, 'items': first['items'] + [duplicate]}, second)
    caption = next(i for i in first['items'] if i['kind'] == 'caption')
    other = {**caption, 'quote': 'Table 4. Additional table'}
    assert not link_tables({**first, 'items': first['items'] + [other]}, second)



@pytest.mark.parametrize(('label','header','shift'), [
    ('Table 1. Test fixture', 'Accuracy %', 0),
    ('Table 2. Continued', 'Accuracy %', 0),
    ('Table 1. Continued experiments', 'Accuracy %', 0),
    ('Table 1. Continued', 'Accuracy', 0),
    ('Table 1. Continued', 'Accuracy %', 50),
    ('Table 1.2 Continued', 'Accuracy %', 0),
])
def test_distinct_or_ambiguous_tables_stay_separate(label, header, shift):
    result = read(two_page_pdf(label, header, shift), 2)
    assert result['table_continuations'] == [] and result['cross_page_table_links'] == 'unverified'


def test_banded_grid_keeps_sentence_across_column_break_and_rejects_mixed_rows():
    from backend.research.banded_tables import _cells

    def word(left, right, top):
        return {"x0": left, "x1": right, "top": top, "bottom": top + 5}

    words = [word(10, 20, 3), word(35, 42, 3), word(10, 25, 13), word(26, 38, 13)]
    assert _cells(words, [10, 30, 50], [0, 10, 20]) == [
        (10, 0, 30, 10), (30, 0, 50, 10), (10, 10, 50, 20)]
    assert not _cells(words + [word(44, 49, 13)], [10, 30, 50], [0, 10, 20])
