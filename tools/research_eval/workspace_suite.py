"""Freeze grouped public tasks before iterating on workspace policy. No model or network."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from tools.research_eval.freeze_quality import canonical
from tools.research_eval.inputs import BENCH, GENERATION, OID, git, read_jsonl

TOPICS = {"train": ("wavelet", "ontology"), "dev": ("fluid", "translation"), "independent": ("thermal", "automata")}
CASES = ("direct", "comparison", "multihop", "alignment", "controversy", "absent", "distractor")


def hash_text(text):
    return sha256(text.encode()).hexdigest()


def corpus_file():
    base = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    return base / "lfs/objects" / OID[:2] / OID[2:4] / OID


def excluded():
    previous = json.loads((BENCH / "quality-v3-frozen.json").read_bytes())["dataset"]["groups"]
    used = {p["paper_id"] for g in previous for p in g["papers"]}
    used.update(p["paper_id"] for p in json.loads((BENCH / "review-v2.json").read_bytes())["papers"])
    used.update(pid for t in read_jsonl(BENCH / "seed-v1.jsonl") for pid in t["scope"]["paper_ids"])
    return used


def freeze():
    pools = {topic: [] for split in TOPICS.values() for topic in split}
    old = excluded()
    digest = sha256()
    with corpus_file().open("rb") as stream:
        for idx, line in enumerate(stream):
            digest.update(line)
            doc = json.loads(line)
            pid, title, abstract = doc["paper_id"], doc["title"], doc.get("abstract") or ""
            topics = [topic for topic in pools if topic in title.casefold()]
            if len(topics) == 1 and pid not in old and len(abstract) > 180:
                pools[topics[0]].append((hash_text("workspace/1:" + pid), {
                    "paper_id": pid, "title": title, "row": idx, "abstract_sha": hash_text(abstract)}))
    if digest.hexdigest() != OID:
        raise ValueError("public source digest changed")
    groups = []
    for split, topics in TOPICS.items():
        for topic in topics:
            pair = [r for _, r in sorted(pools[topic])[:2]]
            if len(pair) != 2:
                raise ValueError(f"topic {topic} has {len(pair)} eligible papers")
            a, b = [p["title"] for p in pair]
            prompts = [f'Quote the first complete sentence of the abstract of "{a}".',
                       f'Compare the approaches to {topic} in "{a}" and "{b}".',
                       f'Trace the causal mechanism linking the approach and outcome in "{b}".',
                       f'Compare the measured results under matching datasets, units, setup and protocol for {topic}.',
                       f'Do the conclusions about {topic} contradict each other under the same conditions?',
                       f'What is the physical shelf location of the printed copy of "{b}"?',
                       f'Given "{a}", give the institutional archive accession number of its signed original.']
            groups.append({"split": split, "topic": topic, "papers": pair, "tasks": [
                {"id": topic+"-"+kind, "kind": kind, "goal": goal,
                 "scope": [pair[0]["paper_id"]] if kind in {"direct","distractor"} else [p["paper_id"] for p in pair]}
                for kind,goal in zip(CASES,prompts,strict=True)]})
    return {"schema":"workspace-suite/1","generation":GENERATION,"groups":groups}


def suite_groups(split):
    path = BENCH / "workspace-v4-frozen.json"
    data = json.loads(path.read_bytes())
    if data["sha256"] != "7f5014b844aa57e308ea3fc0b439a0368dfc5dfa609ce79c1a3a0ac95435ae63" or sha256(canonical(data["dataset"])).hexdigest() != data["sha256"]:
        raise ValueError("invalid suite digest")
    groups = [g for g in data["dataset"]["groups"] if g["split"] == split]
    return groups, data["sha256"]


def load_split(split):
    groups, stamp = suite_groups(split)
    wanted = {p["row"]:p for g in groups for p in g["papers"]}
    docs = {}
    digest = sha256()
    with corpus_file().open("rb") as stream:
        for idx,line in enumerate(stream):
            digest.update(line)
            if idx in wanted:
                row = json.loads(line)
                if hash_text(row["abstract"]) != wanted[idx]["abstract_sha"] or row["paper_id"] != wanted[idx]["paper_id"]:
                    raise ValueError("paper mismatch")
                docs[row["paper_id"]] = {k:row[k] for k in ("paper_id","title","abstract")}
    if digest.hexdigest() != OID or len(docs) != len(wanted):
        raise ValueError("source mismatch")
    return [t for g in groups for t in g["tasks"]], docs, stamp


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    dataset = freeze()
    stamp = sha256(canonical(dataset)).hexdigest()
    with args.output.open("xb") as stream:
        stream.write(canonical({"sha256":stamp,"dataset":dataset}))
    print(stamp, len(dataset["groups"]), "groups")
