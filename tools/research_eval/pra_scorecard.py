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


def matches_recorded_digest(raw, digest):
    # Historical artifacts were stamped from both Windows and POSIX checkouts.
    lf = raw.replace(b"\r\n", b"\n")
    return any(sha256(data).hexdigest() == digest for data in (raw, lf, lf.replace(b"\n", b"\r\n")))


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


def paired_hits(baseline, candidate):
    """List changed cases even when wins and losses cancel in aggregate."""
    return {
        "gained": sorted(candidate - baseline),
        "lost": sorted(baseline - candidate),
        "retained": len(baseline & candidate),
    }


def paired_requirements(baseline, candidate):
    before = keyed(baseline["rows"], "id")
    after = keyed(candidate["rows"], "id")
    if before.keys() != after.keys():
        raise ValueError("Unpaired original requirement review")
    changes = []
    for task, row in sorted(before.items()):
        for ordinal, (old, new) in enumerate(zip(
            row["requirements"], after[task]["requirements"], strict=True
        ), 1):
            if old["requirement"] != new["requirement"]:
                raise ValueError(f"Original requirement changed for {task} field {ordinal}")
            if old["assessment"] != new["assessment"]:
                changes.append({"task": task, "ordinal": ordinal, "requirement": old["requirement"],
                                "A": old["assessment"], "G": new["assessment"],
                                "A_claims": old["claims"], "G_claims": new["claims"]})
    return changes


def build(root, reruns=None):
    review = read(root / "silver-field-review.json")
    ablation = read(root / "ablation-final/metrics.json")
    scores, cohort, silver_rows = {}, None, {}
    for arm in ("A", "G"):
        raw = (root / "ablation-final" / f"{arm}.jsonl").read_bytes()
        metrics = ablation[arm]
        if not matches_recorded_digest(raw, metrics["case_file_sha256"]):
            raise ValueError(f"Ablation checksum mismatch for {arm}")
        rows = keyed([json.loads(line) for line in raw.splitlines()], "task")
        signature = {k: (r["expected"], r["required_silver_fields"]) for k, r in rows.items()}
        if len(rows) != 111 or (cohort is not None and signature != cohort):
            raise ValueError("Unpaired Silver cohort")
        cohort = signature
        silver_rows[arm] = rows
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

    holdout_rows = read(root / "fulltext-transfer-results.json")
    seals = {row["manifest_sha256"] for row in holdout_rows}
    if len(seals) != 1:
        raise ValueError("Inconsistent holdout manifest digests")
    seal = next(iter(seals))
    if not matches_recorded_digest((root / "holdout.json").read_bytes(), seal):
        raise ValueError("Holdout manifest checksum mismatch")
    matched = holdout(holdout_rows, seal)
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
    rerun_negative_changes = {}
    for i, rows in enumerate(rerun_batches, 1):
        row_keys = {(r["paper"], r["question"], r["unanswerable"]) for r in rows}
        expected = {(r["paper"], r["question"], r["unanswerable"]) for r in batches[i-1]["cases"]}
        if row_keys != expected:
            raise ValueError(f"QASPER rerun {i} differs from its blind cohort")
        external[f"same_cases_rerun_{i}"] = qasper_cases(rows)
        negatives_before = {r["question"] for r in batches[i-1]["cases"]
                            if r["unanswerable"] and r["A"]["direct"]}
        negatives_after = {r["question"] for r in rows if r["unanswerable"] and r["direct"]}
        rerun_negative_changes[f"batch_{i}"] = paired_hits(negatives_before, negatives_after)
    acceptance = read(root / "qasper-acceptance.json")
    if acceptance["source_sha256"] != public["archive_sha256"]:
        raise ValueError("QASPER source version mismatch")
    def identity(row):
        return row["paper"], row["question"], row["unanswerable"]
    acceptance_cases = [identity(r) for r in acceptance["manifest"]]
    prior_papers = {r["paper"] for batch in batches for r in batch["cases"]}
    prior_papers.update(acceptance["excluded_papers"])
    if prior_papers.intersection(pid for pid, _, _ in acceptance_cases):
        raise ValueError("QASPER acceptance papers overlap historical cohorts")
    external["independent_acceptance"] = {}
    for arm in ("A", "G"):
        rows = acceptance["results"][arm]
        if [identity(row) for row in rows] != acceptance_cases:
            raise ValueError("Unpaired QASPER acceptance")
        external["independent_acceptance"][arm] = qasper_cases(rows)
    def published(arm, expected_positive):
        return {key for key, row in silver_rows[arm].items()
                if (row["expected"] in POSITIVE) == expected_positive and row["direct_claims"]}

    def external_hits(arm, negative):
        return {row["question"] for row in acceptance["results"][arm]
                if row["unanswerable"] == negative
                and (row["direct"] if negative else row["all_spans_with_reference"])}

    def holdout_hits(arm, field):
        return {r["case"] for r in holdout_rows if r["arm"] == arm and r[field] is True}

    paired = {
        "holdout_full_group_synthesis": paired_hits(holdout_hits("A", "linked_overview"),
                                                    holdout_hits("G", "linked_overview")),
        "qasper_rerun_negative_direct": rerun_negative_changes,
        "silver_any_direct": paired_hits(published("A", True), published("G", True)),
        "silver_negative_direct": paired_hits(published("A", False), published("G", False)),
        "silver_original_requirements_changed": paired_requirements(review["A"], review["G"]),
        "fresh_qasper_reference_hits": paired_hits(external_hits("A", False), external_hits("G", False)),
        "fresh_qasper_negative_direct": paired_hits(external_hits("A", True), external_hits("G", True)),
    }
    failures = []
    if matched["G"]["full_group_synthesis"]["count"] <= matched["A"]["full_group_synthesis"]["count"]:
        failures.append("no_full_group_holdout_gain")
    if matched["G"]["source_failures"] or matched["G"]["unsupported_layout"]["count"]:
        failures.append("holdout_source_or_layout_failure")
    if paired["silver_negative_direct"]["gained"]:
        failures.append("silver_negative_regression")
    if (paired["fresh_qasper_negative_direct"]["gained"]
            or any(row["gained"] for row in rerun_negative_changes.values())):
        failures.append("qasper_negative_regression")
    return {
        "schema": "pra-scorecard/1",
        "silver_single_ai_review": scores,
        "independent_fulltext_holdout": matched,
        "qasper_human_reference": external,
        "paired_changes": paired,
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
