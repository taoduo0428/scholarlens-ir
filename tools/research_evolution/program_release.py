"""Prepare and explicitly publish an independently approved E11 research program."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory

from backend.research.lab_store import LabStore, fingerprint
from backend.research.skills.program import ResearchSkillSpec
from backend.research.skills.registry import POLICY_BASE, SKILL_BASE, bind_versions, resolve_versions
from backend.research.skills.releases import ProgramReceipt, pinned_release


def changed_outputs(rows):
    """Which paired trials changed research content visible to a reviewer?"""
    content = ("answer", "direct", "claims", "judgments", "sources")
    baseline = {r["task"]: r for r in rows if r["variant"] == "contract"}
    return {r["task"] for r in rows if r["variant"] == "skill" and r["task"] in baseline
            and any(r[k] != baseline[r["task"]][k] for k in content)}


def stage(lab_path, output, registry=None):
    from tools.research_eval.agent_ablation import learn
    from tools.research_eval.workspace_arena import load_split, run_one

    if lab_path.exists() or output.exists():
        raise ValueError("choose a fresh lab database and stage directory")
    output.mkdir(parents=True)
    lab = LabStore(lab_path, writable=True)
    skill, policy = bind_versions(registry)
    tuning = resolve_versions(skill, policy, registry)
    tasks, docs, suite = load_split("independent")
    with TemporaryDirectory(dir=output) as tmp:
        root = Path(tmp)
        program, _ = learn(root / "public-train")
        config = {"skill": program.model_dump(), "suite": suite, "runtime_policy": "E11",
                  "base_skill": skill, "base_policy": policy}
        candidate = {**config, "candidate_variant": "skill"}
        for task in tasks:
            for variant in ("contract", "skill"):
                row = run_one(task, docs, suite, "independent", variant, root / variant / task["id"],
                              program, tuning, runtime_policy="E11")
                row.update(policy=fingerprint(config), runtime_policy="E11",
                           program_version=program.version if variant == "skill" else SKILL_BASE)
                lab.save_trial(row)
    (output / "candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf8")
    rows = lab.rows("independent")
    summary = {"suite": suite, "program": program.version, "candidate": fingerprint(candidate),
               "paired_tasks": len(tasks), "changed_outputs": sorted(changed_outputs(rows))}
    for variant in ("contract", "skill"):
        group = [r for r in rows if r["variant"] == variant]
        checks = [c for r in group for c in r["source_checks"]]
        summary[variant] = {"tools": sum(r["tools"] for r in group), "models": sum(r["models"] for r in group),
                            "sources": len(checks), "verified": sum(checks),
                            "program_triggered": sum(bool(r["skill_steps"]) for r in group)}
    (output / "regression.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    print(fingerprint(candidate))


def approved(lab_path, version):
    from tools.research_eval.inputs import GENERATION
    from tools.research_eval.workspace_suite import suite_groups

    lab = LabStore(lab_path)
    with lab.db() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT policy,decision FROM candidates WHERE version=?", (version,)).fetchone()
        if not row or row["decision"] != "approved":
            raise ValueError("an approved lab candidate is required")
        data = json.loads(row["policy"])
        if (fingerprint(data) != version or data.get("candidate_variant") != "skill"
                or data.get("runtime_policy") != "E11"):
            raise ValueError("candidate does not identify an E11 program")
        program = ResearchSkillSpec.model_validate(data["skill"])
        rows = [json.loads(r[0]) for r in db.execute(
            "SELECT data FROM trials WHERE split='independent' ORDER BY task,variant")]
        events = db.execute("SELECT event,detail FROM ledger WHERE version=? ORDER BY seq", (version,)).fetchall()
        if [e["event"] for e in events] != ["awaiting_review", "approved"]:
            raise ValueError("missing independent review and approval history")
        decision = json.loads(events[0]["detail"])
        mark = decision["review"]
        if (decision["reasons"] or mark["policy"] != version or not mark["reviewer"].strip()
                or not events[1]["detail"].strip() or fingerprint(rows) != decision["trials"]):
            raise ValueError("review or independent trials changed")
        regression = fingerprint(rows)
        paired = {key: {r["task"]: r for r in rows if r["variant"] == key} for key in ("contract", "skill")}
        groups, stamp = suite_groups("independent")
        tasks = {t["id"]: t for group in groups for t in group["tasks"]}
        if (data["suite"] != stamp or len(rows) != len(tasks) * 2 or
                paired["skill"].keys() != tasks.keys() or paired["contract"].keys() != tasks.keys()):
            raise ValueError("incomplete paired E11 evidence")
        gains = {task for task, item in mark["tasks"].items() if item["candidate"] and not item["base"]}
        if not gains or not gains.issubset(changed_outputs(rows)):
            raise ValueError("reviewed gain must correspond to changed research output")
        config_id = fingerprint({k: v for k, v in data.items() if k != "candidate_variant"})
        executed = False
        for kind, group in paired.items():
            for r in group.values():
                task = tasks[r["task"]]
                if (r["generation"] != GENERATION or r["scope"] != task["scope"] or r["goal"] != task["goal"]
                        or r["origin"] != "frozen-public-replay" or r["split"] != "independent"
                        or r["runtime_policy"] != "E11" or r["policy"] != config_id or r["suite"] != data["suite"]
                        or r["program_version"] != (program.version if kind == "skill" else SKILL_BASE)
                        or r["scope_errors"] or r["private_sources"] or not all(r["source_checks"])
                        or len(r["source_checks"]) != len(r["sources"])
                        or any(s["paper_id"] not in r["scope"] for s in r["sources"])
                        or not 0 <= r["tools"] <= r["max_tools"] or not 0 <= r["models"] <= r["max_models"]
                        or (kind == "contract" and r["skill_steps"])
                        or any(step not in program.steps for step in r["skill_steps"])):
                    raise ValueError("regression receipt does not cover this program and budget")
                executed |= kind == "skill" and bool(r["skill_steps"])
        if not executed:
            raise ValueError("program was never applicable in the reviewed trials")
        return data, program, fingerprint([decision, events[1]["detail"]]), regression


def registry_db(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path / "approved.sqlite3")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS approved(kind TEXT,version TEXT,config TEXT,parent TEXT,
           review_hash TEXT,PRIMARY KEY(kind,version));
        CREATE TABLE IF NOT EXISTS active(kind TEXT PRIMARY KEY,version TEXT);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,kind TEXT,version TEXT,action TEXT,
           reviewer TEXT,evaluation TEXT);
    """)
    return db


def transition(registry, operator, expected, *, lab=None, candidate=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", operator):
        raise ValueError("named release operator required")
    reviewed = approved(lab, candidate) if lab is not None else None
    with closing(registry_db(registry)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        active = dict(db.execute("SELECT kind,version FROM active"))
        current = active.get("program", SKILL_BASE)
        if current != expected:
            raise ValueError("program release changed")
        if reviewed:
            data, program, review, regression = reviewed
            if (active.get("skill", SKILL_BASE), active.get("policy", POLICY_BASE)) != (
                    data["base_skill"], data["base_policy"]):
                raise ValueError("active tuning differs from reviewed version")
            resolve_versions(data["base_skill"], data["base_policy"], registry)
            receipt = ProgramReceipt(program=program, base_skill=data["base_skill"], base_policy=data["base_policy"],
                                     lab_candidate=candidate, review=review, regression=regression,
                                     suite=data["suite"], parent=current)
            version = receipt.version
            db.execute("INSERT OR IGNORE INTO approved VALUES('program',?,?,?,?)",
                       (version, receipt.encoded(), current, review))
            event = "publish_program"
        else:
            version = pinned_release(db, current).parent
            if version != SKILL_BASE:
                pinned_release(db, version)
            regression, event = current, "rollback_program"
        db.execute("INSERT INTO audit(kind,version,action,reviewer,evaluation) VALUES('program',?,?,?,?)",
                   (version, event, operator, regression))
        if reviewed:
            pinned_release(db, version)
        db.execute("INSERT OR REPLACE INTO active VALUES('program',?)", (version,))
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("stage")
    prepare.add_argument("--lab", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--registry", type=Path)
    review = actions.add_parser("register")
    for name in ("lab", "candidate"):
        review.add_argument("--" + name, type=Path, required=True)
    review.add_argument("--review", type=Path, help="independent review JSON, if available")
    for action in ("publish", "rollback"):
        sub = actions.add_parser(action)
        sub.add_argument("--registry", type=Path, required=True)
        sub.add_argument("--operator", required=True)
        sub.add_argument("--expected", required=True)
        if action == "publish":
            sub.add_argument("--lab", type=Path, required=True)
            sub.add_argument("--candidate", required=True)
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.lab, args.output, args.registry)
    elif args.action == "register":
        lab = LabStore(args.lab, writable=True)
        reasons = [] if changed_outputs(lab.rows("independent")) else ["unchanged_research_output"]
        print(lab.register(json.loads(args.candidate.read_bytes()), reasons=reasons,
                           review=json.loads(args.review.read_bytes()) if args.review else None))
    else:
        print(transition(args.registry, args.operator, args.expected,
                         lab=getattr(args, "lab", None), candidate=getattr(args, "candidate", None)))


if __name__ == "__main__":
    main()
