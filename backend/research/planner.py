"""Offline planning and coverage-driven query refinement for one research agent."""
import re
from backend.research.schemas import ResearchState, Subtask


SIGNALS = {
    "method": ("method", "approach", "architecture", "algorithm", "retriever", "model", "方法", "模型"),
    "dataset": ("dataset", "benchmark", "corpus", "evaluated on", "数据集", "语料"),
    "metric": ("precision", "recall", "ndcg", "accuracy", "score", "metric", "f1", "指标", "准确率"),
    "protocol": ("protocol", "split", "evaluation", "setting", "条件", "协议", "划分"),
    "limitation": ("limitation", "caveat", "however", "limited", "局限", "限制"),
}
STOPWORDS = set("which what how why with using used from this that their these those the and for are was were has have does did across between under list compare comparison study research paper papers describe report result results explain find give tell please according they than it an of to is a as in on by at".split())


def words(text: str) -> list[str]:
    return list(dict.fromkeys(w for w in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]{2,}", text.lower())
                              if w not in STOPWORDS))



# Question head and matching measured unit. "Current studies" is not an electrical question.
QUANTITIES = (
    (r"\b(?:battery|electric(?:al)?|supply|load|operating|device)\s+current\b|\bcurrent\s+(?:draw|consumption)|\b(?:what|which|much)\s+current\s+(?:did|does|was|is)\b|\b(?:milli)?amp(?:ere)?s?\b", r"(?:mA|µA|μA|uA|A|(?:milli|micro)?amp(?:ere)?s?)"),
    (r"\bvoltage\b|\bvolts?\b", r"(?:[mkµμu]?V|(?:milli|micro|kilo)?volts?)"),
    (r"\b(?:power (?:draw|consumption)|wattage|watts?)\b", r"(?:[mkµμu]?W|(?:milli|kilo)?watts?)"),
    (r"\b(?:energy consumption|energy use|joules?)\b", r"(?:[mk]?J|(?:milli|kilo)?joules?|[mk]?Wh)"),
    (r"\b(?:latency|response time|elapsed time|runtime|run time)\b", r"(?:[munµμ]?s|(?:milli|micro|nano)?seconds?|minutes?|hours?)"),
    (r"\b(?:memory consumption|memory footprint|peak memory|RAM usage)\b", r"(?:[KMGTP]i?B|(?:kilo|mega|giga|tera)?bytes?)"),
)
QUANTITY_PATTERNS = [
    (re.compile(head, re.I), re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s*" + unit + r"(?!\w)", re.I))
    for head, unit in QUANTITIES
]


def quantity_matches(goal, text):
    """An explicit physical quantity needs a number in the corresponding dimension."""
    return all(not head.search(goal) or unit.search(text) for head, unit in QUANTITY_PATTERNS)


RANKING_QUESTION = re.compile(r"\b(?:leaderboard|rank(?:ed|ing)?\s+(?:on|against|by))\b", re.I)


def comparison_requested(goal):
    return bool(RANKING_QUESTION.search(goal) or re.search(r"\b(?:compar(?:e|ing|ison)|contrast)\b|比较|对比", goal, re.I))


def requested_slots(goal: str) -> list:
    low = goal.casefold()
    slots = [key for key, terms in SIGNALS.items() if any(w in low for w in terms)]
    if RANKING_QUESTION.search(goal):
        # Find the per-paper observations before searching for comparable measurements.
        return list(dict.fromkeys(["fact", "metric", *slots]))
    if comparison_requested(goal):
        slots = list(dict.fromkeys([*slots, "method", "dataset", "metric", "protocol"]))
    return slots or ["fact"]


def plan(state: ResearchState) -> list[Subtask]:
    return [Subtask(id=f"s{i}", goal=state.task.goal[:460] + " · " + slot,
                    required_slots=[slot], missing_slots=[slot], priority=i)
            for i, slot in enumerate(requested_slots(state.task.goal)[:6], 1)]


def query_for(state: ResearchState, slot: str) -> str:
    if not state.queries:
        return state.task.goal[:500]
    tokens = words(state.task.goal)
    # A focused second query keeps distinctive entities while removing broad task instructions.
    all_signals = {token for items in SIGNALS.values() for phrase in items for token in words(phrase)}
    entities = [w for w in tokens if w not in all_signals and len(w) > 2]
    terms = SIGNALS.get(slot, ("evidence",))
    prior = sum(q.subtask_id == next((s.id for s in state.subtasks if slot in s.required_slots), "")
                for q in state.queries)
    signal = terms[min(prior, len(terms) - 1)]
    return (" ".join([*entities[:3], signal]) or state.task.goal)[:500]


def covers(slot: str, text: str, goal: str) -> bool:
    """Conservative lexical slot observation; never a human support judgment."""
    if not quantity_matches(goal, text):
        return False
    content = text.casefold()
    tokens = set(words(content))
    goal_tokens = set(words(goal))
    entities = [w.casefold() for w in re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}\b", goal)
                if w.casefold() not in STOPWORDS | {"under", "did", "name", "identify", "report", "list",
                                                     "retrieval", "what", "give", "provide", "identify"}]
    if entities and not any(w in content for w in entities):
        return False
    if not (tokens & goal_tokens or any(w in content for w in goal_tokens if len(w) >= 3)):
        return False
    if slot == "fact":
        return True
    if slot == "metric" and not re.search(r"\d", text):
        return False
    return any(term in content for term in SIGNALS.get(slot, ()))
