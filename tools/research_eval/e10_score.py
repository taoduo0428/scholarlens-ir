"""Score blinded, independently signed reviews. Unknown labels remain null."""

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from tools.research_eval.e10_pack import write_new
from tools.research_eval.review_pack import canonical_sha, load
from tools.research_eval.score_reviewed import ranking_metrics

Status = Literal[
    "answerable",
    "partially_answerable",
    "conflicted",
    "not_comparable",
    "insufficient_evidence",
    "source_capability_mismatch",
    "blocked_by_permission",
    "unavailable_in_scope",
]
Grade = Annotated[int, Field(ge=0, le=3)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Judgment(Strict):
    relevant_papers: dict[str, Grade]
    relevant_passages: list[tuple[str, str]]
    required_fields: dict[
        str, str | None
    ]  # gold field -> satisfied system field ID, or null
    gold_answer: str
    expected_claims: dict[
        str, str | None
    ]  # gold proposition -> matching emitted claim ID
    claim_support: dict[str, Literal["supported", "unsupported", "contradicted"]]
    evidence_alignment: dict[str, bool]
    answerability: Status
    contradiction: bool
    comparability: Literal["comparable", "not_comparable", "not_applicable"]
    refusal_correctness: bool | None
    decomposition_correct: bool
    tool_selection_correct: bool
    overall_task_success: bool
    rationale: str = Field(min_length=3)


def signed(sheet, role, pack, run):
    if (
        sheet["role"] != role
        or sheet["version"] != "e10/1"
        or sheet["dataset_hash"] != pack["dataset_hash"]
        or sheet["run_hash"] != canonical_sha(run)
        or sheet["human_confirmed"] is not True
    ):
        raise ValueError("unsigned or different dataset/run")
    reviewer = (sheet.get("reviewer_id") or "").strip().casefold()
    if (
        not reviewer
        or not isinstance(sheet.get("reviewed_at"), str)
        or datetime.fromisoformat(sheet["reviewed_at"]).utcoffset() is None
    ):
        raise ValueError("reviewer identity and timezone required")
    if set(sheet["tasks"]) - run["tasks"].keys():
        raise ValueError("unknown review task")
    return reviewer


def validated(raw, task, pred, docs):
    label = Judgment.model_validate_json(json.dumps(raw))
    if set(label.relevant_papers) != set(task["allowed_papers"]):
        raise ValueError("incomplete paper judgments")
    if set(label.claim_support) != set(pred["claims"]) or set(
        label.evidence_alignment
    ) != set(pred["passages"]):
        raise ValueError("incomplete claim/evidence judgments")
    if any(
        x not in pred["fields"] for x in label.required_fields.values() if x is not None
    ):
        raise ValueError("unknown system field")
    if any(
        label.claim_support.get(x) != "supported"
        for x in label.expected_claims.values()
        if x is not None
    ):
        raise ValueError("gold claim mapped to unsupported output")
    for pid, loc in label.relevant_passages:
        m = re.fullmatch(r"abstract:chars:(\d+)-(\d+)", loc)
        if (
            pid not in task["allowed_papers"]
            or not m
            or not 0 <= int(m[1]) < int(m[2]) <= len(docs[pid])
        ):
            raise ValueError("invalid original source locator")
    return label


def ratio(a, b):
    return a / b if b else None


def score(pack, run, docs, reviews=(), adjudication=None):
    if pack["dataset_hash"] != canonical_sha(
        {k: v for k, v in pack.items() if k != "dataset_hash"}
    ):
        raise ValueError("changed dataset")
    if any(
        canonical_sha(docs[p]) != row["abstract_sha256"]
        for p, row in pack["papers"].items()
    ):
        raise ValueError("source text mismatch")
    tasks = {t["task_id"]: t for t in pack["tasks"]}
    if (
        pack["dataset_hash"] != run["dataset_hash"]
        or tasks.keys() != run["tasks"].keys()
    ):
        raise ValueError("different task list")
    ids = [signed(s, "reviewer", pack, run) for s in reviews]
    if len(ids) not in {0, 2} or len(set(ids)) != len(ids):
        raise ValueError("two independent reviewers required")
    if adjudication and (
        not ids or signed(adjudication, "adjudicator", pack, run) in ids
    ):
        raise ValueError("independent adjudicator required")
    measures = defaultdict(list)
    confusion = Counter()
    agreement = Counter()
    rows = []
    successful = []
    reviewed_cost = []
    adjudicated = 0
    human_metric_names = [
        "precision_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_10",
        "evidence_locator_accuracy",
        "evidence_relevance",
        "claim_support_precision",
        "claim_support_recall",
        "entailment_accuracy",
        "unsupported_claim_rate",
        "contradiction_detection",
        "comparability_accuracy",
        "answerability_accuracy",
        "required_field_coverage",
        "partial_answer_accuracy",
        "false_answer_rate",
        "false_refusal_rate",
        "refusal_correctness",
        "task_success_rate",
        "decomposition_accuracy",
        "tool_selection_accuracy",
    ]
    for tid, t in tasks.items():
        pred = run["tasks"][tid]
        ratings = [
            validated(s["tasks"][tid], t, pred, docs)
            for s in reviews
            if s["tasks"].get(tid) is not None
        ]
        resolution = None
        final = adjudication["tasks"].get(tid) if adjudication else None
        if len(ratings) == 2:
            agreement[(ratings[0].answerability, ratings[1].answerability)] += 1
            if ratings[0].model_dump(exclude={"rationale"}) == ratings[1].model_dump(
                exclude={"rationale"}
            ):
                resolution = ratings[0]
            elif final is not None:
                resolution = validated(final, t, pred, docs)
                adjudicated += 1
        if final is not None and (
            len(ratings) != 2
            or resolution is None
            or ratings[0].model_dump(exclude={"rationale"})
            == ratings[1].model_dump(exclude={"rationale"})
        ):
            raise ValueError("unexpected adjudication")
        vals = {}
        if resolution:
            gold = resolution
            published = bool(pred["claims"])
            expected = gold.answerability in {"answerable", "partially_answerable"}
            predicted = pred["answerability"]
            confusion[(gold.answerability, predicted)] += 1
            supported = list(gold.claim_support.values()).count("supported")
            locators = set(gold.relevant_passages)
            observed = {tuple(v) for v in pred["passages"].values()}
            vals.update(ranking_metrics(pred["ranking"], gold.relevant_papers))
            vals.update(
                evidence_locator_accuracy=ratio(
                    len(observed & locators), len(observed)
                ),
                evidence_relevance=ratio(
                    sum(gold.evidence_alignment.values()), len(gold.evidence_alignment)
                ),
                claim_support_precision=ratio(supported, len(pred["claims"])),
                claim_support_recall=ratio(
                    sum(v is not None for v in gold.expected_claims.values()),
                    len(gold.expected_claims),
                ),
                unsupported_claim_rate=ratio(
                    len(pred["claims"]) - supported, len(pred["claims"])
                ),
                entailment_accuracy=None,  # No independent model entailment classification in this run.
                contradiction_detection=(predicted == "conflicted")
                == gold.contradiction,
                comparability_accuracy=(
                    (predicted == "not_comparable")
                    == (gold.comparability == "not_comparable")
                )
                if gold.comparability != "not_applicable"
                else None,
                answerability_accuracy=predicted == gold.answerability,
                required_field_coverage=ratio(
                    sum(
                        k is not None and pred["fields"][k][1] == "answerable"
                        for k in gold.required_fields.values()
                    ),
                    len(gold.required_fields),
                ),
                partial_answer_accuracy=(
                    predicted == "partially_answerable" and gold.overall_task_success
                )
                if gold.answerability == "partially_answerable"
                else None,
                false_answer_rate=published if not expected else None,
                false_refusal_rate=not published if expected else None,
                refusal_correctness=gold.refusal_correctness,
                task_success_rate=gold.overall_task_success,
                decomposition_accuracy=gold.decomposition_correct,
                tool_selection_accuracy=gold.tool_selection_correct,
            )
            successful.append(pred["tools"] if gold.overall_task_success else None)
            reviewed_cost.append(pred["cost"])
            for k, v in vals.items():
                if v is not None:
                    measures[k].append(v)
        rows.append(
            {
                "task_id": tid,
                "state": "confirmed"
                if resolution
                else "disputed"
                if len(ratings) == 2
                else "pending",
                "metrics": vals,
            }
        )
    metrics = {
        k: mean(measures[k]) if measures[k] else None for k in human_metric_names
    }
    classes = {key for pair in confusion for key in pair}
    metrics["answerability_macro_f1"] = (
        mean(
            2
            * confusion[c, c]
            / sum(n * ((a == c) + (b == c)) for (a, b), n in confusion.items())
            for c in classes
        )
        if classes
        else None
    )
    predictions = list(run["tasks"].values())
    lat = sorted(p["latency_ms"] for p in predictions)
    successes = sum(v is not None for v in successful)
    metrics.update(
        task_completion_rate=mean(
            p["terminal"] in {"completed", "partial"} for p in predictions
        ),
        tool_execution_success=ratio(
            sum(p["tool_success"] for p in predictions),
            sum(p["tool_records"] for p in predictions),
        ),
        recovery_success_rate=ratio(
            sum(p["recovery_successes"] or 0 for p in predictions),
            sum(p["recovery_attempts"] or 0 for p in predictions),
        ),
        p50_ms=median(lat),
        p95_ms=lat[math.ceil(len(lat) * 0.95) - 1],
        tokens=sum(p["tokens"] for p in predictions)
        if all(p["tokens"] is not None for p in predictions)
        else None,
        cost_per_task=mean(p["cost"] for p in predictions)
        if all(p["cost"] is not None for p in predictions)
        else None,
        cost_per_success=ratio(sum(reviewed_cost), successes)
        if all(x is not None for x in reviewed_cost)
        else None,
        tools_per_success=ratio(
            sum(
                run["tasks"][r["task_id"]]["tools"]
                for r in rows
                if r["state"] == "confirmed"
            ),
            successes,
        ),
    )
    pairs = sum(agreement.values())
    return {
        "dataset_hash": pack["dataset_hash"],
        "run_hash": canonical_sha(run),
        "confirmed": len(successful),
        "pending": len(tasks) - len(successful),
        "adjudicated": adjudicated,
        "answerability_interrater_agreement": ratio(
            sum(n for (a, b), n in agreement.items() if a == b), pairs
        ),
        "paired_reviews": pairs,
        "human_metric_denominators": {k: len(measures[k]) for k in human_metric_names},
        "metrics": metrics,
        "rows": rows,
    }


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reviews", type=Path, nargs=2)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_new(
        args.output,
        score(
            load(args.directory / "dataset.json"),
            load(args.directory / "run.local.json"),
            load(args.directory / "reading-material.local.json"),
            [load(p) for p in args.reviews or []],
            load(args.adjudication) if args.adjudication else None,
        ),
    )
