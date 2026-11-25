"""Open-domain cross-paper relation extraction, paradigm alignment, and full-scope synthesis (H3)."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import re

from backend.research.claim_verifier import GUARDS, contextual_conditions
from backend.research.discourse_attribution import (
    analyze_clause_attribution,
    has_propositional_negation,
    is_epistemic_speculation,
)
from backend.research.pra_relations import method_name as legacy_method_name
from backend.research.premises import compare_premises
from backend.research.profile_frames import abstract_method, body_profile_supports
from backend.research.research_profile import FUTURE, HYP, attribution, responsive_claims

_METHOD_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "神经网络与深度学习架构",
        (
            "transformer", "bert", "gpt", "neural network", "neural networks", "deep learning",
            "deep neural", "convolutional", "cnn", "recurrent", "rnn", "lstm", "gru",
            "attention", "autoencoder", "diffusion", "graph neural", "gnn", "reinforcement learning",
            "generative adversarial", "gan", "mlp", "perceptron", "pre-trained language model",
            "deep reinforcement", "quantum neural", "tensor network", "neural", "embedding",
        ),
    ),
    (
        "统计、概率与回归建模",
        (
            "logistic regression", "linear regression", "regression", "bayesian", "markov",
            "pomdp", "hidden markov", "maximum likelihood", "gaussian process", "probabilistic",
            "statistical model", "generalized linear", "mixed-effects", "survival analysis",
            "topic model", "latent dirichlet", "lda", "crf", "conditional random field",
            "回归", "贝叶斯", "马尔可夫", "概率模型",
        ),
    ),
    (
        "数学规划与组合优化",
        (
            "mixed-integer", "linear programming", "integer programming", "convex optimization",
            "dynamic programming", "combinatorial optimization", "gradient descent", "lagrangian",
            "tabu search", "simulated annealing", "evolutionary", "differential evolution",
            "genetic algorithm", "constraint programming", "branch-and-bound", "branch and bound",
            "heuristic", "metaheuristic", "qubo", "hobo", "belief tree search", "solver",
            "优化", "规划", "启发式", "动态规划",
        ),
    ),
    (
        "强化学习与序贯决策",
        (
            "q-learning", "q learning", "policy gradient", "actor-critic", "bandit",
            "multi-armed bandit", "markov decision process", "mdp", "pomdp", "bellman",
            "reinforcement learning", "强化学习", "策略梯度", "马尔可夫决策过程",
        ),
    ),
    (
        "集成、树与核支持向量方法",
        (
            "random forest", "random forests", "decision tree", "decision trees",
            "gradient boosting", "xgboost", "adaboost", "support vector", "svm",
            "kernel", "gaussian kernel", "随机森林", "决策树", "支持向量机",
        ),
    ),
    (
        "检索、图结构与符号推理算法",
        (
            "bm25", "retrieval", "clustering", "spectral", "graph", "network", "shortest path",
            "collaborative filtering", "nearest neighbor", "neighbour", "edit distance",
            "superpixel", "region merging", "finite automata", "automaton", "ontology",
            "knowledge graph", "parser", "syntactic", "index", "hashing", "clustering",
            "检索", "聚类", "图算法", "协同过滤",
        ),
    ),
    (
        "数值模拟与控制实验设计",
        (
            "monte carlo", "numerical simulation", "simulations", "simulation", "finite element",
            "randomized controlled", "controlled experiment", "ablation", "user study",
            "crowdsource", "case study", "microbenchmark", "benchmark evaluation", "sampling",
            "survey", "corpus construction", "annotation", "蒙特卡洛", "数值模拟", "案例研究", "实验",
        ),
    ),
    (
        "形式化证明与解析理论推导",
        (
            "formal proof", "theorem", "closed-form", "analytical derivation", "upper bound",
            "lower bound", "complexity analysis", "asymptotic", "theoretical analysis",
            "axiomatic", "invariant", "证明", "解析", "闭式解", "理论推导",
        ),
    ),
)

_AUTHOR_USE_HEAD = re.compile(
    r"^(?:(?:in\s+(?:this|the\s+present)\s+(?:paper|study|work)|here),?\s*)?"
    r"(?:we|our\s+(?:study|work|paper|approach|method|framework|system|model)|this\s+(?:study|paper|work))\s+"
    r"(?:also\s+|first\s+|then\s+|further\s+)?"
    r"(?:use[ds]?|employ(?:s|ed)?|adopt(?:s|ed)?|appl(?:y|ies|ied)|propos(?:e|es|ed)|introduc(?:e|es|ed)|"
    r"present(?:s|ed)?|develop(?:s|ed)?|design(?:s|ed)?|formulat(?:e|es|ed)|construct(?:s|ed)?|"
    r"implement(?:s|ed)?|evaluat(?:e|es|ed)|investigat(?:e|es|ed)|train(?:s|ed)?|build|built|"
    r"combin(?:e|es|ed)|integrat(?:e|es|ed))\s+(?:an?\s+|the\s+|our\s+|novel\s+)?"
    r"(?P<head>[^,.;!?]{3,110}?)(?=\s+(?:to|for|on|in|with|that|which|based|from|into)\b|[.,;!?])",
    re.I,
)

_ZH_USE_HEAD = re.compile(
    r"^(?:本文|本研究|我们)(?:首先|进一步)?(?:采用|使用|提出|设计|构建|实现)(?:了)?(?:一种|一个)?(?P<head>[^，。；！？]{2,48}?)"
    r"(?=用于|来|以|进行|解决|对|[，。；])",
)

_TASK_TAIL = re.compile(
    r"\b(?:to\s+(?:address|solve|tackle|predict|model|classify|segment|retrieve|estimate|schedule|optimize|reduce|detect)|"
    r"for\s+(?:solving|predicting|modeling|modelling|estimating|scheduling|detecting|evaluating)?\s*)"
    r"(?P<task>[a-zA-Z0-9][a-zA-Z0-9 -]{2,70}?)(?=[.,;!?]|\s+(?:using|with|based|on|in)\b|$)",
    re.I,
)

_STOP_HEAD = re.compile(
    r"^(?:this|that|these|those|it|they|them|something|anything|nothing|experiments?|evaluation|analysis|"
    r"framework|approach|method|model|system|algorithm|technique|paper|study|work)$",
    re.I,
)


def classify_method_family(text: str) -> str | None:
    """Assign an explicit lexical method family when named algorithmic/experimental terms appear."""
    lower = text.casefold()
    for family, keywords in _METHOD_FAMILIES:
        for kw in keywords:
            if re.search(r"[\u3400-\u9fff]", kw):
                if kw in lower:
                    return family
            elif re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", lower):
                return family
    return None


def extract_open_method_signature(statement: str, *, discourse: bool = True) -> dict | None:
    """Extract author-owned `(method, family, task)` without relying on a tiny closed list."""
    if GUARDS.search(statement):
        return None
    if FUTURE.search(statement) or HYP.search(statement) or is_epistemic_speculation(statement):
        return None
    if has_propositional_negation(statement):
        return None
    if discourse:
        origin, _, _ = analyze_clause_attribution(statement)
    else:
        origin = attribution(statement)[0]
    if origin != "authors":
        return None

    legacy = legacy_method_name(statement)
    family = classify_method_family(statement)
    head = None
    match = _AUTHOR_USE_HEAD.match(statement.strip()) or _ZH_USE_HEAD.match(statement.strip())
    if legacy:
        head = legacy
    elif match:
        candidate = " ".join(match.group("head").strip().split())
        if len(candidate) >= 3 and not _STOP_HEAD.fullmatch(candidate):
            head = candidate.casefold()
    if not head and family:
        head = family

    task = None
    task_m = _TASK_TAIL.search(statement)
    if task_m:
        cand_task = " ".join(task_m.group("task").strip().casefold().split())
        if not re.search(r"\b(?:this|that|these|those|our|their|such|above|only|not)\b", cand_task):
            task = cand_task

    if not head and not family:
        return None
    return {"method": head, "family": family, "task": task}


def verify_open_synthesis(witnesses_by_paper: dict[str, list], sources: dict[str, dict], scope: set[str]) -> bool:
    """Independently verify full scope coverage, verbatim source coordinates, hashes, and versions."""
    if len(scope) < 2 or set(witnesses_by_paper.keys()) != set(scope):
        return False
    versions = set()
    for pid, claim_list in witnesses_by_paper.items():
        if not claim_list:
            return False
        for c in claim_list:
            if c.support_status != "verified" or c.paper_ids != [pid] or not c.evidence_ids:
                return False
            for eid in c.evidence_ids:
                row = sources.get(eid)
                if not row or row["paper_id"] != pid:
                    return False
                if c.statement not in row["quote"]:
                    return False
                if sha256(row["quote"].encode()).hexdigest() != row["quote_hash"]:
                    return False
                versions.add(row["corpus_generation"])
    return len(versions) == 1


def _compatible_paper_claims(facet: str, claims: list, profile_index, sources: dict[str, dict], requested_set: set[str], *, discourse: bool) -> dict[str, list]:
    """Select verified claims matching the exact q1 field_gate filters so overview dependencies bind cleanly."""
    candidates = responsive_claims(facet, claims, profile_index)
    grouped: dict[str, list] = defaultdict(list)
    has_correction = any(
        re.search(
            r"\b(?:we\s+(?:did\s+not|never)\s+(?:use|apply|adopt)|(?:we|our\s+study)\s+(?:used|uses)\s+.{1,80}\s+instead\s+of|"
            r"(?:correction|erratum)\s*:)|(?:更正|勘误)[：:]|我们并未采用",
            c.statement,
            re.I,
        )
        for c in claims
    )
    for c in candidates:
        pid = c.paper_ids[0]
        if requested_set and pid not in requested_set:
            continue
        if any(sources.get(e, {}).get("field") == "fulltext" for e in c.evidence_ids):
            if not body_profile_supports(c.statement, facet, discourse=discourse):
                continue
        if facet == "method":
            is_abs = any(sources.get(e, {}).get("field") == "abstract" for e in c.evidence_ids)
            if is_abs and re.match(r"^(?:Methods?|研究方法|方法)\s*[:：]", c.statement, re.I):
                if has_correction or not abstract_method(c.statement):
                    continue
        grouped[pid].append(c)
    return grouped


def _paper_title(pid: str, profile_index, sources: dict[str, dict], claim) -> str:
    if profile_index and pid in profile_index and profile_index[pid].title:
        return profile_index[pid].title
    eid = claim.evidence_ids[0]
    return sources.get(eid, {}).get("paper_title") or pid


def open_overview_relations(
    pool: list,
    profile_index,
    sources: dict[str, dict],
    requested: list[str],
    *,
    method_only: bool = False,
    discourse: bool = True,
) -> list[tuple[str, str, list]]:
    """Produce verified full-scope open-domain synthesis rows when all scoped papers are grounded."""
    scope = list(dict.fromkeys(requested or [c.paper_ids[0] for c in pool if len(c.paper_ids) == 1]))
    scope_set = set(scope)
    if len(scope_set) < 2 or profile_index is None:
        return []

    methods_by_paper = _compatible_paper_claims("method", pool, profile_index, sources, scope_set, discourse=discourse)
    findings_by_paper = _compatible_paper_claims("finding", pool, profile_index, sources, scope_set, discourse=discourse)

    method_sigs: dict[str, tuple] = {}
    for pid, clist in methods_by_paper.items():
        for c in clist:
            sig = extract_open_method_signature(c.statement, discourse=discourse)
            if sig is not None:
                method_sigs[pid] = (c, sig)
                break

    out: list[tuple[str, str, list]] = []

    # 1. Full-group method relation when every scoped paper has an extracted author method signature
    if set(method_sigs.keys()) == scope_set:
        witnesses = {pid: [method_sigs[pid][0]] for pid in scope}
        if verify_open_synthesis(witnesses, sources, scope_set):
            sigs = [method_sigs[pid][1] for pid in scope]
            canonical_methods = {s["method"] for s in sigs if s["method"]}
            families = {s["family"] for s in sigs if s["family"]}
            tasks = {s["task"] for s in sigs if s["task"]}
            details = "；".join(
                f"《{_paper_title(pid, profile_index, sources, method_sigs[pid][0])}》采用 {method_sigs[pid][1]['method']}"
                for pid in scope
            )
            flat_witnesses = [method_sigs[pid][0] for pid in scope]

            if len(canonical_methods) == 1 and len({s["method"] is not None for s in sigs}) == 1:
                only_method = next(iter(canonical_methods))
                # Distinguish exact named technique vs family fallback name
                is_family_fallback = all(s["method"] == s["family"] for s in sigs)
                if not is_family_fallback:
                    out.append((
                        "shared_method",
                        f"所选 {len(scope)} 篇论文的作者均明确报告采用相同方法（{only_method}）：{details}。",
                        flat_witnesses,
                    ))
                else:
                    out.append((
                        "shared_method_family",
                        f"所选 {len(scope)} 篇论文均属于同一方法家族（{only_method}），各篇报告的方法证据为：{details}。",
                        flat_witnesses,
                    ))
            elif len(families) == 1 and len(sigs) == sum(bool(s["family"]) for s in sigs):
                shared_fam = next(iter(families))
                out.append((
                    "shared_method_family",
                    f"所选 {len(scope)} 篇论文的研究方法均归属于同一方法家族「{shared_fam}」，具体方法为：{details}。",
                    flat_witnesses,
                ))
            elif len(tasks) == 1 and all(s["task"] for s in sigs):
                shared_task = next(iter(tasks))
                out.append((
                    "different_methods_for_task",
                    f"针对研究任务「{shared_task}」，各篇论文报告了不同的技术路线：{details}。",
                    flat_witnesses,
                ))

    # 2. Complete full-group method + finding cross-paper comparative synthesis
    has_all_methods = set(methods_by_paper.keys()) == scope_set
    has_all_findings = set(findings_by_paper.keys()) == scope_set
    if not method_only and has_all_methods and has_all_findings:
        witnesses_by_paper = {
            pid: list({c.claim_id: c for c in (methods_by_paper[pid][0], findings_by_paper[pid][0])}.values())
            for pid in scope
        }
        if verify_open_synthesis(witnesses_by_paper, sources, scope_set):
            all_findings = [findings_by_paper[pid][0] for pid in scope]
            all_methods = [methods_by_paper[pid][0] for pid in scope]
            conflicts, differences = compare_premises(all_findings, sources)

            # Check whether experimental metric/dataset/protocol conditions actually align across all papers
            cond_tuples = []
            for fc in all_findings:
                quote = sources[fc.evidence_ids[0]]["quote"]
                cond = contextual_conditions(fc.statement, quote)
                cond_tuples.append((cond.dataset, cond.metric_name, cond.evaluation_protocol, cond.experiment_setup))
            conditions_aligned = (
                len({t for t in cond_tuples}) == 1
                and all(cond_tuples[0][:2])
            )

            families_seen = [
                classify_method_family(m.statement) for m in all_methods
            ]
            if len(set(families_seen)) == 1 and families_seen[0] is not None:
                method_summary = f"研究方法上，{len(scope)} 篇论文均涉及「{families_seen[0]}」路径"
                rel_kind = "shared_method_family"
            else:
                method_summary = f"研究方法上，{len(scope)} 篇论文分别采用了各自独立的技术路径与实验设计"
                rel_kind = "different_methods_and_findings"

            per_paper_notes = []
            for pid in scope:
                m_c = methods_by_paper[pid][0]
                f_c = findings_by_paper[pid][0]
                title = _paper_title(pid, profile_index, sources, m_c)
                if m_c.claim_id == f_c.claim_id:
                    per_paper_notes.append(f"《{title}》：{m_c.statement}")
                else:
                    per_paper_notes.append(f"《{title}》方法：{m_c.statement} 结果：{f_c.statement}")

            if conflicts:
                cond_note = "在所报告条件下存在对立结论；需结合具体实验设定核对差异。"
            elif conditions_aligned:
                cond_note = "各篇关键评估条件可核对对齐。"
            elif differences:
                diff_fields = sorted({d for item in differences for d in item.get("differing_fields", ())})
                cond_note = (
                    f"实验条件存在显式差异（{'、'.join(diff_fields)}），不可直接作性能优劣排序。"
                    if diff_fields
                    else "各篇研究任务、数据集或评估指标未对齐，实验条件不可直接比较，仅作逐篇方法与结果对照。"
                )
            else:
                cond_note = "各篇研究任务、数据集或评估指标未对齐，实验条件不可直接比较，仅作逐篇方法与结果对照。"

            statement = f"{method_summary}；{cond_note} " + " ".join(per_paper_notes)
            combined_premises = list(
                {c.claim_id: c for pid in scope for c in witnesses_by_paper[pid]}.values()
            )
            out.append((rel_kind, statement, combined_premises))
    elif not method_only and set(method_sigs.keys()) == scope_set and not out:
        # Every paper has an explicit extracted author method head/family, even if findings/limitations are missing.
        witnesses = {pid: [method_sigs[pid][0]] for pid in scope}
        if verify_open_synthesis(witnesses, sources, scope_set):
            details = "；".join(
                f"《{_paper_title(pid, profile_index, sources, method_sigs[pid][0])}》采用 {method_sigs[pid][1]['method']}"
                + (f"（归属：{method_sigs[pid][1]['family']}）" if method_sigs[pid][1]["family"] else "")
                for pid in scope
            )
            missing_find = [
                f"《{_paper_title(pid, profile_index, sources, method_sigs[pid][0])}》"
                for pid in scope
                if pid not in findings_by_paper
            ]
            out.append((
                "different_methods",
                f"所选 {len(scope)} 篇论文报告了不同的作者研究方法：{details}。"
                + (
                    f"（{'、'.join(missing_find)} 在当前已读来源中缺少作者明确报告的结果陈述，故暂不作跨论文性能比较。）"
                    if missing_find
                    else ""
                ),
                [method_sigs[pid][0] for pid in scope],
            ))
    elif not method_only and has_all_findings and not out:
        # Every paper has verified findings even where one paper's method clause was implicit
        witnesses = {pid: [findings_by_paper[pid][0]] for pid in scope}
        if verify_open_synthesis(witnesses, sources, scope_set):
            per_paper = " ".join(
                f"《{_paper_title(pid, profile_index, sources, findings_by_paper[pid][0])}》：{findings_by_paper[pid][0].statement}"
                for pid in scope
            )
            out.append((
                "different_paper_findings",
                f"所选 {len(scope)} 篇论文均包含可核验的作者研究结果，但各篇研究方法或实验条件尚未完整对齐（不可直接比较优劣）：{per_paper}",
                [findings_by_paper[pid][0] for pid in scope],
            ))

    return out
