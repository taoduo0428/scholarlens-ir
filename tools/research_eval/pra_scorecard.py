"""Rebuild the PRA acceptance scorecard from versioned, paired evaluation artifacts."""

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from tools.research_eval.pra_baseline import POSITIVE
from tools.research_eval.v7_summary import latency, proportion


def read(path):
    return json.loads(path.read_bytes())


def keyed(rows, field):
    indexed = {row[field]: row for row in rows}
    if len(indexed) != len(rows) or not indexed:
        raise ValueError(f"Empty set or duplicate {field}")
    return indexed


def rate(count, total):
    return proportion(count, total) if total else None


def silver(rows, review):
    positive = {key: row for key, row in rows.items() if row["expected"] in POSITIVE}
    negative = [row for key, row in rows.items() if key not in positive]
    reviewed = keyed(review["rows"], "id")
    if reviewed.keys() != positive.keys():
        raise ValueError("Original requirement review differs from the positive set")
    fields = Counter()
    completed = partial = 0
    for key, row in reviewed.items():
        actual = positive[key]
        requirements = row["requirements"]
        if not requirements or len(requirements) != actual["required_silver_fields"]:
            raise ValueError(f"Invalid original requirements for {key}")
        verdicts = [field["assessment"] for field in requirements]
        for field in requirements:
            if (field["assessment"] not in {"full", "partial", "absent"}
                    or not set(field["claims"]) <= set(actual["claim_ids"])
                    or bool(field["claims"]) != (field["assessment"] != "absent")):
                raise ValueError(f"Invalid review evidence for {key}")
        fields.update(verdicts)
        completed += all(v == "full" for v in verdicts)
        partial += any(v != "absent" for v in verdicts) and not all(v == "full" for v in verdicts)
    total_fields = fields.total()
    direct = sum(bool(row["direct_claims"]) for row in positive.values())
    return {
        "any_direct": rate(direct, len(positive)),
        "no_direct_on_answerable": rate(len(positive) - direct, len(positive)),
        "full_original_task": rate(completed, len(positive)),
        "partial_original_task": rate(partial, len(positive)),
        "full_original_field": rate(fields["full"], total_fields),
        "partial_original_field": rate(fields["partial"], total_fields),
        "published_system_field": rate(sum(r["published_fields"] for r in positive.values()),
                                       sum(r["system_fields"] for r in positive.values())),
        "negative_direct": rate(sum(bool(r["direct_claims"]) for r in negative), len(negative)),
        "tool_calls": sum(r["tools"] for r in rows.values()),
        "model_calls": sum(r["model_calls"] for r in rows.values()),
        **latency([r["elapsed_ms"] for r in rows.values()]),
    }


def holdout(rows, seal):
    arms = {arm: keyed([r for r in rows if r["arm"] == arm], "case") for arm in ("A", "G")}
    if (arms["A"].keys() != arms["G"].keys() or any(r["manifest_sha256"] != seal for r in rows)
            or any(arms["A"][k]["kind"] != arms["G"][k]["kind"] for k in arms["A"])):
        raise ValueError("Unpaired or unsealed holdout")
    results = {}
    for arm, cases in arms.items():
        tasks = [r for r in cases.values() if r["kind"] == "overview"]
        negatives = [r for r in cases.values() if r["kind"] == "layout"]
        if len(tasks) != 12 or len(negatives) != 12 or len(cases) != 24:
            raise ValueError("Incomplete frozen holdout")
        results[arm] = {
            "full_group_synthesis": rate(sum(r["linked_overview"] is True for r in tasks), len(tasks)),
            "unsupported_layout": rate(sum(r["false_release"] is True for r in negatives), len(negatives)),
            "source_failures": sum(len(r["invalid_source_claims"]) + r["scope_errors"] for r in cases.values()),
        }
    return results


def qasper_cases(rows):
    keyed(rows, "question")
    positive = [r for r in rows if not r["unanswerable"]]
    negative = [r for r in rows if r["unanswerable"]]
    if (len(positive), len(negative)) != (24, 8):
        raise ValueError("Incomplete QASPER batch")
    extracts = [r for r in positive if r["has_extractive_reference"]]
    visible = [r for r in extracts if r.get("all_spans_in_retained_reference_sentences") is not None]
    return {
        "any_direct": rate(sum(bool(r["direct"]) for r in positive), len(positive)),
        "all_reference_spans": rate(sum(r["all_spans_with_reference"] for r in extracts), len(extracts)),
        "annotated_passage_read": rate(sum(r["reference_passage_read"] for r in positive), len(positive)),
        "all_reference_sentences_read": rate(
            sum(r["all_spans_in_retained_reference_sentences"] for r in visible), len(visible)
        ) if len(visible) == len(extracts) else None,
        "negative_direct": rate(sum(bool(r["direct"]) for r in negative), len(negative)),
        "tool_calls": sum(r["tools"] for r in rows),
    }


def build(root, reruns=None):
    review = read(root / "silver-field-review.json")
    ablation = read(root / "ablation-final/metrics.json")
    scores, cohort = {}, None
    for arm in ("A", "G"):
        raw = (root / "ablation-final" / f"{arm}.jsonl").read_bytes()
        metrics = ablation[arm]
        if sha256(raw).hexdigest() != metrics["case_file_sha256"]:
            raise ValueError(f"Ablation checksum mismatch for {arm}")
        rows = keyed([json.loads(line) for line in raw.splitlines()], "task")
        signature = {k: (r["expected"], r["required_silver_fields"]) for k, r in rows.items()}
        if len(rows) != 111 or (cohort is not None and signature != cohort):
            raise ValueError("Unpaired Silver cohort")
        cohort = signature
        scores[arm] = silver(rows, review[arm])
        verification = metrics["independent_source_verification"]
        count = verification["reviewed_claims"]
        if count != sum(r["direct_claims"] for r in rows.values()):
            raise ValueError(f"Unpaired source audit for {arm}")
        scores[arm]["source_integrity"] = rate(count - verification["removed_claims"], count)
        scores[arm]["cost_per_full_task_usd"] = None
        scores[arm]["input_tokens"] = metrics["input_tokens"]
        scores[arm]["output_tokens"] = metrics["output_tokens"]
        scores[arm]["cost_per_task_usd"] = metrics["model_cost_usd"] / len(rows)
        scores[arm]["missing_field_reasons"] = metrics["loss_on_unanswered_positives"]
        scores[arm]["case_sha256"] = metrics["case_file_sha256"]

    seal = sha256((root / "holdout.json").read_bytes()).hexdigest()
    matched = holdout(read(root / "fulltext-transfer-results.json"), seal)
    public = read(root / "qasper-human-results.json")
    external = {}
    batches = (public, public["fresh_second_batch"])
    for i, batch in enumerate(batches, 1):
        cases = batch["cases"]
        arms = ("A", "G_blind") if i == 1 else ("A", "G")
        external[f"blind_batch_{i}"] = {
            arm: qasper_cases([{**r[arm], "question": r["question"], "unanswerable": r["unanswerable"]}
                               for r in cases]) for arm in arms
        }
    rerun_batches = [read(path) for path in reruns] if reruns else read(root / "qasper-same-case-reruns.json")
    if len(rerun_batches) != len(batches):
        raise ValueError("Missing QASPER rerun batch")
    for i, rows in enumerate(rerun_batches, 1):
        row_keys = {(r["paper"], r["question"], r["unanswerable"]) for r in rows}
        expected = {(r["paper"], r["question"], r["unanswerable"]) for r in batches[i-1]["cases"]}
        if row_keys != expected:
            raise ValueError(f"QASPER rerun {i} differs from its blind cohort")
        external[f"same_cases_rerun_{i}"] = qasper_cases(rows)
    failures = []
    if matched["G"]["full_group_synthesis"]["count"] <= matched["A"]["full_group_synthesis"]["count"]:
        failures.append("no_full_group_holdout_gain")
    if matched["G"]["source_failures"] or matched["G"]["unsupported_layout"]["count"]:
        failures.append("holdout_source_or_layout_failure")
    if scores["G"]["negative_direct"]["count"] > scores["A"]["negative_direct"]["count"]:
        failures.append("silver_negative_regression")
    if any(external[f"same_cases_rerun_{i}"]["negative_direct"]["count"] >
           external[f"blind_batch_{i}"]["A"]["negative_direct"]["count"]
           for i in range(1, len(batches) + 1)):
        failures.append("qasper_negative_regression")
    return {
        "schema": "pra-scorecard/1",
        "silver_single_ai_review": scores,
        "independent_fulltext_holdout": matched,
        "qasper_human_reference": external,
        "holdout_manifest_sha256": seal,
        "qasper_archive_sha256": public["archive_sha256"],
        "unmeasured": ["claim_entailment_precision", "question_decomposition_accuracy",
                       "evidence_extraction_accuracy", "relation_identification_accuracy",
                       "profile_semantic_completeness", "tool_selection_accuracy",
                       "representative_recovery_rate", "real_provider_usage_latency_cost"],
        "default_policy_gate": {"status": "keep_current" if failures else "review_required",
                                "reasons": failures},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=Path("docs/agent-v8"))
    parser.add_argument("--qasper-reruns", type=Path, nargs=2, default=())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.records, args.qasper_reruns)
    with args.out.open("x", encoding="utf-8") as target:
        json.dump(report, target, indent=2)
        target.write("\n")


if __name__ == "__main__":
    main()
