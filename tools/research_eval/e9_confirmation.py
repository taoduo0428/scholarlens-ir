"""Second-family confirmation of named-paper excerpts within a multi-paper scope."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.claim_verifier import sentences
from tools.research_eval.e9_accept import public_cases
from tools.research_eval.inputs import BENCH, GENERATION, OID
from tools.research_eval.trace_loss import execute
from tools.research_eval.workspace_suite import corpus_file, excluded


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    used=excluded().union(*(set(docs) for _,_,docs,_,_ in public_cases()))
    for g in json.loads((BENCH/"workspace-v4-frozen.json").read_bytes())["dataset"]["groups"]:
        used.update(p["paper_id"] for p in g["papers"])
    pool=[]
    digest=sha256()
    with corpus_file().open("rb") as lines:
        for line in lines:
            digest.update(line)
            p=json.loads(line)
            abstract=p.get("abstract","")
            lines_=sentences(abstract)
            if p["paper_id"] not in used and p.get("title") and lines_ and abstract.startswith(lines_[0]) and lines_[0].endswith("."):
                pool.append((sha256(("e9/cn-final/"+p["paper_id"]).encode()).digest(),{k:p[k] for k in ("paper_id","title","abstract")}))
    assert digest.hexdigest()==OID
    papers=[p for _,p in sorted(pool,key=lambda r:r[0])[:6]]
    with TemporaryDirectory(dir=args.output) as tmp:
        for policy in ("V1","V5","E9"):
            rows=[]
            for i,p in enumerate(papers):
                other=papers[(i+1)%len(papers)]
                docs={d["paper_id"]:d for d in [p,other]}
                title=p["title"]
                for kind,q in [("direct",f"摘录《{title}》摘要的第一句并附原文位置。"),("partial",f"摘录《{title}》摘要的第一句，再解释作者的理由。"),("absent",f"请给出《{title}》摘要在PDF中的边界框坐标。")]:
                    t=execute(q,list(docs),docs,GENERATION,Path(tmp)/policy/str(i)/kind,policy)
                    report=t["report"]
                    released=[c for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]
                    exact=any(c["statement"]==sentences(p["abstract"])[0] and c["paper_ids"]==[p["paper_id"]] for c in released)
                    rows.append({
                        "case": i, "scope": list(docs), "kind": kind, "correct_excerpt": exact,
                        "partial": report.get("answerability", {}).get("status") == "partially_answerable",
                        "released": bool(released), "tools": t["budget"]["tool_calls_used"], "ms": t["elapsed_ms"],
                    })
            (args.output/(policy+".json")).write_text(json.dumps(rows,indent=2),encoding="utf8")
            print(policy,len(rows),flush=True)


if __name__=="__main__":
    main()
