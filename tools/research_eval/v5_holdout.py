"""Preregistered held-out multi-document tasks. The graph receives only public inputs."""

import json
from hashlib import sha256

from backend.research.claim_verifier import sentences
from tools.research_eval.e9_accept import public_cases
from tools.research_eval.inputs import BENCH, GENERATION, OID
from tools.research_eval.workspace_suite import corpus_file, excluded


def cases():
    used = excluded().union(*(set(docs) for _, _, docs, _, _ in public_cases()))
    frozen = json.loads((BENCH / "workspace-v4-frozen.json").read_bytes())
    for group in frozen["dataset"]["groups"]:
        used.update(p["paper_id"] for p in group["papers"])
    pool = []
    digest = sha256()
    with corpus_file().open("rb") as stream:
        for line in stream:
            digest.update(line)
            paper = json.loads(line)
            opening = sentences(paper.get("abstract", ""))
            if (paper["paper_id"] not in used and paper.get("title") and opening
                    and paper["abstract"].startswith(opening[0]) and opening[0].endswith(".")):
                pool.append({k: paper[k] for k in ("paper_id", "title", "abstract")})
    if digest.hexdigest() != OID:
        raise ValueError("unexpected source corpus")
    def key(salt, paper):
        return sha256((salt + paper["paper_id"]).encode()).digest()
    chinese = sorted(pool, key=lambda p: key("e9/cn-final/", p))[:6]
    selected = sorted((p for p in pool if p not in chinese), key=lambda p: key("v5/holdout/1/", p))[:12]
    assert len(selected) == 12
    for i in range(0, 12, 2):
        p, other = selected[i:i + 2]
        docs = {r["paper_id"]: r for r in (p, other)}
        title = p["title"]
        for kind, goal in [
            ("quote", f"请摘录《{title}》摘要的开篇原句。"),
            ("layout", f"请查找《{title}》摘要在 PDF 的边界框坐标。"),
            ("overview", "在这两篇论文的范围内写一段研究综述，梳理各自的方法、主要结果、差异和仍待解决的问题。"),
        ]:
            yield f"public-{i//2}-{kind}", kind, goal, docs, GENERATION
    for i, topic in enumerate(("calibration", "routing", "forecasting", "segmentation")):
        docs = {}
        for j, method in enumerate(("kernel regression", "spectral filtering")):
            pid = f"controlled-{i}-{j}"
            abstract = f"We use {method} for {topic}. Our results show that {topic} improves on the held-out samples."
            if i == 1 and j == 1:
                abstract = "The paper lists the authors and their affiliations."
            if i == 2 and j == 1:
                abstract = f"We employ {method} for {topic}. Our results show that {topic} declines on the held-out samples."
            docs[pid] = dict(paper_id=pid, title=f"{topic.capitalize()} study {j}", abstract=abstract)
        yield f"control-{i}", "overview", f"Give an overview of the methods and findings for {topic} across these two studies.", docs, "fixture:v5-holdout"
