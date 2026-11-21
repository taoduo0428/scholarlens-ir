"""Compile validated DAG nodes, their evidence obligations and server-authorized scope."""

import re

from backend.research.field_contract import AnswerRequirement, TITLES, field_for, requests

# Requirements are projected from node roles and paper scope. Lexical hints only
# select dimensions inside an existing role. They never create permissions.
LABELS = {
    "method": ("研究方法", "reported method"),
    "dataset": ("实验数据集", "evaluation dataset"),
    "metric": ("评价指标", "evaluation metric"),
    "finding": ("主要结果", "reported finding"),
    "topic": ("研究主题", "study topic"),
    "conditions": ("实验条件是否对齐", "alignment of experimental conditions"),
    "comparison": ("结果差异", "supported difference in results"),
    "overview": ("综合研究发现", "cross-paper synthesis"),
    "chain": ("原文支持的因果关系", "source-supported causal link"),
    "conflict": ("相反结论及其适用条件", "opposing conclusions and their conditions"),
}
HINTS = {
    "method": r"method|approach|方法|途径",
    "dataset": r"dataset|corpus|corpora|数据集|语料",
    "metric": r"metric|measure|指标|accuracy|precision|recall|f1|ndcg",
    "finding": r"result|finding|outcome|conclusion|结果|发现|结论",
}
METRICS = re.compile(r"\b(?:accuracy|precision|recall|f1|ndcg|mrr|rmse|mae)\b|准确率|召回率|精确率", re.I)


def dimensions(plan, node, contract):
    role = node.requirement.kind
    goal = TITLES.sub("", contract.goal)
    text = node.question if plan.origin == "personal_model" else goal
    if contract.answer_type == "overview":
        return {"source_fact": ["topic", "finding"], "mechanism": ["method"],
                "synthesis": ["overview"]}.get(role, ["finding"])
    if contract.answer_type == "causal_chain":
        return ["chain"]
    if contract.answer_type == "disagreement":
        return ["conflict"] if role in {"synthesis", "comparison"} else ["finding" if role == "source_fact" else "conditions"]
    if role == "source_fact":
        return [k for k in ("method", "finding") if re.search(HINTS[k], text, re.I)] or ["finding"]
    if role == "conditions":
        selected = [k for k in ("dataset", "metric") if re.search(HINTS[k], text, re.I)]
        return selected + ["conditions"] if contract.answer_type != "methods" else ["method"]
    if role == "comparison":
        return ["comparison"]
    if role == "synthesis":
        return ["overview"]
    return ["chain" if role == "mechanism" else "finding"]


def compile_fields(plan, contract):
    scope = list(dict.fromkeys(contract.scope["paper_ids"]))
    chinese = bool(re.search(r"[\u3400-\u9fff]", contract.goal))
    one = len(plan.graph.nodes) == 1
    result = []
    for node in plan.graph.nodes:
        fields = []
        if one:
            question = node.question if plan.origin == "personal_model" else contract.goal
            for i, request in enumerate(requests(question), 1):
                f = field_for(node, contract, request, i)
                fields.append(f.model_copy(update={"min_evidence": 1}))
        else:
            facets = dimensions(plan, node, contract)
            for facet in facets:
                per_paper = facet in {"method", "dataset", "metric", "finding", "topic"}
                targets = [[p] for p in scope] if per_paper and 0 < len(scope) <= 4 else [scope]
                metrics = list(dict.fromkeys(m.casefold() for m in METRICS.findall(TITLES.sub("", contract.goal))))
                for papers in targets:
                    for metric in (metrics if facet in {"metric", "comparison"} and metrics else [None]):
                        label = LABELS[facet][0 if chinese else 1]
                        request = f"{label} ({metric})" if metric else label
                        if plan.origin == "personal_model":
                            request = f"{node.question} · {request}"
                        if len(targets) > 1:
                            request = f"{request} · {papers[0]}"
                        f = field_for(node, contract, request, len(fields) + 1)
                        count = 2 if facet in {"comparison", "overview", "conflict"} else 1
                        changes = dict(facet=facet, paper_ids=papers, requested_metric=metric,
                                       min_evidence=2 if facet in {"chain", "overview"} else 1,
                                       min_papers=count, acceptance=f"{request}: {node.requirement.acceptance}")
                        fields.append(f.model_copy(update=changes))
        result.append(AnswerRequirement(contract_binding=contract.binding, original_goal=contract.goal,
                                        node_question=node.question, question_id=node.id,
                                        dependencies=node.dependencies, fields=fields))
    return result
