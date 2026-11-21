"""Attribute contributions to authors before using them as overview premises."""
import re

from backend.research.claim_verifier import GUARDS

# The subject of a contribution matters: prior work can use the same verbs.
AUTHOR = r"(?:\bwe|\bthis (?:paper|study|work)|\bour (?:study|work|approach|method|model|experiments?|results?)|\bthe proposed (?:method|model|approach))"
METHOD = re.compile(AUTHOR + r"\s+(?:(?:also|further|first|then|systematically)\s+)?(?:introduc|propos|present|construct|develop|deriv|employ|use\b|used\b|adopt|design|extend|investigat|analy[sz]|examin|stud(?:y|ied)|evaluat|compar|train|characteriz|formaliz|prove|establish|define|compute|demonstrate how|show how)", re.I)
RESULT = re.compile(AUTHOR + r"\s+(?:(?:also|further|experimentally|empirically|formally|theoretically)\s+)?(?:show\b|shows\b|found\b|find\b|demonstrat|establish|prov(?:e|ed)\b|obtain|identif|characteriz|achiev|outperform|observ|validat|confirm|deriv)", re.I)
MEASURED = re.compile(r"\b(?:our|experimental|empirical|simulation|numerical|evaluation)\s+results?\s+(?:show|confirm|demonstrate|indicate|reveal)|\b(?:we|our .{1,32}?)\s+(?:achieved|outperformed|reduced|improved)\b|(?:我们|本研究|本文)(?:发现|证明|验证)|实验结果表明", re.I)
CHINESE_METHOD = re.compile(r"(?:我们|本研究|本文)(?:提出|采用|设计|构建|分析)")
QUALIFIED = re.compile(r"\b(?:may|might|hypothesi[sz]e|conjecture|future work|plan to|aim to|hope to|expected to)\b|可能|计划|拟议", re.I)


def roles(statement):
    """Classify only complete, attributable claims; leave forecasts as gaps."""
    if GUARDS.search(statement) or QUALIFIED.search(statement):
        return set()
    method = METHOD.search(statement) or CHINESE_METHOD.search(statement)
    result = RESULT.search(statement) or MEASURED.search(statement)
    return {key for key, match in (("method", method), ("finding", result),
                                   ("topic", method or result)) if match}
