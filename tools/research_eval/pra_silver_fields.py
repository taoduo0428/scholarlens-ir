"""Post-hoc AI review of the frozen A/G publications against the original Silver requirements."""

import argparse
import json
from pathlib import Path

from tools.research_eval.pra_baseline import LABELS, POSITIVE
from tools.research_eval.v6_silver import rows


# Only visible direct statements are credited, with a task-local claim key. A compound requirement
# receives partial credit when the statement covers only some questions or only one requested paper.
# This table is offline evaluation material and is never imported by the runtime.
REVIEW = {
    "v3-quantum-compare": [(1, "partial", "b219f2bd"), (2, "partial", "5fe4e3d3")],
    "v3-quantum-multihop": [(1, "full", "5fe4e3d3"), (2, "full", "5bbed7ab"), (3, "partial", "919d35b2")],
    "v3-routing-compare": [(1, "full", "6f936f86"), (3, "partial", "6f936f86")],
    "v3-routing-multihop": [(1, "partial", "aff27694")],
    "v3-privacy-compare": [(1, "partial", "93be5f84")],
    "v3-privacy-multihop": [(2, "partial", "75424e16"), (3, "partial", "00bea3d4")],
    "review-04-comparison": [(1, "partial", "5ffd59ce")],
    "review-04-metrics": [(1, "partial", "f69d4634")],
    "review-06-fact": [(1, "full", "ea5ed897")],
    "review-06-comparison": [(1, "partial", "ea5ed897")],
    "review-09-comparison": [(1, "partial", "401befea")],
    "review-10-comparison": [(2, "partial", "b7636643"), (3, "partial", "c434d300")],
    "review-12-comparison": [(1, "partial", "9e824667"), (3, "partial", "9e824667")],
    "review-12-metrics": [(1, "partial", "19ce91c6")],
    "review-14-comparison": [(1, "partial", "ba7539f2"), (3, "partial", "ba7539f2")],
    "review-15-comparison": [(1, "partial", "3527b40c")],
    "review-16-comparison": [(2, "partial", "b5620366")],
    "review-17-comparison": [(1, "partial", "72f94426"), (3, "partial", "72f94426")],
    "review-17-metrics": [(1, "partial", "618cb0e3")],
}


def review(directory):
    task_rows = []
    counts = {"full": 0, "partial": 0, "absent": 0}
    for label in rows(LABELS):
        if label["answerability"] not in POSITIVE:
            continue
        task = label["task_id"]
        report = json.loads((directory/(task + ".json")).read_bytes())["report"]
        direct = report["sections"]["verified"]
        details = [{"requirement": text, "assessment": "absent", "claims": []} for text in label["required_fields"]]
        for ordinal, status, key in REVIEW.get(task, []):
            ids = [cid for cid in direct if cid.startswith("c-" + key)]
            if ids:
                if len(ids) != 1:
                    raise ValueError("ambiguous claim key")
                details[ordinal-1].update(assessment=status, claims=ids)
        for item in details:
            counts[item["assessment"]] += 1
        task_rows.append({"id": task, "requirements": details})
    return {"reviewer": "post-hoc single AI assessment of published direct claims", "counts": counts,
            "full_tasks": sum(all(f["assessment"] == "full" for f in r["requirements"]) for r in task_rows),
            "rows": task_rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidate", default="G7", help="candidate experiment directory")
    args = parser.parse_args()
    with args.out.open("x", encoding="utf8") as stream:
        json.dump({arm: review(args.root/folder/"diagnostic/E11") for arm, folder in [("A","A"),("G",args.candidate)]},
                  stream, ensure_ascii=False, indent=1)
        stream.write("\n")
