"""Build and blind-score the independent review set from a pinned local paper corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path

from backend.chunks import chunks
from tools.research_eval.inputs import (
    BENCH,
    GENERATION,
    LFS_PATH,
    OID,
    SOURCE_REF,
    digest,
    exact_anchor,
    git,
)
from tools.research_eval.score_reviewed import ranking_metrics

PACK = BENCH / "review-v2.json"
# Corpus row IDs only. Authoring uses neither the frozen questions nor their outputs.
TOPICS = (
    (
        717,
        2536,
        "collaborative filtering",
        "neighbour selection",
        "preference prediction",
        "cold-start users",
    ),
    (
        8,
        1204,
        "adaptive routing",
        "battery-powered nodes",
        "application traffic on a Dragonfly interconnect",
        "a congested network",
    ),
    (
        204,
        228,
        "database design",
        "dependency tracking in workflows",
        "write-heavy workloads",
        "a multi-tenant transaction system",
    ),
    (
        25,
        235,
        "data warehouse design",
        "fragmenting XML warehouses",
        "uncertain itemset support",
        "an uncertain XML workload",
    ),
    (
        321,
        414,
        "network communities",
        "evaluation of network partitions",
        "ground-truth communities",
        "a network without labels",
    ),
    (
        823,
        1066,
        "project scheduling",
        "parallel tabu search",
        "activity and time flexibility",
        "a manufacturing line with variable lot sizes",
    ),
    (
        873,
        1249,
        "image segmentation",
        "superpixel region merging",
        "cross-modal alignment",
        "a partially labelled imaging dataset",
    ),
    (
        6,
        270,
        "compression and similarity",
        "edit-distance computation",
        "distances between multisets",
        "a repeated-string workload",
    ),
    (
        187,
        206,
        "data clustering",
        "topologically embedded graphs",
        "changes in web usage",
        "an evolving clickstream",
    ),
    (
        573,
        629,
        "wireless sensor networks",
        "information-theoretic limits",
        "indoor temperature regulation",
        "a network with intermittent sensors",
    ),
    (
        588,
        816,
        "quantum queries",
        "state decomposition",
        "dual polynomials",
        "a new Boolean oracle",
    ),
    (
        259,
        56,
        "graph colouring",
        "differential evolution",
        "network conduciveness",
        "a new class of sparse graphs",
    ),
    (
        961,
        1804,
        "recommendations",
        "video transcripts",
        "repository context",
        "an unseen software repository",
    ),
    (
        465,
        623,
        "community estimation",
        "sparse networks",
        "modularity and likelihood",
        "a graph with unknown community sizes",
    ),
    (
        251,
        273,
        "graph-based clustering",
        "network-constrained trajectories",
        "edge structure over time",
        "a time-varying road network",
    ),
    (
        1723,
        1770,
        "discrete scheduling",
        "railway rescheduling constraints",
        "job-shop policy gradients",
        "an unplanned disruption",
    ),
    (
        366,
        647,
        "supervised classification",
        "time-series features",
        "class potential functions",
        "a dataset with shifted class frequencies",
    ),
)
TASK_TYPES = (
    (
        "fact",
        "For {topic}, what problem does {a} address and which input does it require? Quote the supporting passage and flag any unstated assumption.",
    ),
    (
        "comparison",
        "Prepare a design review comparing {a} with {b}. Give the unit of analysis, data representation and objective for each. Identify which statements are explicit.",
    ),
    (
        "multihop",
        "Trace how the input for {a} affects the proposed method, then relate that dependency to {b}. Cite each link and mark the cross-paper inference.",
    ),
    (
        "metrics",
        "Which quantitative evidence, bound or evaluation measure is actually reported for {b}? Record its value or definition, units, comparator and conditions, leaving missing fields unknown.",
    ),
    (
        "comparability",
        "Can measurements or bounds for {a} and {b} decide what to use for {scenario}? Compare inputs, objectives and evaluation protocols. Give a ranking only if the comparison is supported.",
    ),
    (
        "insufficient",
        "Does the available evidence guarantee deployment performance for {scenario} with a 20% relative gain over its current baseline? Identify the denominator, baseline and external-validity evidence needed to justify the guarantee.",
    ),
)


def canonical_sha(value):
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return digest(raw)


def paper_material(include_text=False):
    selected = {row for group in TOPICS for row in group[:2]}
    if (
        "oid sha256:" + OID
        not in git("cat-file", "blob", SOURCE_REF + ":" + LFS_PATH).splitlines()
    ):
        raise ValueError("pinned LFS pointer changed")
    path = (
        Path(git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        / "lfs/objects"
        / OID[:2]
        / OID[2:4]
        / OID
    )
    file_hash, result = hashlib.sha256(), {}
    with path.open("rb") as handle:
        for row, line in enumerate(handle):
            file_hash.update(line)
            if row not in selected:
                continue
            data = json.loads(line)
            text = data["abstract"].strip()
            if text != data["abstract"] or not text:
                raise ValueError("expected a normalized source abstract")
            material = {"paper_id": data["paper_id"], "abstract": text}
            parts = [part for part in chunks(material) if part["field"] == "abstract"]
            # Navigation hints are exact source ranges and are never relevance labels.
            anchors = []
            for index, part in enumerate((parts[0], parts[-1])):
                start = part["offset_start"]
                end = min(part["offset_end"], start + 200)
                if index:
                    end = part["offset_end"]
                    start = max(start, end - 200)
                anchors.append(exact_anchor(part, start, end))
            result[row] = {
                "paper_id": data["paper_id"],
                "title": data["title"],
                "source_row": row,
                "source_row_sha256": hashlib.sha256(line).hexdigest(),
                "abstract_sha256": digest(text),
                "navigation_anchors": anchors,
            }
            if include_text:
                result[row]["abstract"] = text
    if file_hash.hexdigest() != OID or set(result) != selected:
        raise ValueError("source bytes or selected paper rows changed")
    return result


def build():
    material = paper_material()
    by_id = {d["paper_id"]: d for d in material.values()}
    tasks = []
    for group_index, (left, right, topic, a, b, scenario) in enumerate(TOPICS, 1):
        reference = [material[left]["paper_id"], material[right]["paper_id"]]
        for kind, prompt in TASK_TYPES:
            task_id = f"review-{group_index:02d}-{kind}"
            others = sorted(
                set(by_id) - set(reference), key=lambda pid: digest(task_id + pid)
            )
            scope = sorted(
                reference + others[:6], key=lambda pid: digest(pid + task_id)
            )
            tasks.append(
                {
                    "task_id": task_id,
                    "category": kind,
                    "task": prompt.format(topic=topic, a=a, b=b, scenario=scenario),
                    "scope": {"paper_ids": scope, "fields": ["abstract"]},
                    "annotation_status": "pending_human_review",
                    "human_qrels": None,
                    "human_claim_judgments": None,
                }
            )
    return {
        "schema": "scholarlens-review-v2",
        "source_commit": SOURCE_REF,
        "source_path": LFS_PATH,
        "corpus_generation": GENERATION,
        "papers": list(by_id.values()),
        "tasks": tasks,
        "annotation_template": {
            "relevance_scale": [0, 1, 2, 3],
            "claim_labels": ["supported", "contradicted", "insufficient"],
            "human_signoff": None,
        },
    }


def load(path):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=unique)


def rows_by_key(rows, key):
    if not isinstance(rows, list):
        raise TypeError("expected a list of rows")
    result = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get(key), str)
            or not row[key].strip()
            or row[key] in result
        ):
            raise ValueError("missing or duplicate " + key)
        result[row[key]] = row
    return result


def validate_run(pack, run):
    if run.get("pack_sha256") != canonical_sha(pack):
        raise ValueError("run targets a different review pack")
    tasks = rows_by_key(pack["tasks"], "task_id")
    entries = rows_by_key(run.get("tasks"), "task_id")
    if not entries or set(entries) - set(tasks):
        raise ValueError("run contains no tasks or an unknown task")
    for tid, item in entries.items():
        scope = set(tasks[tid]["scope"]["paper_ids"])
        ranking = item["ranking"]
        if (
            not isinstance(ranking, list)
            or len(set(ranking)) != len(ranking)
            or set(ranking) - scope
        ):
            raise ValueError("ranking must contain unique in-scope paper IDs")
        for claim in rows_by_key(item.get("claims"), "claim_id").values():
            if not isinstance(claim.get("text"), str) or not claim["text"].strip():
                raise ValueError("claim text required")
            citations = claim.get("cited_paper_ids", [])
            if not isinstance(citations, list) or set(citations) - scope:
                raise ValueError("claim citations must be in the task scope")
    return tasks, entries


def template(pack, run):
    tasks, entries = validate_run(pack, run)
    return {
        "pack_sha256": canonical_sha(pack),
        "run_sha256": canonical_sha(run),
        "reviewer_id": None,
        "signed_at": None,
        "human_attestation": False,
        "tasks": [
            {
                "task_id": tid,
                "task": tasks[tid]["task"],
                "qrels": dict.fromkeys(tasks[tid]["scope"]["paper_ids"]),
                "claims": {
                    claim["claim_id"]: {
                        "text": claim["text"],
                        "cited_paper_ids": claim.get("cited_paper_ids", []),
                        "judgment": None,
                        "reason": "",
                    }
                    for claim in item["claims"]
                },
            }
            for tid, item in entries.items()
        ],
    }


def checked_reviews(pack, run, reviews, allow_single):
    tasks, entries = validate_run(pack, run)
    if not reviews:
        return entries, [], "awaiting_human_review"
    if len(reviews) not in (1, 2):
        raise ValueError("supply one or two independent reviews")
    reviewers, sheets = set(), []
    for review in reviews:
        if review.get("pack_sha256") != canonical_sha(pack) or review.get(
            "run_sha256"
        ) != canonical_sha(run):
            raise ValueError("review binds to different source or system outputs")
        reviewer = review.get("reviewer_id")
        if (
            not isinstance(reviewer, str)
            or not reviewer.strip()
            or reviewer.strip().casefold() in reviewers
        ):
            raise ValueError("a distinct human reviewer ID is required for each sheet")
        if review.get("human_attestation") is not True:
            raise ValueError("human signoff required")
        try:
            instant = datetime.fromisoformat(review["signed_at"])
            if instant.tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "signed_at requires an ISO timestamp with timezone"
            ) from exc
        reviewers.add(reviewer.strip().casefold())
        sheet = rows_by_key(review["tasks"], "task_id")
        if set(sheet) - set(entries):
            raise ValueError("unexpected reviewed task")
        for tid, row in sheet.items():
            if row.get("task") != tasks[tid]["task"]:
                raise ValueError("review question differs from the bound task")
            qrels, claims = row["qrels"], row["claims"]
            if not isinstance(qrels, dict) or qrels.keys() - set(
                tasks[tid]["scope"]["paper_ids"]
            ):
                raise ValueError("unknown qrel paper ID")
            if any(
                v is not None and (type(v) is not int or v not in range(4))
                for v in qrels.values()
            ):
                raise ValueError("human relevance must range from 0 to 3")
            allowed = rows_by_key(entries[tid]["claims"], "claim_id")
            if not isinstance(claims, dict) or claims.keys() - allowed.keys():
                raise ValueError("unknown claim ID")
            for cid, judgment in claims.items():
                if (
                    not isinstance(judgment, dict)
                    or judgment.get("text") != allowed[cid]["text"]
                    or judgment.get("cited_paper_ids")
                    != allowed[cid].get("cited_paper_ids", [])
                ):
                    raise ValueError("judgment text must match the run")
                if judgment.get("judgment") is None:
                    continue
                if (
                    judgment["judgment"]
                    not in ("supported", "contradicted", "insufficient")
                    or not isinstance(judgment.get("reason"), str)
                    or not judgment["reason"].strip()
                ):
                    raise ValueError(
                        "each human claim judgment requires an allowed label and reason"
                    )
        sheets.append(sheet)
    if len(sheets) == 1 and not allow_single:
        return entries, [], "second_reviewer_required"
    return (
        entries,
        sheets,
        "explicit_single_reviewer" if len(sheets) == 1 else "two_reviewers",
    )


def score(pack, run, reviews=(), allow_single=False):
    entries, sheets, state = checked_reviews(pack, run, reviews, allow_single)
    tasks = rows_by_key(pack["tasks"], "task_id")
    rows = []
    for tid, entry in entries.items():
        row = {
            "task_id": tid,
            "precision_at_5": None,
            "recall_at_10": None,
            "ndcg_at_10": None,
            "mrr": None,
            "human_supported_claims": None,
            "emitted_claims": len(entry["claims"]),
            "qrels_state": "pending",
            "claims_state": "pending",
        }
        submitted = [sheet[tid] for sheet in sheets if tid in sheet]
        scope = set(tasks[tid]["scope"]["paper_ids"])
        if sheets and len(submitted) == len(sheets):
            qrels = [item["qrels"] for item in submitted]
            if all(
                set(labels) == scope and None not in labels.values() for labels in qrels
            ):
                if all(labels == qrels[0] for labels in qrels):
                    row["qrels_state"] = "complete"
                    row.update(ranking_metrics(entry["ranking"], qrels[0]))
                else:
                    row["qrels_state"] = "disagreement"
            claim_ids = {c["claim_id"] for c in entry["claims"]}
            grades = [
                {k: v.get("judgment") for k, v in item["claims"].items()}
                for item in submitted
            ]
            if all(
                set(labels) == claim_ids and None not in labels.values()
                for labels in grades
            ):
                if all(labels == grades[0] for labels in grades):
                    row["claims_state"] = "complete"
                    row["human_supported_claims"] = sum(
                        v == "supported" for v in grades[0].values()
                    )
                else:
                    row["claims_state"] = "disagreement"
        rows.append(row)
    metrics = {}
    for key in ("precision_at_5", "recall_at_10", "ndcg_at_10", "mrr"):
        metrics[key] = (
            statistics.mean(row[key] for row in rows)
            if all(row[key] is not None for row in rows)
            else None
        )
    claim_count = sum(r["emitted_claims"] for r in rows)
    metrics["human_claim_support_rate"] = (
        sum(r["human_supported_claims"] for r in rows) / claim_count
        if claim_count and all(r["human_supported_claims"] is not None for r in rows)
        else None
    )
    return {
        "schema": "scholarlens-human-scores-v2",
        "pack_sha256": canonical_sha(pack),
        "run_sha256": canonical_sha(run),
        "review_mode": state,
        "reviewed_run_tasks": len(rows),
        "total_pack_tasks": len(tasks),
        "metrics": metrics,
        "tasks": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="cmd", required=True)
    cmds.add_parser("build")
    cmds.add_parser("verify")
    materials = cmds.add_parser("materials")
    materials.add_argument("--task", required=True)
    for name in ("template", "score"):
        sub = cmds.add_parser(name)
        sub.add_argument("--run", type=Path, required=True)
        if name == "score":
            sub.add_argument("--review", type=Path, action="append", default=[])
            sub.add_argument("--allow-single-reviewer", action="store_true")
    parser.add_argument("--out", type=Path, help="new output file, otherwise stdout")
    args = parser.parse_args()
    if args.cmd == "build":
        result = build()
    elif args.cmd == "verify":
        generated, saved = build(), load(PACK)
        if saved != generated:
            raise SystemExit("saved pack differs from pinned source regeneration")
        result = {
            "pack_sha256": canonical_sha(saved),
            "tasks": len(saved["tasks"]),
            "papers": len(saved["papers"]),
            "human_labels": 0,
        }
    elif args.cmd == "materials":
        pack = load(PACK)
        task = rows_by_key(pack["tasks"], "task_id").get(args.task)
        if not task:
            raise SystemExit("unknown review task")
        papers = {d["paper_id"]: d for d in paper_material(include_text=True).values()}
        result = {
            "task_id": task["task_id"],
            "question": task["task"],
            "papers": [papers[pid] for pid in task["scope"]["paper_ids"]],
        }
    else:
        pack, run = load(PACK), load(args.run)
        result = (
            template(pack, run)
            if args.cmd == "template"
            else score(
                pack, run, [load(f) for f in args.review], args.allow_single_reviewer
            )
        )
    if args.out:
        with args.out.open("x", encoding="utf8", newline="\n") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
