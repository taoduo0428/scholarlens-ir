"""Identify explicit study predicates and their arguments in complete source sentences."""

import re


SUBJECT = r"(?:we|this (?:paper|study|work|article)|our (?:study|paper|work))"
LEAD = rf"^(?:(?:in (?:this|the present) (?:paper|study|work)|here),? )?{SUBJECT} (?:also |first |then )?"
CLAUSE = re.compile(r"\b(?:if|whether|would|should|could|might|may|not|never|previously|according to)\b|"
                    r"据称|未能|并非|可能|如果|没有", re.I)
OBJECTIVE = re.compile(LEAD + r"(?:address(?:es)?|examin(?:e|es|ed)|investigat(?:e|es|ed)|"
                       r"stud(?:y|ies|ied)|analy[sz](?:e|es|ed)|consider(?:s|ed)?|explor(?:e|es|ed)|"
                       r"work(?:s|ed)? on|focus(?:es|ed)? on) "
                       r"(?!using\b|only\b)[a-z0-9][^.;!?]{6,}", re.I)
REPRESENT = re.compile(LEAD + r"(?:(?:formulat(?:e|es|ed)|model(?:s|led|ed)?|represent(?:s|ed)?|"
                       r"encod(?:e|es|ed)) [^.;!?]{2,140} (?:as|using|with) [^.;!?]{2,}"
                       r"|(?:introduc(?:e|es|ed)|propos(?:e|es|ed)|present(?:s|ed)?) "
                       r"[^.;!?]{2,100} representations? for [^.;!?]+)", re.I)
DECISION = re.compile(r"\b(?:markov decision process(?:es)?|decision trees?|mixed.integer "
                      r"(?:linear )?program(?:ming)?|decision models?)\b|马尔可夫决策过程|决策树|混合整数规划", re.I)
METHOD = re.compile(LEAD + r"(?:implement(?:s|ed)?|appl(?:y|ies|ied)|train(?:s|ed)?|"
                    r"simulat(?:e|es|ed)|reconstruct(?:s|ed)?|encod(?:e|es|ed)|combin(?:e|es|ed)|"
                    r"solv(?:e|es|ed)) [^.;!?]{4,}", re.I)
CHINESE = re.compile(r"^(?:为.{2,50}[，,])?(?:本文|本研究|我们)(?:首先|进一步)?"
                     r"(?P<verb>研究|考察|探讨|分析|构建|训练|采用|使用|设计|提出|将)(?P<object>[^。！？]{3,})")
RESULT = re.compile(r"^(?:our (?:experimental |simulation |numerical )?(?:results?|analysis|experiments?) "
                    r"(?:show|indicate|reveal|demonstrate|confirm)s? (?:that )?|"
                    r"(?:我们的(?:实验|结果)|本研究的(?:结果|分析))(?:表明|显示|证实))", re.I)
DESIGN_OBJECT = re.compile(
    LEAD + r"(?:present(?:s|ed)?|introduc(?:e|es|ed)|propos(?:e|es|ed)|develop(?:s|ed)?|"
    r"construct(?:s|ed)?) (?:an? |the )?[^.;!?]{0,90}?"
    r"\b(?:method|procedure|model|approach|framework|algorithm|scheme) "
    r"(?:for|which|that|to|based on|using)\b", re.I)
VARIABLES = {
    "input_variables": r"(?:our (?:model|method|system) (?:takes|accepts|uses) .{2,100} as inputs?|"
                       r"the inputs? to our (?:model|system) (?:is|are) |(?:本模型|我们的方法)的输入(?:为|是))",
    "state": r"(?:(?:we define the state as|our state (?:is|consists of)) |我们将状态定义为)",
    "action": r"(?:(?:we define the action as|our action space (?:is|consists of)) |我们将动作定义为)",
    "reward": r"(?:(?:we define the reward as|our reward (?:function )?(?:is|equals)) |我们将奖励定义为)",
}

PASSIVE_PROPOSAL = re.compile(
    r"^(?:in (?:this|the present|the) (?:paper|article|study|work),? )?"
    r"(?:an?|the) [^.;!?]{0,95}?\b(?:approach|method|algorithm|procedure|model|framework|scheme) "
    r"(?:for|to) (?P<task>[^.;!?]{3,140}?) (?:is|was) (?:here |herein )?"
    r"(?:proposed|introduced|developed|presented)(?=[.!]| (?:that|which|to|for|using)\b)", re.I)


def passive_proposal(text):
    """Keep the purpose clause with the passive proposal and reject external attribution."""
    if CLAUSE.search(text) or re.search(r"\b(?:by|earlier|prior|previous|originally|previously)\b", text, re.I):
        return False
    return bool(PASSIVE_PROPOSAL.match(text))


def frame_fields(text):
    """Return only roles licensed by a stated author predicate, preserving the entire sentence."""
    if CLAUSE.search(text):
        return set()
    fields = set()
    if OBJECTIVE.search(text):
        fields.add("research_objective")
    if passive_proposal(text):
        fields.update(("methods", "research_objective", "proposed_contributions"))
    if METHOD.search(text) or DESIGN_OBJECT.search(text):
        fields.add("methods")
    if REPRESENT.search(text):
        fields.update(("representations", "methods"))
    if DECISION.search(text) and (REPRESENT.search(text) or METHOD.search(text) or
                                 re.search(LEAD + r"(?:use|adopt|employ)(?:s|ed)? ", text, re.I)):
        fields.add("decision_models")
    if RESULT.search(text):
        fields.add("reported_findings")
    match = CHINESE.search(text)
    if match:
        if match["verb"] in {"研究", "考察", "探讨", "分析"}:
            fields.add("research_objective")
        elif match["verb"] != "将":
            fields.add("methods")
        if re.search(r"(?:表示|建模|编码)为", match["object"]):
            fields.add("representations")
            if DECISION.search(match["object"]):
                fields.add("decision_models")
    fields.update(k for k, pattern in VARIABLES.items() if re.match(pattern, text, re.I))
    return fields


def abstract_method(text):
    """A Methods label plus a study procedure, never a section label alone."""
    match = re.fullmatch(r"(?:Methods?|研究方法|方法)\s*[:：]\s*(.+[.。])", text, re.I)
    if not match:
        return False
    body = match[1]
    if (CLAUSE.search(body) or re.search(r"\b(?:earlier|prior|previous|another|historical|other (?:studies|authors)|"
            r"planned|plans?|literature suggests|by others|instead|elsewhere|(?:in|by) (?:a|the) previous study)\b|前人|此前|计划|曾有", body, re.I)
            or re.search(r"\b(?:i\.e|e\.g|et al)\.$|(?:Results?|Conclusions?|Background)\s*:", body, re.I)):
        return False
    return bool(re.search(
        r"\bwe (?:have |also )?(?:used?|perform(?:ed)?|conduct(?:ed)?|carried out|develop(?:ed)?|"
        r"evaluat(?:e|ed)|propos(?:e|ed)|adopt(?:ed)?|implement(?:ed)?|address\b.{1,70}by performing)\b|"
        r"\b(?:was|were|is|are) (?:optimized|ported|recruited|trained|sampled|measured|"
        r"encoded|simplified|implemented|composed of)\b|(?:本研究|本文|我们)(?:采用|使用|测量|采样)", body, re.I))
