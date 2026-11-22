"""Extract a physically bounded grid from repeated row fills and segmented rules."""
from collections import defaultdict


def _rules(page):
    rows = defaultdict(list)
    for line in page.lines:
        if line["width"] >= 4 and line["height"] < .3:
            rows[round(line["top"], 1)].append((line["x0"], line["x1"]))
    return rows


def _partitions(segments, left, right):
    segments = sorted((a, b) for a, b in segments if a >= left - .5 and b <= right + .5)
    if (not 2 <= len(segments) <= 40 or abs(segments[0][0] - left) > .5
            or abs(segments[-1][1] - right) > .5
            or any(abs(a[1] - b[0]) > .5 for a, b in zip(segments, segments[1:]))):
        return ()
    return (left, *(a for a, _ in segments[1:]), right)


def _runs(bands):
    run = []
    for top, bottom in sorted(set(bands)):
        if run and not 2 <= top - run[-1][1] <= 48:
            if len(run) >= 3:
                yield run
            run = []
        run.append((top, bottom))
    if len(run) >= 3:
        yield run


def _cells(words, xs, ys):
    cells = []
    for y0, y1 in zip(ys, ys[1:]):
        row = sorted((w for w in words if xs[0] - .5 <= w["x0"] and w["x1"] <= xs[-1] + .5
                      and y0 <= (w["top"] + w["bottom"]) / 2 < y1), key=lambda w: w["x0"])
        crosses = any(w["x0"] + 1 < x < w["x1"] - 1 for x in xs[1:-1] for w in row)
        if crosses:
            # A single left-aligned line of prose spanning columns is one labelled region.
            if (y0 == ys[0] or abs(row[0]["x0"] - xs[0]) > 2
                    or max(w["top"] for w in row) - min(w["top"] for w in row) > 1
                    or any(not -.5 <= b["x0"] - a["x1"] <= 3 for a, b in zip(row, row[1:]))):
                return []
            cells.append((xs[0], y0, xs[-1], y1))
        else:
            cells.extend((x0, y0, x1, y1) for x0, x1 in zip(xs, xs[1:]))
    return cells


def banded_tables(page, captions, ruled):
    """Use explicit header divisions and horizontal bands for the cell geometry."""
    from pdfplumber.table import Table

    if not captions or len(page.rects) > 2000 or len(page.lines) > 4000:
        return []
    rules = _rules(page)
    bands = defaultdict(list)
    for box in page.rects:
        if box["fill"] and 5 <= box["height"] <= 48 and box["width"] >= 60:
            bands[round(box["x0"], 1), round(box["x1"], 1)].append((box["top"], box["bottom"]))
    tables = []
    words = None
    for (left, right), entries in bands.items():
        for run in _runs(entries):
            start, end = run[0][0], run[-1][1]
            headers = [(y, xs) for y, lines in rules.items() if 5 <= start-y <= 48
                       and (xs := _partitions(lines, left, right))]
            if len(headers) != 1:
                continue
            top, xs = headers[0]
            if not any(0 <= top-c["bbox"][3] <= 56 and abs(left-c["bbox"][0]) <= 4 for c in captions):
                continue
            # An enclosing table already found by pdfplumber owns these cells.
            if any(t.bbox[0] < right and t.bbox[2] > left and t.bbox[1] < end and t.bbox[3] > top
                   for t in [*ruled, *tables]):
                continue
            ys = [top, *(edge for band in run for edge in band)]
            # A final unshaded row must have its own closing rule across the table.
            closes = [y for y, lines in rules.items() if 3 <= y-end <= 48
                      and (_partitions(lines, left, right) or any(
                          abs(a-left) <= .5 and abs(b-right) <= .5 for a, b in lines))]
            if closes:
                ys.append(min(closes))
            if len(ys) > 101:
                continue
            if words is None:
                words = page.extract_words()
                if len(words) > 4000:
                    return []
            cells = _cells(words, xs, ys)
            if not cells:
                continue
            tables.append(Table(page, cells))
            if len(tables) + len(ruled) >= 20:
                return tables
    return tables
