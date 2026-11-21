"""Identify the requested output independently of whether its evidence is available."""
import re
from typing import Literal

from backend.research.field_contract import TITLES

ResearchIntent = Literal[
    "description", "literature_synthesis", "method_comparison", "condition_comparison",
    "metric_comparison", "performance_ranking", "causal_analysis", "contradiction_analysis",
    "gap_discovery", "trend_analysis",
]

COMPARE = re.compile(r"compar|differ|contrast|versus|分别|对比|比较|差异|异同", re.I)
PATTERNS = (
    ("performance_ranking", r"\brank(?:ing)?\b|which.{0,28}(?:better|best|superior|outperform)|谁.{0,8}(?:好|高|优)|排名|优于|性能更"),
    ("contradiction_analysis", r"contradict|conflict|inconsistent|矛盾|冲突|不一致"),
    ("causal_analysis", r"\bcaus(?:e[sd]?|al|ality)\b|\bwhy\b|mechanism|因果|导致|为什么|为何|机制"),
    ("trend_analysis", r"\btrends?\b|over time|趋势|演变"),
    ("literature_synthesis", r"survey|landscape|overview|synthesi[sz]|literature review|综述|全景|概览|综合"),
    ("gap_discovery", r"research gaps?|open questions?|future work|limitations?|局限|研究空白|未解决|开放问题"),
)
DIMENSIONS = (
    ("metric_comparison", r"\bmetrics?\b|accuracy|precision|recall|评价指标|准确率|召回率|精确率"),
    ("condition_comparison", r"conditions?|settings?|protocols?|datasets?|corpora|条件|设置|数据集|语料"),
    ("method_comparison", r"methods?|approach(?:es)?|techniques?|方法|途径|技术路线"),
)


def research_intent(goal: str) -> ResearchIntent:
    text = TITLES.sub(" ", goal)
    for intent, pattern in PATTERNS:
        if re.search(pattern, text, re.I):
            return intent
    if COMPARE.search(text) and re.search(r"objectives?|research goals?|研究目标|研究目的", text, re.I):
        return "description"
    if COMPARE.search(text):
        for intent, pattern in DIMENSIONS:
            if re.search(pattern, text, re.I):
                return intent
    return "description"


def plan_intent(intent, legacy):
    """Preserve strict comparison and causal dependencies for inferential tasks."""
    return {
        "performance_ranking": "performance_ranking", "contradiction_analysis": "conflicting_findings",
        "causal_analysis": "multihop", "literature_synthesis": "literature_synthesis",
        "trend_analysis": "trend_analysis", "method_comparison": "fact",
        "condition_comparison": "fact", "metric_comparison": "fact", "gap_discovery": "fact",
    }.get(intent, legacy)
