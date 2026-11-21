"""Verify the public E10 Silver adjudication, optionally against its private inputs."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

PREDICTION_KEYS = {
    "supported_claims",
    "unsupported_claims",
    "refusal_correctness",
    "failure_category",
    "prediction_assessment",
}
ROOT = Path(__file__).resolve().parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
    ]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_span(papers: dict, scope: list, evidence: dict, expected: str) -> None:
    pid, start, end = (evidence[key] for key in ("paper_id", "start", "end"))
    require(pid in scope, "Evidence outside task scope")
    abstract = papers[pid]
    require(0 <= start < end <= len(abstract), "Invalid source offsets")
    require(
        digest(abstract[start:end].encode()) == expected, "Source slice hash mismatch"
    )


def verify_private(root: Path, manifest: dict, labels: list[dict]) -> dict:
    blind_dir = root / "output/v6"
    historical = root / "output/v5/accepted-e10"
    for name, entry in manifest["inputs"].items():
        path = (
            historical
            if name in {"run.local.json", "dataset.json", "reading-material.local.json"}
            else blind_dir
        ) / name
        require(
            digest(path.read_bytes()) == entry["sha256"],
            f"Private input changed: {name}",
        )
    blind = load_json(blind_dir / "blind-source.json")
    papers = load_json(historical / "reading-material.local.json")
    require(
        papers == {k: v["abstract"] for k, v in blind["papers"].items()},
        "Blind source differs from original abstracts",
    )
    original = load_json(historical / "dataset.json")
    run = load_json(historical / "run.local.json")
    require(
        run["dataset_hash"] == original["dataset_hash"], "Run and dataset hashes differ"
    )
    prior = {t["task_id"]: t for t in original["tasks"]}
    raw_reviews = [rows(blind_dir / f"reviewer-{name}.jsonl") for name in ("a", "b")]
    require(
        all(len(batch) == len(labels) for batch in raw_reviews),
        "Incomplete blind review",
    )
    counts = Counter()
    for i, (label, question) in enumerate(zip(labels, blind["tasks"], strict=True)):
        tid = label["task_id"]
        scope = label["requested_paper_scope"]
        require(
            tid == question["id"]
            and question["question"] == prior[tid]["research_goal"],
            f"Question mismatch: {tid}",
        )
        require(
            scope == question["scope"] == prior[tid]["allowed_papers"],
            f"Paper scope mismatch: {tid}",
        )
        for batch in raw_reviews:
            require(batch[i]["task_id"] == tid, "Blind review IDs differ")
            for e in batch[i]["evidence"]:
                verify_span(papers, scope, e, e["quote_hash"])
                counts["blind_review_spans"] += 1
        for e in label["relevant_evidence"]:
            verify_span(papers, scope, e, e["quote_hash"])
            counts["silver_spans"] += 1
        prediction = label["prediction_assessment"]
        raw = run["tasks"][tid]
        require(
            prediction["answerability"] == raw["answerability"], "Prediction differs"
        )
        require(
            {f["field_id"]: [f["request"], f["status"]] for f in prediction["fields"]}
            == raw["fields"]
            and {f["field_id"]: f["reason"] for f in prediction["fields"]}
            == raw["field_reasons"],
            f"Field records differ: {tid}",
        )
        require(
            len(prediction["retrieved_sources"]) == len(raw["passages"]),
            "Passage count differs",
        )
        for e in prediction["retrieved_sources"]:
            verify_span(papers, scope, e, e["quote_hash"])
            locator = f"abstract:chars:{e['start']}-{e['end']}"
            require(
                raw["passages"][e["evidence_id"]] == [e["paper_id"], locator],
                "Retrieved locator differs",
            )
            counts["retrieved_spans"] += 1
        reviewed_claims = label["supported_claims"] + label["unsupported_claims"]
        require(
            {c["claim_id"] for c in reviewed_claims}
            == set(raw["entailment_candidates"]),
            "Candidate set differs",
        )
        require(
            len(raw["claims"]) == prediction["direct_verified_claim_count"],
            "Direct claim count differs",
        )
        for claim in reviewed_claims:
            candidate = raw["entailment_candidates"][claim["claim_id"]]
            verify_span(papers, scope, claim["source_locator"], claim["quote_hash"])
            require(
                digest(candidate["statement"].encode()) == claim["quote_hash"],
                "Candidate text does not match its source",
            )
            require(
                candidate["evidence"] == claim["evidence_ids"],
                "Candidate attribution changed",
            )
            counts["candidate_spans"] += 1
    return dict(counts)


def verify(root: Path, public_only: bool = False) -> dict:
    """Read the retained release and return checked counts, raising on a mismatch."""
    public = root / "docs/agent-v6/e10"
    manifest = load_json(public / "review-manifest.json")
    for name, expected in manifest["outputs"].items():
        data = (public / name).read_bytes().replace(b"\r\n", b"\n")
        require(digest(data) == expected, f"Public output changed: {name}")
    labels = rows(public / "silver-labels.jsonl")
    comparison = load_json(public / "disagreements.json")["rows"]
    decisions = load_json(public / "adjudication.json")
    ids = [r["task_id"] for r in labels]
    require(len(set(ids)) == len(labels) == 111, "Expected 111 unique labels")
    require(
        ids
        == [r["task_id"] for r in comparison]
        == [r["task_id"] for r in decisions["rows"]],
        "Adjudication IDs differ",
    )
    require(
        manifest["counts"] == decisions["counts"], "Counts differ across public reports"
    )
    stats = manifest["counts"]
    source = [
        {k: v for k, v in row.items() if k not in PREDICTION_KEYS} for row in labels
    ]
    frozen = b"".join(
        (
            json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
        for r in source
    )
    require(
        digest(frozen) == manifest["source_phase_sha256"],
        "Independent source labels changed",
    )
    require(
        dict(Counter(r["answerability"] for r in labels))
        == stats["adjudicated_answerability"],
        "Source status counts differ",
    )
    require(
        dict(Counter(r["refusal_correctness"] for r in labels))
        == stats["refusal_assessment"],
        "Refusal counts differ",
    )
    require(
        sum(
            r["reviewer_a"]["answerability"] == r["reviewer_b"]["answerability"]
            for r in comparison
        )
        == stats["ab_answerability_agreement"],
        "A/B agreement differs",
    )
    for label in labels:
        evidence = label["relevant_evidence"]
        require(
            label["quote_hash"] == [e["quote_hash"] for e in evidence],
            "Parallel hash list differs",
        )
        expected = [
            {
                "paper_id": e["paper_id"],
                "field": "abstract",
                "start": e["start"],
                "end": e["end"],
            }
            for e in evidence
        ]
        require(label["source_locator"] == expected, "Parallel locator list differs")
    result = {
        "task_count": len(labels),
        "source_phase_sha256": digest(frozen),
        "public_only": public_only,
    }
    if not public_only:
        result.update(verify_private(root, manifest, labels))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-only",
        action="store_true",
        help="Check the public release without local source materials",
    )
    print(json.dumps(verify(ROOT, parser.parse_args().public_only), indent=2))
