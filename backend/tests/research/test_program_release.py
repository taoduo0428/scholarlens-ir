"""Use isolated registries and synthetic approvals to test the E11 release path."""
import json
from time import monotonic, sleep
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend.app1 import create_app
from backend.config import Settings
from backend.research.lab_store import LabStore, fingerprint
from backend.research.skills.program import ResearchSkillSpec
from backend.research.skills.registry import POLICY_BASE, SKILL_BASE, bind_versions, resolve_program
from backend.research.tools import LocalCorpus
from tools.research_eval.inputs import GENERATION
from tools.research_eval.workspace_suite import suite_groups
from tools.research_evolution.program_release import approved, registry_db, transition


def fixture_lab(root, *, changed=True, substitute_goal=False):
    """Mechanical sign-off fixtures. Never use the synthetic judgments as research results."""
    lab = LabStore(root / "lab.sqlite", writable=True)
    groups, suite = suite_groups("independent")
    program = ResearchSkillSpec(intents=["conflicting_findings"], min_papers=2,
                                steps=["identify_comparators", "collect_conditions"],
                                expected="condition_matrix", dataset_hash="a" * 64, trace_hashes=["b" * 64])
    config = dict(skill=program.model_dump(), suite=suite, runtime_policy="E11",
                  base_skill=SKILL_BASE, base_policy=POLICY_BASE)
    candidate = {**config, "candidate_variant": "skill"}
    marks = {}
    for group in groups:
        for task in group["tasks"]:
            applies = task["kind"] == "controversy"
            for variant in ("contract", "skill"):
                active = variant == "skill" and applies
                lab.save_trial(dict(split="independent", task=task["id"], variant=variant,
                    scope=task["scope"], goal="replaced fixture" if substitute_goal else task["goal"],
                    suite=suite, generation=GENERATION, model="none", runtime_policy="E11",
                    origin="frozen-public-replay", scope_errors=0, private_sources=0,
                    max_tools=10, max_models=0, tools=2, models=0, source_checks=[True],
                    sources=[{"paper_id": task["scope"][0]}], exact_answer=None, abstained=None,
                    policy=fingerprint(config), program_version=program.version if variant == "skill" else SKILL_BASE,
                    skill_steps=program.steps if active else [], claims=[], judgments=None, direct=[],
                    answer="fixture variant" if active and changed else "fixture baseline"))
            marks[task["id"]] = dict(base=False, candidate=applies, source_note="synthetic gate fixture")
    version = lab.register(candidate, review=dict(reviewer="fixture-review", tasks=marks,
                                                  policy=fingerprint(candidate)))
    return lab, version, program


def account(client):
    data = {"username": "acct-" + uuid4().hex[:12], "password": uuid4().hex}
    assert client.post("/api/auth/register", json=data).status_code == 201
    return {"Authorization": "Bearer " + client.post("/api/auth/login", json=data).json()["access_token"]}


def finish(client, uid, headers):
    until = monotonic() + 20
    while monotonic() < until:
        state = client.get("/api/research/tasks/" + uid, headers=headers).json()["state"]
        if state["status"] in {"completed", "partial", "failed"}:
            assert state["status"] != "failed", state["warnings"]
            return state
        sleep(.05)
    pytest.fail("worker did not finish")


def test_approved_program_is_pinned_across_app_restart_and_rollback(tmp_path, monkeypatch):
    lab, candidate, program = fixture_lab(tmp_path)
    registry = tmp_path / "registry"
    with pytest.raises(ValueError, match="approved lab candidate"):
        transition(registry, "fixture-release", SKILL_BASE, lab=lab.path, candidate=candidate)
    lab.operator(candidate, "approve", "fixture-approver")
    release = transition(registry, "fixture-release", SKILL_BASE, lab=lab.path, candidate=candidate)
    with pytest.raises(ValueError, match="release changed"):
        transition(registry, "fixture-release", SKILL_BASE)
    assert bind_versions(registry, programs=True) == (release, POLICY_BASE)
    assert bind_versions(registry) == (SKILL_BASE, POLICY_BASE)
    task = next(t for t in suite_groups("independent")[0][0]["tasks"] if t["kind"] == "controversy")
    corpus = LocalCorpus([{"paper_id": pid, "title": f"Fixture thermal paper {i}",
                           "abstract": "This method estimates heat demand under a measured thermal load."}
                          for i, pid in enumerate(task["scope"])], GENERATION)
    monkeypatch.setenv("SCHOLARLENS_E11_ENABLED", "true")
    monkeypatch.setenv("SCHOLARLENS_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("SCHOLARLENS_APPROVED_REGISTRY", str(registry))
    monkeypatch.setattr("backend.research.tools.EsCorpus", lambda *args, **kwargs: corpus)
    settings = Settings(runtime_dir=str(tmp_path / "runtime"))
    payload = {"goal": task["goal"], "scope": {"paper_ids": task["scope"]}}
    url = "/api/research/tasks"
    client = TestClient(create_app(settings, client=object()))
    try:
        owner, other = account(client), account(client)
        headers = {**owner, "Idempotency-Key": "before-restart"}
        assert client.post(url, headers=headers, json={**payload, "skill_version": release}).status_code == 400
        posted = client.post(url, headers=headers, json=payload)
        assert posted.status_code == 202
        before = posted.json()["task_id"]
        assert client.get(url + "/" + before, headers=other).status_code == 404
        initial = client.get(url + "/" + before, headers=owner).json()["state"]
        assert (initial["status"], initial["skill_version"]) == ("queued", release)
        paths = client.app.openapi()["paths"]
        assert all("post" not in ops and "put" not in ops and "patch" not in ops and "delete" not in ops
                   for route, ops in paths.items() if "evolution-lab" in route)
    finally:
        client.close()
    assert transition(registry, "fixture-release", release) == SKILL_BASE
    assert resolve_program(release, registry) == program
    with TestClient(create_app(settings, client=object())) as restarted:
        assert restarted.post(url, headers=headers, json=payload).json()["task_id"] == before
        old = finish(restarted, before, owner)
        assert old["skill_version"] == release and old["skill_steps"] == program.steps
        assert old["budget"]["tool_calls_used"] <= old["budget"]["max_tool_calls"]
        assert old["budget"]["model_calls_used"] == 0
        assert all(row["paper_id"] in task["scope"] for row in old["evidence_refs"])
        resp = restarted.post(url, headers={**owner, "Idempotency-Key": "after-restart"}, json=payload)
        assert resp.status_code == 202
        new = finish(restarted, resp.json()["task_id"], owner)
        assert new["skill_version"] == SKILL_BASE and new["skill_steps"] == []
        with registry_db(registry) as db:
            db.execute("UPDATE active SET version=? WHERE kind='program'", (release,))
            db.execute("DELETE FROM audit WHERE action='publish_program'")
        invalid = restarted.post(url, headers={**owner, "Idempotency-Key": "corrupt"}, json=payload)
        assert invalid.status_code == 503 and invalid.json()["error"]["code"] == "research_registry_unavailable"


@pytest.mark.parametrize(("changed", "wrong_goal", "error"), [
    (False, False, "changed research output"), (True, True, "regression receipt")])
def test_approvals_require_changed_output_on_frozen_questions(tmp_path, changed, wrong_goal, error):
    lab, version, _ = fixture_lab(tmp_path, changed=changed, substitute_goal=wrong_goal)
    lab.operator(version, "approve", "fixture-review")
    with pytest.raises(ValueError, match=error):
        approved(lab.path, version)


def test_trials_changed_after_review_block_publication(tmp_path):
    lab, version, _ = fixture_lab(tmp_path)
    lab.operator(version, "approve", "fixture-review")
    with lab.db() as db:
        rowid, data = db.execute("SELECT rowid,data FROM trials LIMIT 1").fetchone()
        row = json.loads(data)
        row["tools"] += 1
        db.execute("UPDATE trials SET data=? WHERE rowid=?", (json.dumps(row), rowid))
    with pytest.raises(ValueError, match="trials changed"):
        approved(lab.path, version)
