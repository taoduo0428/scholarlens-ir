"""Frozen, post-hoc mechanical checks on public abstracts and controlled multipart records.

Run only after freezing a candidate. Never expose expected answers to the graph.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.research.claim_verifier import sentences
from tools.research_eval.inputs import BENCH, GENERATION, OID
from tools.research_eval.trace_loss import execute
from tools.research_eval.workspace_suite import corpus_file, excluded


def public_cases():
    used=excluded()
    for g in json.loads((BENCH/"workspace-v4-frozen.json").read_bytes())["dataset"]["groups"]:
        used.update(p["paper_id"] for p in g["papers"])
    choices=[]
    digest=sha256()
    with corpus_file().open("rb") as inp:
        for line in inp:
            digest.update(line)
            r=json.loads(line)
            title=r.get("title","")
            abstract=r.get("abstract","")
            lines=sentences(abstract)
            if r["paper_id"] in used or not title or '"' in title or not lines or not abstract.startswith(lines[0]) or not lines[0].endswith("."):
                continue
            choices.append((sha256(("e9-sample-v1/"+r["paper_id"]).encode()).digest(),{k:r[k] for k in ("paper_id","title","abstract")}))
    assert digest.hexdigest()==OID
    for _,doc in sorted(choices,key=lambda x:x[0])[:6]:
        title,pid=doc["title"],doc["paper_id"]
        known=sentences(doc["abstract"])[0]
        for case,goal in [
            ("fact",f'Quote the first sentence of the abstract of "{title}".'),
            ("layout",f'What are the PDF bounding box coordinates of the abstract of "{title}"?'),
            ("multipart",f'Quote the first sentence of the abstract of "{title}" and give its PDF page number.'),
        ]:
            yield case,goal,{pid:doc},known,GENERATION


def controls():
    for paper,substance in (("Garnet","titanium"),("Indigo","copper"),("Quartz","aluminium")):
        pid=paper.lower()
        text=f"The material of the sensor is {substance}."
        doc={"paper_id":pid,"title":paper+" trial","abstract":text+" Its housing was inspected under a microscope."}
        yield "attribute","What is the material of the sensor?",{pid:doc},text,"fixture:e9-controlled"
        yield "distractor","What is the material of the microscope?",{pid:doc},None,"fixture:e9-controlled"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--policies",nargs="+",default=["V1","V5","E9"])
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases=list(public_cases())+list(controls())
    with TemporaryDirectory(dir=args.output) as tmp:
        for policy in args.policies:
            rows=[]
            for i,(kind,goal,docs,gold,gen) in enumerate(cases):
                t=execute(goal,list(docs),docs,gen,Path(tmp)/policy/str(i),policy)
                report=t["report"]
                direct=[c["statement"] for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]
                part=report.get("answerability",{}).get("status")
                rows.append({"case":i,"kind":kind,"scope":list(docs),"goal":goal,"statements":direct,
                             "exact":gold in direct if gold else None,"published":bool(direct),
                             "answerability":part,"partial_correct":part=="partially_answerable" and gold in direct if kind=="multipart" else None,
                             "scope_errors":sum(s["paper_id"] not in docs for s in report["sources"]),
                             "tools":t["budget"]["tool_calls_used"],"model_calls":t["budget"]["model_calls_used"],"ms":t["elapsed_ms"]})
            (args.output/(policy+".json")).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf8")
            print(policy,len(rows),sum(r["exact"] is True for r in rows if r["kind"] in {"fact","attribute"}),
                  sum(r["published"] for r in rows if r["kind"] in {"layout","distractor"}),
                  sum(r["partial_correct"] is True for r in rows),flush=True)


if __name__=="__main__":
    main()
