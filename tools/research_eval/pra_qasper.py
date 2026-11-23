"""Compare two frozen ScholarLens policies on published QASPER v0.3 human annotations."""
import argparse
import json
import re
import tarfile
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.claim_verifier import sentence_boundaries
from tools.research_eval.trace_loss import execute
from tools.research_eval.v6_holdout import source_rows
from tools.research_eval.v7_independent_verifier import source_valid

ARCHIVE = "72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72"


def digest(text):
    return sha256(text.encode()).hexdigest()


def norm(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def select(dataset, batch=1):
    excluded = {norm(p["title"]) for p in source_rows()}
    pool = []
    for pid, paper in dataset.items():
        if norm(paper["title"]) in excluded:
            continue
        for question in paper["qas"]:
            annotations = question["answers"]
            labels = {a["answer"]["unanswerable"] for a in annotations}
            if len({a["worker_id"] for a in annotations}) >= 2 and len(labels) == 1:
                pool.append((digest("scholarlens-qasper-v1:" + question["question_id"]), pid, question, labels.pop()))
    seen = set()
    ordered = sorted(pool, key=lambda item: item[0])
    for _ in range(batch):
        quota = {False: 24, True: 8}
        chosen = []
        for _, pid, question, negative in ordered:
            title = norm(dataset[pid]["title"])
            if title not in seen and quota[negative]:
                chosen.append((pid, question, negative))
                seen.add(title)
                quota[negative] -= 1
        if any(quota.values()):
            raise ValueError("insufficient eligible questions")
    return chosen


def document(pid, paper):
    parts, headings, offset = [], [], 0
    for section in paper["full_text"]:
        title = section["section_name"]
        if title:
            headings.append({"title": title, "start": offset})
        for text in [title, *section["paragraphs"]]:
            if text:
                parts.append(text)
                offset += len(text) + 1
    return {"paper_id": pid, "title": paper["title"], "abstract": paper["abstract"],
            "fulltext": "\n".join(parts), "sections": headings}


def retained_reference_sentences(paragraph, document_text, start, end):
    """Return exactly contained sentences at the annotated paragraph's original location."""
    bounds = []
    cursor = 0
    for split in [*sentence_boundaries(paragraph), None]:
        stop = split.start() if split else len(paragraph)
        raw = paragraph[cursor:stop]
        sentence = raw.strip()
        if sentence and sentence[-1] in ".!?。！？":
            left = cursor + len(raw) - len(raw.lstrip())
            bounds.append((left, left + len(sentence), sentence))
        if split:
            cursor = split.end()
    for occurrence in re.finditer(re.escape(paragraph), document_text):
        origin = occurrence.start()
        if origin >= end:
            break
        if occurrence.end() > start:
            yield from (sentence for left, right, sentence in bounds
                        if start <= origin + left and origin + right <= end)


def score(report, doc, annotations):
    sources = {s["evidence_id"]: s for s in report["sources"]}
    direct = set(report["sections"]["verified"])
    claims = [c for c in report["claims"] if c["claim_id"] in direct]
    excerpts = [c["statement"] for c in claims]
    if len(claims) != len(direct):
        raise ValueError("missing published claim")
    for claim in claims:
        if claim["paper_ids"] != [doc["paper_id"]] or not claim["evidence_ids"]:
            raise ValueError("scope mismatch")
        for eid in claim["evidence_ids"]:
            src = sources[eid]
            if (not source_valid(src, {doc["paper_id"]: doc}, [doc["paper_id"]], "qasper:" + ARCHIVE)
                    or claim["statement"] not in src["quote"]):
                raise ValueError("source mismatch")
    answers = [a["answer"] for a in annotations]
    evidence = {p for a in answers for p in a["evidence"] if p}
    located = False
    readable = {p: set() for p in evidence}
    generation = "qasper:" + ARCHIVE
    for src in sources.values():
        if not source_valid(src, {doc["paper_id"]: doc}, [doc["paper_id"]], generation):
            raise ValueError("retained source mismatch")
        text = doc[src["field"]]
        start, end = map(int, src["locator"].rsplit(":", 1)[1].split("-"))
        for paragraph in evidence:
            at = text.find(paragraph)
            if at >= 0 and min(at + len(paragraph), end) - max(at, start) >= min(40, len(paragraph)):
                located = True
            readable[paragraph].update(retained_reference_sentences(paragraph, text, start, end))
    cited = any(s in paragraph for s in excerpts for paragraph in evidence)
    extractive = [a for a in answers if a["extractive_spans"]]
    def covers_spans(answer, sentences):
        statements = [f" {norm(sentence)} " for sentence in sentences]
        return all(norm(span) and any(f" {norm(span)} " in s for s in statements)
                   for span in answer["extractive_spans"])

    def covered(answer):
        return covers_spans(answer, (s for s in excerpts if any(s in p for p in answer["evidence"])))

    all_spans_read = any(covers_spans(a, (s for p in a["evidence"] for s in readable.get(p, ())))
                         for a in extractive)
    return {"direct": len(direct), "reference_passage_read": located, "direct_sentence_in_reference": cited,
            "has_extractive_reference": bool(extractive), "all_spans_with_reference": any(covered(a) for a in extractive),
            "all_spans_in_retained_reference_sentences": all_spans_read if extractive else None,
            "published_ids": sorted(direct)}


def main(archive, out, arms, batch):
    if sha256(archive.read_bytes()).hexdigest() != ARCHIVE:
        raise ValueError("unexpected official test archive")
    with tarfile.open(archive) as reader:
        data = json.load(reader.extractfile("qasper-test-v0.3.json"))
    cases = select(data, batch)
    out.mkdir(exist_ok=False)
    manifest = [{"paper": pid, "question": q["question_id"], "unanswerable": no} for pid, q, no in cases]
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    with TemporaryDirectory(dir=out) as tmp:
        for arm in arms:
            results = []
            for info, (pid, q, _) in zip(manifest, cases, strict=True):
                doc = document(pid, data[pid])
                trace = execute(q["question"], [pid], {pid: doc}, "qasper:" + ARCHIVE,
                                Path(tmp)/arm/q["question_id"], "E11", pra_arm=arm)
                results.append({**info, **score(trace["report"], doc, q["answers"]), "tools": len(trace["actions"])})
            (out/(arm+".json")).write_text(json.dumps(results, indent=2), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", choices=("A", "G"), default=["A", "G"])
    parser.add_argument("--batch", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    main(args.archive, args.out, args.arms, args.batch)
