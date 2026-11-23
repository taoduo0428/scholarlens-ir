"""Compile validated DAG nodes, their evidence obligations and server-authorized scope."""

import re

from backend.research.field_contract import (
    AnswerFieldType, AnswerRequirement, RequiredSourceCapability, TITLES, field_for, requests,
)

# Requirements are projected from node roles and paper scope. Lexical hints only
# select dimensions inside an existing role. They never create permissions.
LABELS = {
    "limitations": ("原文明确指出的局限或开放问题", "limitations or open questions stated by the authors"),
    "method": ("研究方法", "reported method"),
    "dataset": ("实验数据集", "evaluation dataset"),
    "metric": ("评价指标", "evaluation metric"),
    "finding": ("主要结果", "reported finding"),
    "topic": ("研究主题", "study topic"),
    "conditions": ("实验条件是否对齐", "alignment of experimental conditions"),
    "comparison": ("结果差异", "supported difference in results"),
    "trend": ("原文支持的时间趋势", "documented time trend"),
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
    if plan.contract.intent in {"literature_synthesis", "trend_analysis"}:
        return (["topic", "method", "finding"] if role == "source_fact" else
                ["trend"] if plan.contract.intent == "trend_analysis" else ["overview"])
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


def compile_fields(plan, contract, *, profile_gaps=False, independent=False, pra=False):
    scope = list(dict.fromkeys(contract.scope["paper_ids"]))
    chinese = bool(re.search(r"[\u3400-\u9fff]", contract.goal))
    one = len(plan.graph.nodes) == 1
    result = []
    for node in plan.graph.nodes:
        fields = []
        from backend.research.research_intent import research_intent
        research_type = research_intent(contract.goal) if independent else None
        dimensions_by_intent = {
            "method_comparison": ["method"], "metric_comparison": ["metric"],
            "condition_comparison": ["dataset" if re.search(HINTS["dataset"], contract.goal, re.I) else "setting"],
            "gap_discovery": ["limitations"],
        }
        independent_facets = dimensions_by_intent.get(research_type)
        intent_goal = TITLES.sub(" ", contract.goal)
        named_targets = []
        if research_type == "description" and re.search(r"objectives?|research goals?|研究目标|研究目的", intent_goal, re.I):
            # Mixed objectives, representation and units still need independent proofs.
            if not re.search(r"unit of analysis|representation|分析单位|数据表示", intent_goal, re.I):
                independent_facets = ["objective"]
        if pra and one and scope and len(scope) <= 4 and research_type in {
            "description", "method_comparison", "condition_comparison", "metric_comparison"
        } and re.search(r"compar|contrast|比较|对比", intent_goal, re.I):
            dimensions_requested = [k for k, rx in {
                "objective": r"objectives?|research goals?|研究目标|研究目的",
                "method": r"\bmethods?\b|研究方法|方法",
                "decision_model": r"decision models?|决策模型",
                "setting": r"experimental (?:conditions?|settings?)|实验条件|实验设置",
                "finding": r"reported (?:findings?|results?)|研究结果|实验结果",
                "metric": r"evaluation metrics?|评价指标",
            }.items() if re.search(rx, intent_goal, re.I)]
            # Named titles can denote a strict subset of the permitted library.
            if (len(dimensions_requested) >= 2
                    and not re.search(r"rank|caus|contradict|unit of analysis|representation|排名|因果|矛盾", intent_goal, re.I)):
                titles = list(dict.fromkeys(match[0][1:-1].strip() for match in TITLES.finditer(contract.goal)))
                if not titles or len(titles) <= 4 and all(0 < len(t) <= 500 for t in titles):
                    independent_facets = dimensions_requested
                    named_targets = titles
        from backend.research.descriptive_plan import comparison_subjects, requested_dimensions
        subjects = comparison_subjects(contract.goal) if independent and one and research_type == "description" else []
        typed = requested_dimensions(intent_goal)
        from backend.research.study_brief import brief_remainder, named_problem_method
        title = named_problem_method(contract.goal) if independent and scope else None
        from backend.research.multihop_fields import link_field, link_request
        link = link_request(contract.goal) if independent and contract.answer_type == "causal_chain" else None
        compiled_link = link_field(node, contract, link) if link else None
        from backend.research.quantitative_evidence import quantity_fields
        quantitative = quantity_fields(node, contract) if independent and one else []
        if quantitative:
            fields.extend(quantitative)
        elif compiled_link is not None:
            fields.append(compiled_link)
        elif (title and len(title) <= 500 and node.requirement.kind == "source_fact"
                and (contract.answer_type == "causal_chain" or (one and research_type == "description"))
                and not any(field_for(node, contract, part, 1).operation in {"layout", "quote"}
                            for part in requests(contract.goal))):
            for facet in ("problem", "method"):
                label = {"problem": "研究问题", "method": "研究方法"}[facet] if chinese else facet
                request = f"《{title}》 · {label}"
                field = field_for(node, contract, request, len(fields) + 1)
                fields.append(field.model_copy(update={"required_title": title, "facet": facet,
                    "operation": "fact", "min_evidence": 1, "min_papers": 1,
                    "acceptance": f"Source explicitly states the {facet} of this study."}))
            if one:
                for request in brief_remainder(contract.goal):
                    field = field_for(node, contract, request, len(fields) + 1)
                    fields.append(field.model_copy(update={"required_title": title, "min_evidence": 1}))
        elif subjects and typed and not any(f.operation == "layout" for f in
                [field_for(node, contract, part, 1) for part in requests(contract.goal)]):
            for subject in subjects:
                for dim in typed:
                    request = f"{subject} · {dim}"
                    f = field_for(node, contract, request, len(fields) + 1)
                    fields.append(f.model_copy(update={"facet": dim, "subject": subject, "operation": "fact",
                        "min_evidence": 1, "min_papers": 1, "acceptance": f"Source states {dim} for {subject}."}))
        elif one and independent_facets and len(scope) <= 4 and not any(
            field_for(node, contract, part, 1).operation in {"layout", "quote"} for part in requests(contract.goal)
        ):
            targets = [(None, title) for title in named_targets] or [(p, None) for p in scope or [None]]
            for paper, title in targets:
                for facet in independent_facets:
                    f = field_for(node, contract, contract.goal, len(fields) + 1)
                    metric_names = list(dict.fromkeys(m.casefold() for m in METRICS.findall(intent_goal)))
                    for metric in metric_names if facet == "metric" and metric_names else [None]:
                        fields.append(f.model_copy(update={"field_id": f"{node.id}.f{len(fields)+1}",
                            "facet": facet, "paper_ids": [paper] if paper else [], "requested_metric": metric,
                            **({"required_title": title, "request": f"《{title}》 · {facet}"} if title else {}),
                            "min_evidence": 1, "min_papers": 1}))
        elif one:
            question = node.question if plan.origin == "personal_model" else contract.goal
            from backend.research.subject_facts import parse_request
            previous_subject = None
            for i, request in enumerate(requests(question), 1):
                f = field_for(node, contract, request, i)
                changes = {"min_evidence": 1}
                if independent and research_type == "description" and question == contract.goal:
                    previous_subject = parse_request(request, previous_subject)
                    if previous_subject:
                        changes.update(facet=previous_subject.facet, subject=previous_subject.subject,
                                       subject_context=previous_subject.context, operation="attribute",
                                       datatype=AnswerFieldType.text, capability=RequiredSourceCapability(requires="text"))
                fields.append(f.model_copy(update=changes))
        else:
            facets = dimensions(plan, node, contract)
            if profile_gaps and contract.answer_type == "overview" and "overview" in facets and re.search(
                r"open questions?|limitations?|future (?:work|research)|仍待|待解决|局限|不足", contract.goal, re.I
            ):
                facets = [*facets, "limitations"]
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
                        count = 2 if facet in {"comparison", "overview", "conflict", "trend"} else 1
                        changes = dict(facet=facet, paper_ids=papers, requested_metric=metric,
                                       min_evidence=2 if facet in {"chain", "overview"} else 1,
                                       min_papers=count, acceptance=f"{request}: {node.requirement.acceptance}")
                        fields.append(f.model_copy(update=changes))
        result.append(AnswerRequirement(contract_binding=contract.binding, original_goal=contract.goal,
                                        node_question=node.question, question_id=node.id,
                                        dependencies=node.dependencies, fields=fields))
    return result
