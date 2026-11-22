"""Typed E11 relations over source-verified, author-attributed method statements."""
import re
from collections import defaultdict

from backend.research.premises import compare_premises
from backend.research.research_profile import responsive_claims


# Only normalize explicit technique names. Different names license a contrast
# only when the authors also name the same task in the same sentence.
TECHNIQUES = {
    "BM25": ("BM25",),
    "BERT": ("BERT",),
    "logistic regression": ("logistic regression", "逻辑回归"),
    "linear regression": ("linear regression", "线性回归"),
    "random forests": ("random forests", "a random forest", "随机森林"),
    "Monte Carlo simulation": ("Monte Carlo simulation", "Monte Carlo simulations", "蒙特卡洛模拟"),
    "finite element analysis": ("finite element analysis", "有限元分析"),
    "support vector machines": ("support vector machines", "a support vector machine", "支持向量机"),
}
NAMES = {alias.casefold(): name for name, aliases in TECHNIQUES.items() for alias in aliases}
NAME = "(?P<method>" + "|".join(map(re.escape, NAMES)) + ")"
EN = re.compile(r"(?:we (?:used?|employ(?:ed)?|adopt(?:ed)?)|this study (?:uses|used|employs|employed)) "
                + NAME + r"(?: for (?P<task>[\w-]+(?: [\w-]+){0,6}))?\.", re.I)
ZH = re.compile(r"(?:我们|本研究|本文)(?:采用|使用)(?:了)?" + NAME + r"(?:用于(?P<task>[\u3400-\u9fff]{2,16}))?。", re.I)
TASK_REFERENCE = re.compile(r"\b(?:the|this|that|our|its|their|these|those|not|no|except|only|if|and|or|but)\b|该|上述|此|本次|仅|除外")
DESIGNS = {
    "形式证明": r"(?:we (?:also )?prove (?:that |the existence of |a theorem\b)|(?:本文|我们)证明了)",
    "数值模拟": r"(?:we (?:use|present|perform|conduct) (?:numerical|Monte Carlo) simulations?\b|(?:本文|我们)(?:采用|进行)了?数值模拟)",
    "案例研究": r"(?:we (?:present|conduct|report) (?:a case study|case studies) (?:of|on) |(?:本文|我们)(?:开展|进行)了案例研究)",
    "解析推导": r"(?:we derive (?:a closed.form (?:expression|solution)|an analytical (?:expression|solution))\b|(?:本文|我们)推导出.{0,12}(?:闭式解|解析表达式))",
}
DESIGN_PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in DESIGNS.items()}


def method_relations(claims, index, requested):
    """Yield one verified premise per paper for each relation in the requested set."""
    by_method, by_task, by_design = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for claim in responsive_claims("method", claims, index):
        pid = claim.paper_ids[0]
        if requested and pid not in requested:
            continue
        for design, pattern in DESIGN_PATTERNS.items():
            if pattern.match(claim.statement):
                by_design[design].setdefault(pid, claim)
        match = EN.fullmatch(claim.statement) or ZH.fullmatch(claim.statement)
        if not match:
            continue
        name = NAMES[match["method"].casefold()]
        by_method[name].setdefault(pid, claim)
        task = (match["task"] or "").casefold()
        if task and not TASK_REFERENCE.search(task):
            by_task[task].setdefault(pid, {})[name] = claim
    for name, papers in sorted(by_method.items()):
        if len(papers) >= 2:
            yield "shared_method", f"{len(papers)} 篇论文的作者均报告使用了 {name}。", list(papers.values())
    for design, papers in sorted(by_design.items()):
        if len(papers) >= 2:
            yield "shared_research_design", f"{len(papers)} 篇论文的作者均报告采用了{design}。", list(papers.values())
    for task, papers in sorted(by_task.items()):
        if len(papers) < 2 or any(len(methods) != 1 for methods in papers.values()):
            continue
        names = sorted({name for methods in papers.values() for name in methods})
        if len(names) >= 2:
            yield ("different_methods_for_task",
                   f"对于「{task}」，这些论文报告使用的方法包括{'、'.join(names)}。",
                   [next(iter(methods.values())) for methods in papers.values()])


DIRECTION = re.compile(
    r"(?:we (?:find|found|show)|our results (?:show|indicate)) that "
    r"(?P<measure>accuracy|recall|precision|error|latency|yield|sensitivity|specificity) "
    r"(?P<verb>increases?|increased|decreases?|decreased) "
    r"(?P<setting>(?:on|in|under|at) [\w-]+(?: [\w-]+){0,5})\.", re.I)


def finding_relations(claims, index, requested, sources):
    rows = [c for c in responsive_claims("finding", claims, index)
            if not requested or c.paper_ids[0] in requested]
    groups = defaultdict(dict)
    for c in rows:
        match = DIRECTION.fullmatch(c.statement)
        if match and not TASK_REFERENCE.search(match["setting"].casefold()):
            key = match["measure"].casefold(), match["setting"].casefold()
            sign = match["verb"].lower().startswith("increas")
            groups[key].setdefault(c.paper_ids[0], {})[sign] = c
    for (measure, setting), papers in sorted(groups.items()):
        if len(papers) < 2 or any(len(signs) != 1 for signs in papers.values()):
            continue
        same = len({sign for signs in papers.values() for sign in signs}) == 1
        yield ("shared_direction" if same else "different_directions",
               f"在原文所述的「{setting}」条件下，作者报告的 {measure} 变化方向{'相同' if same else '不同'}。",
               [next(iter(signs.values())) for signs in papers.values()])
    by_id = {c.claim_id: c for c in rows}
    conflicts, differences = compare_premises(rows, sources)
    for edge in conflicts + differences:
        if edge["basis"] == "missing_conditions":
            continue
        statement = ("在所列相同实验条件下，两篇论文报告了相反结论。" if edge["relation"] == "contradicts"
                     else "两项陈述的实验条件有差异：" + "、".join(edge["differing_fields"]) + "。")
        yield edge["relation"], statement, [by_id[i] for i in edge["claim_ids"]]
