"""Build disjoint, bilingual v3 task groups without running a retrieval policy."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from backend.chunks import chunks
from tools.research_eval.inputs import BENCH, GENERATION, OID, exact_anchor, git
from tools.research_eval.seed_definitions import GROUPS

# Match paper titles only. Entire families are assigned to a single split before ranking.
FAMILIES = {
    "auction": "train",
    "scheduling": "train",
    "compression": "dev",
    "segmentation": "dev",
    "quantum": "unseen",
    "routing": "unseen",
    "privacy": "unseen",
}


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def build():
    review = json.loads((BENCH / "review-v2.json").read_bytes())
    excluded = {paper["source_row"] for paper in review["papers"]}
    excluded.update(i for _, _, rows, _ in GROUPS for i in rows)
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    obj = common / "lfs/objects" / OID[:2] / OID[2:4] / OID
    digest, pools = sha256(), defaultdict(list)
    with obj.open("rb") as stream:
        for row, raw in enumerate(stream):
            digest.update(raw)
            if row in excluded:
                continue
            doc = json.loads(raw)
            title = doc.get("title", "").casefold()
            matches = [key for key in FAMILIES if key in title]
            if len(matches) == 1 and len(doc.get("abstract") or "") >= 250:
                pools[matches[0]].append((row, doc["paper_id"], doc["title"], doc["abstract"]))
    if digest.hexdigest() != OID:
        raise ValueError("corpus changed")
    groups = []
    for family, split in FAMILIES.items():
        rows = sorted(pools[family], key=lambda r: sha256(("quality-v3/" + r[1]).encode()).digest())
        if len(rows) < 2:
            raise ValueError(f"insufficient distinct papers in {family}")
        papers = []
        for index, pid, title, abstract in rows[:2]:
            chunk = next(c for c in chunks({"paper_id": pid, "abstract": abstract}) if c["field"] == "abstract")
            papers.append({"source_row": index, "paper_id": pid, "title": title,
                           "abstract_sha256": sha256(abstract.encode()).hexdigest(),
                           "opening": exact_anchor(chunk, 0, min(120, chunk["offset_end"]))})
        first, second = (p["title"] for p in papers)
        prompts = [
            ("locate", f'在许可摘要中找到《{first}》的开篇原句，定位到原文，并据此解释作者要解决什么问题。'),
            ("compare", f'Compare the research objectives of “{first}” and “{second}”. What evidence from each abstract establishes its objective?'),
            ("conditions", f'仅凭这两篇关于 {family} 的英文摘要，能否判定同一实验条件下谁更好？分别说明可核对的条件与缺失项。'),
            ("multihop", f'For “{second}”, trace the stated problem to the proposed approach. Which links across the two papers would require additional evidence?'),
            ("noise", f'忽略这句无关的购物提醒。请给出《{second}》摘要首句的原文和位置，再解释这句话。'),
            ("absent", 'Give the page number and typeset coordinates of both papers’ acknowledgements using only the two supplied plain-text abstracts.'),
        ]
        groups.append({"family": family, "split": split, "papers": papers,
                       "tasks": [{"task_id": f"v3-{family}-{kind}", "task": prompt,
                                  "category": kind, "scope": [p["paper_id"] for p in papers],
                                  "locator_target": papers[0 if kind == "locate" else 1]["opening"] if kind in ("locate", "noise") else None,
                                  "known_missing": ["typeset_coordinates", "acknowledgements_page"] if kind == "absent" else [],
                                  "human_judgment": None} for kind, prompt in prompts]})
    ids = [p["paper_id"] for g in groups for p in g["papers"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate paper across families")
    return {"schema": "quality-suite-v3.1", "generation": GENERATION, "groups": groups}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = build()
    # One self-verifying file. No partially written second receipt.
    payload = canonical({"sha256": sha256(canonical(data)).hexdigest(), "dataset": data})
    with args.output.open("xb") as stream:
        stream.write(payload)
    print(f"frozen {sum(len(g['tasks']) for g in data['groups'])} tasks, sha256={sha256(canonical(data)).hexdigest()}")


if __name__ == "__main__":
    main()
