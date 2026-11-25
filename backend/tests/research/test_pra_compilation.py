"""PRA source selection, independent fields, and withdrawal when a premise disappears."""

from hashlib import sha256
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.research.answer_compiler import compile_answer, markdown
from backend.research.pra_relations import method_name, verify_derivation
from backend.research.workspace_model import SourceReview
from tools.research_eval.trace_loss import execute


def test_model_nominates_existing_ids_without_choosing_source_coordinates():
    data = {"evidence_id": "e-one", "sentence_id": "s-one", "field": "methods", "origin": "authors"}
    assert SourceReview.model_validate({"selections": [data]}).selections[0].field == "methods"
    with pytest.raises(ValidationError):
        SourceReview.model_validate({"selections": [{**data, "start": 0, "quote": "altered"}]})


@pytest.mark.parametrize("text", [
    "Earlier studies used dynamic programming for scheduling.",
    "We might use dynamic programming for scheduling.",
    "We use dynamic programming only if sufficient time is available.",
    "We use dynamic programming as a baseline for comparison.",
    "Using Monte Carlo simulations, we compute drift as a baseline for comparison.",
    "Using Monte Carlo simulations, we might compute phase drift.",
    "Using Monte Carlo simulations, other authors examined phase drift.",
    "We propose a process that can be used in Monte Carlo simulations.",
])
def test_qualified_method_cannot_become_an_author_relation(text):
    assert method_name(text) is None


def test_method_stated_as_an_instrument_of_author_action():
    assert method_name("Using Monte Carlo simulations, we computed phase drift.") == "Monte Carlo simulation"
    assert method_name("Using Monte Carlo simulations we examined lattice fluctuations.") == "Monte Carlo simulation"


def test_unregistered_method_needs_full_author_supplied_name():
    assert method_name("We use sparse lattice optimization (SLO) for scheduling.") == "sparse lattice optimization"
    assert method_name("We use stochastic likelihood optimization (SLO) for scheduling.") == "stochastic likelihood optimization"
    assert method_name("We use SLO for scheduling.") is None
    assert method_name("We use sparse lattice optimization (ABC) for scheduling.") is None


def test_metric_identity_is_distinct_from_its_value_and_external_protocol():
    from backend.research.profile_frames import METRIC_NAMES_QUESTION, states_metric_use
    assert METRIC_NAMES_QUESTION.fullmatch("Which evaluation metrics were used?")
    assert not METRIC_NAMES_QUESTION.fullmatch("What precision value was measured?")
    assert states_metric_use("We report precision as our primary evaluation metric.", "")
    criterion = "The checkpoint with the lowest validation RMSE was selected."
    assert states_metric_use(criterion, "Our models were evaluated on the test set.")
    assert not states_metric_use(criterion, "In prior work the models were evaluated on the test set.")
    assert not states_metric_use("We did not use BLEU as our evaluation metric.", "")


@pytest.mark.parametrize("group_request", [False, True])
def test_individual_limits_survive_missing_other_paper_but_shared_limits_do_not(tmp_path, group_request):
    statement = "Our study is limited to daytime observations."
    docs = {
        "a": {"paper_id": "a", "title": "Transit", "abstract": "We use dynamic programming for scheduling. " + statement},
        "b": {"paper_id": "b", "title": "Workshop", "abstract": "We use linear regression for estimation. "
              "To address this limitation, we introduce an estimator. We will discuss applications below."},
    }
    goal = ("综合这组论文各自的方法、主要结果和共同局限。" if group_request else
            "综合这组论文各自的方法、主要结果和局限。")
    report = execute(goal, list(docs), docs, "test:limits", tmp_path, "E11", pra_arm="G")["report"]
    fields = [f for q in report["field_requirements"] for f in q["fields"] if f["facet"] == "limitations"]
    decisions = report["answerability"]["fields"]
    if group_request:
        assert len(fields) == 1 and set(fields[0]["paper_ids"]) == set(docs)
        assert decisions[fields[0]["field_id"]]["status"] != "answerable"
    else:
        assert {tuple(f["paper_ids"]): decisions[f["field_id"]]["status"] for f in fields} == {
            ("a",): "answerable", ("b",): "insufficient_evidence"}
        section = next(s for s in report["compiled_answer"] if s["section"] == "limitations")
        assert [(i["paper_ids"], i["text"]) for i in section["items"]] == [(["a"], statement)]


def test_named_mixed_dimensions_exclude_permitted_distractor(tmp_path):
    docs = {pid: {"paper_id": pid, "title": title, "abstract": text} for pid, title, text in (
        ("a", "Transit design", "We use dynamic programming for scheduling. Our results show that delays decreased."),
        ("b", "Workshop design", "We use linear regression for forecasting."),
        ("c", "Unrequested study", "We use BERT for retrieval. Our results show that accuracy increased."),
    )}
    goal = "Compare the methods and reported findings of “Transit design” and “Workshop design”."
    r = execute(goal, list(docs), docs, "test:v8:names", tmp_path, "E11", pra_arm="G")["report"]
    fields = [f for q in r["field_requirements"] for f in q["fields"]]
    assert {(f["required_title"], f["facet"]) for f in fields} == {
        (title, facet) for title in ("Transit design", "Workshop design") for facet in ("method", "finding")}
    claims = {c["claim_id"]: c for c in r["claims"]}
    assert {p for cid in r["sections"]["verified"] for p in claims[cid]["paper_ids"]} == {"a", "b"}
    assert any(f["required_title"] == "Workshop design" and f["facet"] == "finding"
               and r["answerability"]["fields"][f["field_id"]]["status"] != "answerable" for f in fields)


@pytest.mark.parametrize("heading_offset,expected", [(0, True), (1, False)])
def test_method_gap_reads_validated_fulltext_heading(tmp_path, heading_offset, expected):
    statement = "我们采用线性回归估计明日气温。"
    doc = {"paper_id": "atlas", "title": "Forecasts", "abstract": "Archived summary of historical observations.",
           "fulltext": "研究方法。" + statement, "sections": [{"start": heading_offset, "title": "研究方法"}]}
    report = execute("What method did the authors use?", ["atlas"], {"atlas": doc}, "test:section",
                     tmp_path, "E11", pra_arm="G")["report"]
    direct = report["sections"]["verified"]
    answers = [c for c in report["claims"] if c["claim_id"] in direct and c["statement"] == statement]
    assert bool(answers) is expected
    if expected:
        ids = set(answers[0]["evidence_ids"])
        assert ids == {s["evidence_id"] for s in report["sources"] if s["field"] == "fulltext" and statement in s["quote"]}


def test_bilingual_pair_uses_exact_spans_and_withdraws_on_premise_loss(tmp_path):
    docs = {
        "p1": {"paper_id": "p1", "title": "Scheduling", "abstract": "We use dynamic programming for scheduling."},
        "p2": {"paper_id": "p2", "title": "资源分配", "abstract": "我们采用动态规划用于计算资源分配。"},
    }
    task = "Compare the methods used in the two papers."
    r = execute(task, list(docs), docs, "test:v8", tmp_path/"pair", "E11", pra_arm="G")["report"]
    edges = [e for e in r["profile_relations"] if e["relation"] == "uses"]
    assert len(edges) == 2
    claims = {c["claim_id"]: SimpleNamespace(**c) for c in r["claims"]}
    sources = {s["evidence_id"]: s for s in r["sources"]}
    assert verify_derivation(edges, claims, sources, docs)
    assert not verify_derivation(edges[:1], claims, sources, docs)
    assert not verify_derivation(edges, claims, {k:v for k,v in sources.items() if v["paper_id"]=="p1"}, docs)
    assert not verify_derivation(edges, claims, sources, {"p1"})
    assert not verify_derivation([{**edges[0], "target": "BERT"}, edges[1]], claims, sources, docs)
    assert len(r["compiled_answer"]) == 12
    assert any(x["kind"] == "shared_method" for x in r["method_relations"])
    relation = next(x for x in r["method_relations"] if x["kind"] == "shared_method")
    assert "《Scheduling》用于 scheduling" in relation["statement"]
    assert "《资源分配》用于 计算资源分配" in relation["statement"]
    assert not verify_derivation([{**edges[0], "application": "another task"}, edges[1]], claims, sources, docs)
    assert "#### Scheduling" in r["markdown"] and "#### 资源分配" in r["markdown"]
    assert any(x["kind"] == "derived" for section in r["compiled_answer"] if section["section"] == "common"
               for x in section["items"])
    for entry in r["compiled_answer"]:
        for item in entry["items"]:
            if item["kind"] == "source":
                assert all(item["text"] in sources[e]["quote"] for e in item["evidence_ids"])
    missing = {**docs, "p2": {**docs["p2"], "abstract": "Earlier studies used dynamic programming for resource allocation."}}
    weaker = execute(task, list(missing), missing, "test:v8:changed", tmp_path/"missing", "E11", pra_arm="G")["report"]
    assert {p for e in weaker["profile_relations"] if e["relation"]=="uses" for p in e["paper_ids"]} == {"p1"}
    assert weaker["answerability"]["status"] == "partially_answerable"
    assert not weaker["method_relations"]


def test_profiles_separate_goals_from_observed_results(tmp_path):
    text = ("We introduce a controller for scheduling jobs. The aim is to reduce waiting time for unobserved jobs. "
            "Previous studies reported a 15% reduction in waiting time.")
    docs = {"p": {"paper_id": "p", "title": "Scheduling jobs", "abstract": text}}
    report = execute("Describe the research objectives.", ["p"], docs, "test:objective",
                     tmp_path/"objective", "E11", pra_arm="B")["report"]
    p = report["research_profiles"][0]
    intended = next(x for x in p["fields"]["research_objective"] if x["quote"].startswith("The aim"))
    assert intended["attribution_sentence_id"] and intended["attribution_sentence_id"] != intended["sentence_id"]
    assert text[intended["start"]:intended["end"]] == intended["quote"]
    assert sha256(intended["quote"].encode()).hexdigest() == intended["quote_hash"]
    assert not p["fields"]["reported_findings"]


@pytest.mark.parametrize("goal", [
    "Compare the methods used in the two papers.",
    "综合这组论文各自的方法、主要结果和仍待解决的问题。",
])
def test_interface_join_preserves_direction_units_and_evidence(tmp_path, goal):
    from backend.research.method_interfaces import interface

    output = "Our method outputs an hourly demand matrix in MW."
    input_ = "Our method requires an hourly demand matrix in MW as input."
    docs = {"a": {"paper_id": "a", "title": "Emitter", "abstract": output},
            "b": {"paper_id": "b", "title": "Reader", "abstract": input_}}

    def compare(source, path):
        r = execute(goal, list(source), source, "test:v8:interface", path, "E11", pra_arm="G")["report"]
        return r, [x for x in r.get("method_relations", r.get("overview", {}).get("findings", []))
                   if x["kind"] == "complements"]

    r, relations = compare(docs, tmp_path/"intact")
    assert len(relations) == 1
    assert relations[0]["paper_ids"] == ["a", "b"] and len(relations[0]["evidence_ids"]) == 2
    assert "《Emitter》输出" in relations[0]["statement"] and "《Reader》所列输入" in relations[0]["statement"]
    assert relations[0]["statement"] in r["markdown"]
    assert interface(input_.replace("Our method requires", "Previous studies required")) is None
    assert interface(output.replace("outputs", "may output")) is None
    assert interface(input_.replace("MW", "mW")) != interface(input_)
    for n, changed in enumerate((input_.replace("MW", "mW"), output)):
        _, withdrawn = compare({**docs, "b": {**docs["b"], "abstract": changed}}, tmp_path/str(n))
        assert not withdrawn


def test_structured_method_requires_an_attributable_complete_procedure(tmp_path):
    from backend.research.profile_frames import abstract_method

    assert not abstract_method("Methods: Previous authors used a different mapping.")
    assert not abstract_method("Methods: The sensor was optimized if readings were reliable.")
    assert not abstract_method("Methods: We propose to measure the predicted rate, i.e.")
    assert not abstract_method("Methods: A significant problem in data analysis.")
    method = "Methods: The sensor was optimized for contactless mapping."
    docs = {"s": {"paper_id": "s", "title": "Sensor study", "abstract": method}}
    def direct(source, directory):
        report = execute("作者采用了什么方法？", ["s"], source, "test:structured-method",
                         directory, "E11", pra_arm="G")["report"]
        cited = set(report["sections"]["verified"])
        return [c["statement"] for c in report["claims"] if c["claim_id"] in cited]
    assert direct(docs, tmp_path/"ok") == [method]
    changed = {"s": {**docs["s"], "abstract": method + " Correction: We did not use this sensor."}}
    assert not direct(changed, tmp_path/"correction")


def test_subset_relation_has_its_own_scope_and_cannot_complete_the_overview(tmp_path):
    docs = {p: {"paper_id": p, "title": p, "abstract": statement} for p, statement in [
        ("a", "We use BM25 for document retrieval."), ("b", "We use BM25 for patent search."),
        ("c", "We use BERT for document classification.")]}
    report = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs), docs,
                     "test:v8:subset", tmp_path, "E11", pra_arm="G")["report"]
    relation = next(r for r in report["method_relations"] if r["kind"] == "shared_method")
    assert relation["scope"] == "subset" and relation["paper_ids"] == ["a", "b"]
    sections = {s["section"]: s for s in report["compiled_answer"]}
    assert any("《a》" in r["text"] and "《b》" in r["text"] for r in sections["relations"]["items"])
    assert not sections["synthesis"]["items"]


@pytest.mark.parametrize("connected", [True, False])
def test_method_only_overview_joins_verified_relations_without_inventing_direct_edges(tmp_path, connected):
    abstracts = {
        "a": "We use BM25 for patent retrieval.",
        "b": "We use BM25 for document retrieval.",
        "c": "We use BERT for document retrieval." if connected else "We use BERT for author identification.",
    }
    docs = {pid: {"paper_id": pid, "title": f"Study {pid.upper()}", "abstract": text} for pid, text in abstracts.items()}
    report = execute("综合这组论文各自的方法。", list(docs), docs,
                     "test:v8:connected-methods", tmp_path, "E11", pra_arm="G")["report"]
    fields = [field for question in report["field_requirements"] for field in question["fields"]]
    assert [field["facet"] for field in fields] == ["method", "method", "method", "overview"]
    synthesis = next(section["items"] for section in report["compiled_answer"] if section["section"] == "synthesis")
    assert (report["status"] == "completed") is connected
    assert bool(synthesis) is connected
    subsets = {tuple(item["paper_ids"]) for item in report["method_relations"]}
    assert subsets == ({("a", "b"), ("b", "c")} if connected else {("a", "b")})
    if connected:
        assert len(synthesis) == 1 and synthesis[0]["paper_ids"] == ["a", "b", "c"]
        claims = {claim["claim_id"]: claim for claim in report["claims"]}
        sources = {source["evidence_id"]: source for source in report["sources"]}
        for claim_id in synthesis[0]["claim_ids"]:
            claim = claims[claim_id]
            assert claim["statement"] == abstracts[claim["paper_ids"][0]]
            assert all(claim["statement"] in sources[evidence]["quote"] for evidence in claim["evidence_ids"])


def test_overview_recovers_attributed_body_when_abstract_is_unavailable(tmp_path):
    method = "We used line intercept sampling to measure average shrub height along each transect."
    finding = "We found that average shrub height increased by 18 cm."
    misleading = "We found tests on the Internet that took hours to administer."
    truncated = "We used a dispenser fitted with a 5/8-in."
    docs = {
        "a": {"paper_id": "a", "title": "Shrub sampling", "abstract": "",
              "fulltext": f"{method} {misleading} {truncated} outlet. {finding}"},
        "b": {"paper_id": "b", "title": "Canopy survey", "abstract": "",
              "fulltext": "Prior work used field measurements. We used aerial photography to estimate canopy cover."},
    }
    report = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs), docs,
                     "test:v8:no-abstract", tmp_path, "E11", pra_arm="G")["report"]
    claims = {c["claim_id"]: c for c in report["claims"]}
    released = {claims[c]["statement"]: claims[c] for c in report["sections"]["verified"]}
    sources = {r["evidence_id"]: r for r in report["sources"]}
    assert method in released and finding in released
    assert misleading not in released and truncated not in released
    assert released[method]["paper_ids"] == ["a"]
    assert all(sources[e]["field"] == "fulltext" for e in released[method]["evidence_ids"])
    assert report["status"] == "partial"
    assert not next(s for s in report["compiled_answer"] if s["section"] == "synthesis")["items"]


@pytest.mark.parametrize("abstract_repeats", [1, 65])
def test_missing_overview_role_places_body_candidate_after_both_abstracts(abstract_repeats):
    from backend.research.schemas import Scope
    from backend.research.tools import LocalCorpus, ToolRegistry

    text = "We used line intercept sampling to measure canopy cover."
    corpus = LocalCorpus([
        {"paper_id": "a", "title": "Survey", "abstract": "Background observations. " * abstract_repeats,
         "fulltext": text},
        {"paper_id": "b", "title": "Trials", "abstract": "We found that measured cover increased.",
         "fulltext": "We examined a completely different site."},
    ], "test:v8:body-priority")
    scope = Scope(paper_ids=["a", "b"])
    registry = ToolRegistry(corpus, owner_id=1, scope=scope, generation=corpus.generation)
    passages = registry.call("search_passages", {
        "query": "summarize the methods and findings", "paper_ids": scope.paper_ids,
        "abstract_profile": True, "profile_body_fallback": True, "limit": 3,
    })["passages"]
    assert [(row["paper_id"], row["field"]) for row in passages] == [
        ("a", "abstract"), ("b", "abstract"), ("a", "fulltext"),
    ]
    assert passages[-1]["quote"] == text


@pytest.mark.parametrize(("dataset", "other_result", "answerable"), [
    ("East", "", True),
    ("West", "", False),
    ("East", " Our chamber accuracy was 70% on dataset: East, setup: bench, protocol: blind.", False),
])
def test_author_measurements_support_a_comparison_only_when_aligned_and_unique(
        tmp_path, dataset, other_result, answerable):
    docs = {
        "a": {"paper_id": "a", "title": "First chamber", "abstract":
              "Our chamber accuracy was 73% on dataset: East, setup: bench, protocol: blind." + other_result},
        "b": {"paper_id": "b", "title": "Second chamber", "abstract":
              f"Our chamber accuracy was 87% on dataset: {dataset}, setup: bench, protocol: blind."},
    }
    report = execute("Which model has the highest accuracy?", list(docs), docs,
                     "test:v8:metric-premises", tmp_path, "E11", pra_arm="G")["report"]
    direct = [c for c in report["claims"] if c["claim_id"] in report["sections"]["verified"]]
    assert bool(direct) is answerable
    if answerable:
        assert report["status"] == "completed"
        assert len(direct) == 1 and direct[0]["claim_type"] == "comparison"
        assert set(direct[0]["paper_ids"]) == set(docs) and len(direct[0]["evidence_ids"]) == 2
        compiled = {s["section"]: s["items"] for s in report["compiled_answer"]}
        assert compiled["synthesis"][0]["claim_ids"] == [direct[0]["claim_id"]]
        assert compiled["synthesis"][0]["evidence_ids"] == direct[0]["evidence_ids"]
        direct[0]["statement"] = "The first model wins on every test."
        rebuilt = {s["section"]: s["items"] for s in compile_answer(report)}
        assert not rebuilt["synthesis"]
    else:
        assert not next(s for s in report["compiled_answer"] if s["section"] == "synthesis")["items"]


def test_overview_prioritizes_a_source_stated_open_question(tmp_path):
    limitation = "In future work, we plan to test whether the estimator generalizes to coastal sites."
    docs = {
        "a": {"paper_id": "a", "title": "Interior sites", "abstract": "We use regression to estimate canopy cover.",
              "fulltext": "Background observations. " * 80 + limitation},
        "b": {"paper_id": "b", "title": "Solid cover", "abstract": "We use field measurements to assess cover.",
              "fulltext": "Prior work asked whether wheat species are affected."},
    }
    report = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs), docs,
                     "test:v8:body-limit", tmp_path, "E11", pra_arm="G")["report"]
    claims = {c["claim_id"]: c for c in report["claims"]}
    limits = {f["paper_ids"][0]: report["answerability"]["fields"][f["field_id"]]
              for q in report["field_requirements"] for f in q["fields"] if f["facet"] == "limitations"}
    assert limits["a"]["status"] == "answerable"
    assert limits["b"]["status"] != "answerable"
    assert {claims[b["claim_id"]]["statement"] for b in limits["a"]["bindings"]} == {limitation}
    assert report["status"] == "partial"


def test_object_words_and_requested_analysis_have_separate_roles():
    from backend.research.descriptive_plan import anchored
    from backend.research.research_intent import research_intent

    goal = "Compare selecting records with price changes over time. Give the unit of analysis and objective for each."
    assert research_intent(goal, descriptive_subjects=True) == "description"
    assert research_intent(goal + " Analyze the trends over time.", descriptive_subjects=True) == "trend_analysis"
    assert research_intent("Which module yields the largest gain compared with other methods?",
                           descriptive_subjects=True) == "performance_ranking"
    assert research_intent("How does this result compare to other methods on the benchmark?",
                           descriptive_subjects=True) == "performance_ranking"
    assert research_intent("实验结果与其他方法相比如何？",
                           descriptive_subjects=True) == "performance_ranking"
    assert research_intent("How does this method compare to other methods?",
                           descriptive_subjects=True) == "method_comparison"
    assert research_intent("Compare the methods in “Which model gives the most speedup?”.",
                           descriptive_subjects=True) == "method_comparison"
    c = SimpleNamespace(statement="We examine record selection.", evidence_ids=["e"])
    assert anchored("selecting records", c, {"e": {"paper_title": "Study"}}, frames=True)
    assert not anchored("selecting documents", c, {"e": {"paper_title": "Study"}}, frames=True)


def test_compiled_report_keeps_source_checked_premises_without_promoting_the_comparison():
    sentence = "Our simulations reduced delivery delays by 16%."
    source = {"evidence_id": "e1", "paper_id": "p1", "paper_title": "Routing", "quote": sentence,
              "corpus_generation": "g1", "locator": "abstract:chars:0-47"}
    claim = {"claim_id": "c1", "paper_ids": ["p1"], "evidence_ids": ["e1"],
             "support_status": "verified", "statement": sentence}
    binding = {"claim_id": "c1", "evidence_id": "e1", "verification_status": "verified", "source_version": "g1"}
    report = {
        "answerability": {"fields": {"observed": {"status": "answerable", "bindings": [binding]},
                                     "relation": {"status": "not_comparable", "reason": "conditions_mismatch"}}},
        "sources": [source], "claims": [claim], "sections": {"verified": []},
        "answer_groups": {"background": ["c1"]},
        "field_requirements": [{"fields": [{"field_id": "observed", "facet": "finding"},
                                          {"field_id": "relation", "request": "Compare both methods"}]}],
        "method_relations": [{"level": "derived_synthesis", "premise_claim_ids": ["c1"], "evidence_ids": ["e1"],
                              "paper_ids": ["p1"], "kind": "shared_method", "statement": "Unlicensed relation."}],
    }
    compiled = compile_answer(report)
    sections = {section["section"]: section["items"] for section in compiled}
    assert [(item["kind"], item["text"], item["evidence_ids"]) for item in sections["papers"]] == [
        ("premise", sentence, ["e1"]),
    ]
    assert sentence in markdown(compiled, str) and "已核验前提" in markdown(compiled, str)
    assert sections["gaps"] and sections["references"]
    assert not sections["summary"] and not sections["relations"] and not sections["synthesis"]
    binding["source_version"] = "stale"
    assert not next(section for section in compile_answer(report) if section["section"] == "papers")["items"]


@pytest.mark.parametrize(("left", "right", "relation"), [
    ("We use logistic regression for forecasting.", "We use linear regression for forecasting.", "shared_method_family"),
    ("We use BM25 for document retrieval.", "We use BERT for document retrieval.", "different_methods_for_task"),
    ("We use dynamic programming for scheduling.", "我们使用动态规划用于分配资源。", "shared_method"),
    ("We find that yield increases under dry conditions.", "We find that yield decreases under dry conditions.", "different_directions"),
    ("We find that yield increases under dry conditions.", "We find that yield decreases under wet conditions.", None),
    ("We use dynamic programming for scheduling.", "Previous studies used dynamic programming for scheduling.", None),
])
def test_compiled_relations_preserve_scope_and_experimental_conditions(tmp_path, left, right, relation):
    docs = {k: {"paper_id": k, "title": k, "abstract": v} for k, v in (("A", left), ("B", right))}
    r = execute("综合这组论文各自的方法、主要结果和仍待解决的问题。", list(docs), docs,
                "test:v8:overview", tmp_path, "E11", pra_arm="G")["report"]
    derived = [x for x in r["overview"]["findings"] if x["level"] == "derived_synthesis"]
    if relation:
        assert any(x["kind"] == relation and set(x["paper_ids"]) == set(docs) for x in derived)
    else:
        assert not derived
    assert not any(x["kind"] == "causal" for x in derived)
    direct = set(r["sections"]["verified"])
    for claim in r["claims"]:
        if claim["claim_id"] in direct:
            assert len(claim["paper_ids"]) == 1
            assert claim["statement"] in docs[claim["paper_ids"][0]]["abstract"]


def test_cross_window_method_is_read_back_and_withdrawn_with_removed_source(tmp_path):
    first = "Using Monte Carlo simulations, we examined lattice fluctuations."
    second = "Using Monte Carlo simulations, we computed drift in daily temperature measurements."
    background = "Background observations. " * 34
    docs = {
        "a": {"paper_id": "a", "title": "Lattice", "abstract": first},
        "b": {"paper_id": "b", "title": "Temperature", "abstract": background + second},
        "c": {"paper_id": "c", "title": "Other", "abstract":
              "We develop a method that can be used in Monte Carlo simulations."},
    }
    goal = "Compare the methods used in these papers."
    def report(scope, path):
        trace = execute(goal, scope, {pid: docs[pid] for pid in scope}, "fixture:instrument",
                        tmp_path / path, "E11", pra_arm="G")
        return trace["report"]

    r = report(["a", "b", "c"], "with-both")
    relation, = [x for x in r["method_relations"] if x["kind"] == "shared_method"]
    assert relation["scope"] == "subset" and relation["paper_ids"] == ["a", "b"]
    source = next(x for x in r["sources"] if x["paper_id"] == "b" and second in x["quote"])
    assert source["locator"] == f"abstract:chars:0-{len(docs['b']['abstract'])}"
    assert source["quote"] == docs["b"]["abstract"]
    assert sha256(source["quote"].encode()).hexdigest() == source["quote_hash"]
    assert not [x for x in report(["b", "c"], "without-a")["method_relations"]
                if x["kind"] == "shared_method"]
