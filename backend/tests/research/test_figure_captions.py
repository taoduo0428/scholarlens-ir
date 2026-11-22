import pytest

from backend.research.pdf_layout import figure_caption_links


def item(kind, locator, bbox, quote=""):
    return dict(kind=kind, locator=locator, bbox=bbox, quote=quote, quote_sha256=locator + "-hash")


IMAGE = item("figure", "im", (50, 10, 140, 80))
CAPTION = item("caption", "cap", (30, 88, 170, 102), "Figure 1. Example")


@pytest.mark.parametrize("label", ["Fig. 1: Test", "图 1：实例", "Figure1.Example"])
def test_numbered_caption_links_carry_both_locators(label):
    links = figure_caption_links([IMAGE, {**CAPTION, "quote": label}])
    assert links == [{"number": 1, "figure_locator": "im", "caption_locator": "cap",
                      "caption_quote_sha256": "cap-hash", "basis": "unique_adjacent_caption"}]


@pytest.mark.parametrize("items", [
    [IMAGE, {**CAPTION, "bbox": (152, 88, 210, 102)}],
    [IMAGE, {**CAPTION, "bbox": (30, 131, 170, 139)}],
    [IMAGE, {**CAPTION, "quote": "Table 1. Characteristics"}],
    [IMAGE, {**CAPTION, "quote": "Figure 1 shows an example."}],
    [IMAGE, {**IMAGE, "locator": "neighbor"}, CAPTION],
    [IMAGE, CAPTION, {**CAPTION, "locator": "other", "quote": "Figure 2. Example"}],
    [IMAGE, CAPTION, {**CAPTION, "locator": "again", "bbox": (190, 188, 250, 199)}],
])
def test_ambiguous_or_distant_regions_stay_unpaired(items):
    assert figure_caption_links(items) == []
