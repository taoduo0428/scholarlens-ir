"""Match physical figure regions to the publisher's JATS titles and decoded RGB images."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
import xml.etree.ElementTree as ET

from backend.research.pdf_layout import page_evidence
from tools.research_eval.v7_pdf import DOI, PDF_HASH, XML_HASH, normalized


def evaluate(pdf, xml, graphics):
    from PIL import Image
    from pypdf import PdfReader

    started = monotonic()
    raw, markup = pdf.read_bytes(), xml.read_bytes()
    if sha256(raw).hexdigest() != PDF_HASH or sha256(markup).hexdigest() != XML_HASH:
        raise ValueError("publisher document version mismatch")
    references = {}
    for fig in ET.fromstring(markup).findall(".//fig"):
        number = int(fig.findtext("label").split()[1])
        href = fig.find("graphic").get("{http://www.w3.org/1999/xlink}href")
        if href != f"info:doi/{DOI}.g{number:03d}" or number in references:
            raise ValueError("ambiguous publisher graphic")
        title = "".join(fig.find("caption/title").itertext())
        img = graphics / f"publisher-g{number:03d}.img"
        with Image.open(img) as source:
            rgb = source.convert("RGB")
            references[number] = (title, rgb.size, sha256(rgb.tobytes()).hexdigest(),
                                  sha256(img.read_bytes()).hexdigest())
    matched, unresolved, seen = [], [], set()
    reader = PdfReader(pdf)
    for page, pdfpage in enumerate(reader.pages, 1):
        layout = page_evidence(raw, DOI, page)
        items = {item["locator"]: item for item in layout["items"]}
        figures = [row for row in items.values() if row["kind"] == "figure"]
        paired = set()
        for link in layout["figure_caption_links"]:
            number = link["number"]
            # For this edition each numbered figure is the only raster on its page.
            if number not in references or number in seen or len(figures) != 1 or len(pdfpage.images) != 1:
                raise ValueError("ambiguous numbered raster")
            region, caption = items[link["figure_locator"]], items[link["caption_locator"]]
            title, size, digest, file_hash = references[number]
            prefix = normalized(f"Figure {number}. {title}")
            if not normalized(caption["quote"]).startswith(prefix):
                raise ValueError(f"caption title mismatch on page {page}")
            image = pdfpage.images[0].image.convert("RGB")
            if image.size != size or sha256(image.tobytes()).hexdigest() != digest:
                raise ValueError(f"publisher pixels mismatch on page {page}")
            matched.append({"page": page, "number": number, "bbox": region["bbox"], "caption_bbox": caption["bbox"],
                            "caption_line_sha256": caption["quote_sha256"], "size": size,
                            "rgb_sha256": digest, "publisher_file_sha256": file_hash})
            paired.add(region["locator"])
            seen.add(number)
        unresolved.extend({"page": page, "bbox": row["bbox"]} for row in figures if row["locator"] not in paired)
    return {"doi": DOI, "pdf_sha256": PDF_HASH, "jats_sha256": XML_HASH, "publisher_figures": len(references),
            "matched": matched, "regions_without_caption": unresolved, "missing": sorted(references.keys() - seen),
            "elapsed_seconds": round(monotonic()-started, 3)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("pdf", "xml", "graphics", "output"):
        cli.add_argument(key, type=Path)
    args = cli.parse_args()
    result = evaluate(args.pdf, args.xml, args.graphics)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("matched", len(result["matched"]), "/", result["publisher_figures"])
