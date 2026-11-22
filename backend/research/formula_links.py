"""Provenance for simple displayed equations, literal mentions and author definitions."""
from collections import Counter
from hashlib import sha256
import ast
import re

NUMBER = r"[1-9][0-9]{0,3}[a-z]?"
SYMBOL = r"[a-zA-Z\u0391-\u03A9\u03B1-\u03C9]"
EQUATION = re.compile(
    rf"(?P<expression>{SYMBOL}(?:_[A-Za-z0-9]+)?\s*=\s*.{{1,120}}?)\s*\((?P<number>{NUMBER})\)"
)
MENTION = re.compile(rf"\b(?:Eq\.|Equation)\s*\((?P<number>{NUMBER})\)", re.I)
DEFINITION = re.compile(
    rf"(?:[Ww]here|[Hh]ere)\s+(?P<symbol>{SYMBOL}(?:_[A-Za-z0-9]+)?)\s+"
    r"(?:denotes|represents|is defined as|is)\s+[A-Za-z][^.;:!?]{1,140}[.]?"
)
VARIABLE = re.compile(rf"{SYMBOL}(?:_[A-Za-z0-9]+)?")
MATH_SIGNS = str.maketrans({"−": "-", "×": "*", "·": "*", "^": "**"})


def simple_expression(expression):
    """Recognize a small arithmetic grammar without evaluating or rendering the source."""
    right = expression.split("=", 1)[1].strip().translate(MATH_SIGNS)
    if not re.fullmatch(r"[\w +*/().-]+", right):
        return False
    try:
        tree = ast.parse(right, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if not VARIABLE.fullmatch(node.id):
                return False
        elif isinstance(node, ast.Constant):
            if type(node.value) not in (int, float):
                return False
        elif not isinstance(node, (ast.Expression, ast.Load, ast.UnaryOp, ast.BinOp,
                                   ast.Add, ast.Sub, ast.UAdd, ast.USub, ast.Mult, ast.Div, ast.Pow)):
            return False
    return True


def source(item, start, end):
    quote = item["quote"][start:end]
    return {"locator": item["locator"], "bbox": item["bbox"], "line_sha256": item["quote_sha256"],
            "start": start, "end": end, "quote": quote, "quote_sha256": sha256(quote.encode()).hexdigest()}


def formula_evidence(items):
    """Resolve only unique numbered equations and unambiguous adjacent source lines on this page."""
    lines = [item for item in items if item["kind"] in {"text", "formula"}]
    candidates = []
    mentions = []
    for line in lines:
        text = line["quote"]
        match = EQUATION.fullmatch(text)
        if match:
            candidates.append((line, match))
        for ref in MENTION.finditer(text):
            if len(mentions) < 64:
                mentions.append({"number": ref["number"].lower(), "source": source(line, *ref.span())})

    counts = Counter(match["number"] for _, match in candidates)
    equations = []
    for line, match in candidates:
        if counts[match["number"]] != 1 or len(equations) >= 32 or not simple_expression(match["expression"]):
            continue
        x0, _, x1, bottom = line["bbox"]
        near = [other for other in lines if 0 <= other["bbox"][1] - bottom <= 18
                and min(x1, other["bbox"][2]) > max(x0, other["bbox"][0])]
        definitions = []
        if len(near) == 1:
            definition = DEFINITION.fullmatch(near[0]["quote"])
            if definition and re.search(rf"(?<![\w]){re.escape(definition['symbol'])}(?![\w])", match["expression"]):
                definitions.append({"symbol": definition["symbol"], "source": source(near[0], *definition.span())})
        equations.append({"number": match["number"], "source": source(line, *match.span("expression")),
                          "definitions": definitions})
    by_number = {row["number"]: row["source"]["locator"] for row in equations}
    for mention in mentions:
        mention["equation_locator"] = by_number.get(mention["number"])
    return {"basis": "pdf_text_layer", "equations": equations, "mentions": mentions}
