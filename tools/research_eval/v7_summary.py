"""Aggregate public numbers from local sealed replays without exporting source text or accounts."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median

from tools.research_eval.v7_compare import POLICIES
from tools.research_eval.v7_holdout import DEST


def proportion(hits, n):
    z = 1.95996398454
    mean = hits / n
    scale = 1 + z*z/n
    center = (mean + z*z/(2*n)) / scale
    margin = z * math.sqrt(mean*(1-mean)/n + z*z/(4*n*n)) / scale
    return {"count": hits, "total": n, "wilson95": [round(max(0,center-margin),4), round(min(1,center+margin),4)]}


def latency(values):
    values = sorted(values)
    return dict(p50_ms=round(median(values), 2), p95_ms=round(values[math.ceil(.95*len(values))-1], 2))


def holdout(path):
    seal = sha256(DEST.read_bytes()).hexdigest()
    results = {}
    metrics = {"quote": "exact", "overview": "linked_overview", "layout": "false_release"}
    for policy in POLICIES:
        rows = []
        for n in range(28):
            for kind, metric in metrics.items():
                case = f"group-{n:02d}-{kind}"
                row = json.loads((path/f"{case}-{policy}.json").read_bytes())
                if (row["case"], row["policy"], row["dataset_sha256"]) != (case, policy, seal) or type(row[metric]) is not bool:
                    raise ValueError("holdout identity or score mismatch")
                rows.append(row)
        summary = {metric: proportion(sum(r[metric] for r in rows if r["kind"]==kind), 28)
                   for kind, metric in metrics.items()}
        summary.update(latency([r["ms"] for r in rows]), tool_calls=sum(r["tools"] for r in rows),
                       model_calls=sum(r["model_calls"] for r in rows), scope_errors=sum(r["scope_errors"] for r in rows))
        results[policy] = summary
    return results


def silver(rows):
    positives = [r for r in rows if r["expected"] in {"answerable","partially_answerable"}]
    negatives = [r for r in rows if r["expected"] in {"not_comparable","insufficient_evidence"}]
    if (len(positives),len(negatives)) != (70,41):
        raise ValueError("unexpected label distribution")
    return dict(direct_on_positive=proportion(sum(r["direct_count"]>0 for r in positives),len(positives)),
                no_direct_on_positive=proportion(sum(r["direct_count"]==0 for r in positives),len(positives)),
                direct_on_negative=proportion(sum(r["direct_count"]>0 for r in negatives),len(negatives)),
                exact_answerability=proportion(sum(r["expected"]==r["predicted"] for r in rows),len(rows)),
                source_span_overlap=proportion(sum(r["overlapping"] for r in rows),sum(r["located_sources"] for r in rows)),
                successful_tool_calls=proportion(sum(r["tool_ok"] for r in rows),sum(r["actions"] for r in rows)),
                task_states=dict(Counter(r["status"] for r in rows)), **latency([r["elapsed_ms"] for r in rows]))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("holdout","e10","e11","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args = p.parse_args()
    old, new = (json.loads(path.read_bytes()) for path in (args.e10,args.e11))
    pairs = [(r["task_id"],r["expected"]) for r in old]
    if len(set(pairs)) != 111 or pairs != [(r["task_id"],r["expected"]) for r in new]:
        raise ValueError("replays must contain identical cases")
    result = {"holdout_sha256":sha256(DEST.read_bytes()).hexdigest(),"holdout":holdout(args.holdout),
              "silver":{"E10":silver(old),"E11":silver(new)}, "paired_direct":dict(Counter(
                  f"{int(a['direct_count']>0)}_to_{int(b['direct_count']>0)}" for a,b in zip(old,new)))}
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
