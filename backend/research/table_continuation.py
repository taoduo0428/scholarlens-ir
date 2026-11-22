"""Resolve numbered table continuations from physical evidence on adjacent pages."""
import re
from unicodedata import normalize


_LABEL = re.compile(r"^(?:table\s+|表\s*)([1-9]\d{0,3})(?![\w.-]\d|\w)(.*)$", re.I)
_CONTINUED = re.compile(r"^[\s.,:：．、–—-]*(?:\(continued\)|continued|\(cont\.\)|cont\.|（续）|\(续\)|续表|续)[\s.:。．]*$", re.I)


def _label(item):
    return _LABEL.fullmatch(item['quote'].strip()) if item['kind'] == 'caption' else None


def continuation_number(item):
    match = _label(item)
    return int(match[1]) if match and _CONTINUED.fullmatch(match[2]) else None


def _binding(page, number):
    items = page['items']
    if len(items) >= 1200:
        return None
    captions = [item for item in items if (m := _label(item)) and int(m[1]) == number]
    if len(captions) != 1:
        return None
    caption = captions[0]
    def adjacent(label, table):
        left, _, right, bottom = label['bbox']
        x0, top, x1, _ = table['bbox']
        overlap = min(right, x1) - max(left, x0)
        return 0 <= top - bottom <= 56 and overlap >= .65 * min(right - left, x1 - x0)

    choices = [item for item in items if item['kind'] == 'table' and adjacent(caption, item)]
    if len(choices) != 1:
        return None
    table = choices[0]
    if sum(1 for item in items if _label(item) and adjacent(item, table)) != 1:
        return None
    cells = [c for c in items if c['kind'] == 'cell' and c['table_id'] == table['table_id']]
    header = sorted((c for c in cells if c['row'] == 1), key=lambda c: c['column'])
    names = tuple(' '.join(normalize('NFC', c['quote']).split()) for c in header)
    if (not 2 <= len(names) < 40 or not all(names) or len(set(names)) != len(names)
            or any(len(c['quote']) == 1500 for c in header)
            or [c['column'] for c in header] != list(range(1, len(header) + 1))
            or not any(c['row'] > 1 and c['quote'].strip() for c in cells)):
        return None
    left, _, right, _ = table['bbox']
    edges = [(edge - left) / page['width'] for c in header for edge in (c['bbox'][0], c['bbox'][2])]
    ref = {'page': page['page'], 'table_locator': table['locator'], 'caption_locator': caption['locator'],
           'caption_quote_sha256': caption['quote_sha256']}
    return names, edges, ref, (left / page['width'], right / page['width'])


def link_tables(previous, current):
    if (previous['paper_id'] != current['paper_id'] or previous['source_version'] != current['source_version']
            or previous['page'] + 1 != current['page']):
        return []
    links = []
    numbers = {n for item in current['items'] if (n := continuation_number(item))}
    for number in sorted(numbers):
        first, second = _binding(previous, number), _binding(current, number)
        if not (first and second and first[0] == second[0]):
            continue
        left, right = first[3]
        new_left, new_right = second[3]
        same_column = abs(left - new_left) <= .015
        switched_columns = right <= .5 <= new_left or new_right <= .5 <= left
        if (same_column or switched_columns) and all(
                abs(a - b) <= .015 for a, b in zip(first[1], second[1], strict=True)):
            links.append({'number': number, 'headers': list(first[0]), 'previous': first[2], 'current': second[2]})
    return links
