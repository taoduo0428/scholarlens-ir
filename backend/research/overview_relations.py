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

# A model must be the object the authors build, or the setting in which they
# add a specified mechanism. A "model comparison" or "model selection method"
# has a different head noun and supplies neither witness.
MODEL_ACTION = re.compile(
    r"(?:we (?:propos(?:e|ed)|develop(?:ed)?|introduc(?:e|ed)|construct(?:ed)?|build|built) "
    r"(?:a|an) (?P<modifiers>(?:[a-z][a-z0-9-]* ){0,4})"
    r"model (?:of|for|to|that|which|combining|incorporating|describing|based on) |"
    r"in our model,? we (?:introduce|add|incorporate) (?:a |an |the )?"
    r"(?:feedback|coupling|interaction|constraint|noise term) (?:between|among|on|for|from|into|to) )"
    r"(?P<detail>[\w][^\n]*?)\.", re.I)
MODEL_ACTION_ZH = re.compile(
    r"(?:本文|我们|本研究)(?:构建|提出|设计)了?(?:一个|一种)?(?:用于|用以|描述|刻画|解释|模拟)"
    r"[\u3400-\u9fff]{3,80}的(?:数学|统计|概率|计算|理论)?模型。")
MODEL_QUALIFIER = re.compile(
    r"\b(?:if|unless|whether|never|neither|not|would|will|plan|hope|hypothetically|hypothetical|"
    r"previously|elsewhere|attributed|quoted)\b|未能|假如|能否|计划|此前|前人", re.I)
MODIFIER_BOUNDARY = re.compile(
    r"\b(?:a|an|the|this|that|our|their|his|her|its|your|my|of|for|on|at|in|with|by|as|"
    r"from|to|into|over|under|via|and|or|but|than|called|named|versus|against|about|"
    r"without|review|comparison|evaluation|critique|survey)\b", re.I)
GERUND_MODIFIERS = {"learning", "forecasting", "ranking", "matching", "sampling", "reasoning"}


def describes_model_construction(statement: str) -> bool:
    """Recognize a completed, author-owned model design statement with substantive detail."""
    if MODEL_QUALIFIER.search(statement):
        return False
    if MODEL_ACTION_ZH.fullmatch(statement):
        return True
    match = MODEL_ACTION.fullmatch(statement)
    if not match:
        return False
    modifiers = (match["modifiers"] or "").casefold()
    if (MODIFIER_BOUNDARY.search(modifiers) or
            any(w.endswith("ing") and w not in GERUND_MODIFIERS for w in modifiers.split())):
        return False
    detail = match["detail"]
    return (len(re.findall(r"\b[\w-]+\b", detail)) >= 2
            and not re.search(r"(?:[.,;:]|\b(?:a|an|and|or|of|to|for|the|that|with|e\.g|i\.e))$", detail, re.I))


def method_relations(claims, index, requested):
    """Yield one verified premise per paper for each relation in the requested set."""
    by_method, by_task, by_design = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    model_builders = {}
    for claim in responsive_claims("method", claims, index):
        pid = claim.paper_ids[0]
        if requested and pid not in requested:
            continue
        if describes_model_construction(claim.statement):
            model_builders.setdefault(pid, claim)
        for design, pattern in DESIGN_PATTERNS.items():
            if pattern.match(claim.statement):
                by_design[design].setdefault(pid, claim)
        match = EN.fullmatch(claim.statement) or ZH.fullmatch(claim.statement)
        if not match or re.search(r"\b(?:neither|nor|never|not|no|unless|except|without|if|only)\b|并非|除外|仅当|而非",
                                  match["task"] or "", re.I):
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
    if len(model_builders) >= 2 and (not requested or set(model_builders) == set(requested)):
        witnesses = [model_builders[pid] for pid in sorted(model_builders)]
        details = [f"《{index[c.paper_ids[0]].title}》 — {c.statement}" for c in witnesses]
        yield ("shared_research_design", "这些论文的共同研究手段是构建模型或在模型中引入机制。\n"
               + "\n".join(details), witnesses)
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
