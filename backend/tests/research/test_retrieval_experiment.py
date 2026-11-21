import pytest

from tools.research_eval.retrieval_experiment import (
    check_identity,
    corpus,
    create_indices,
    near_recall,
)


def test_ann_recall_uses_exact_distinct_top_k():
    assert near_recall(["c", "b", "a"], ["a", "b", "c"], 2) == 0.5
    with pytest.raises(ValueError, match="different"):
        near_recall(["a"], ["a", "a"], 2)


def test_deterministic_bounded_corpus_contains_only_public_text():
    docs, sha = corpus(30)
    other_docs, other_sha = corpus(31)
    assert list(docs) == list(other_docs)[:30] and sha == other_sha
    assert all(k.startswith("source-sha256:") and d["abstract"] for k, d in docs.items())
    with pytest.raises(ValueError):
        corpus(0)


@pytest.mark.parametrize("wrong", ["cluster_uuid", "cluster_name", "version"])
def test_refuses_wrong_cluster_before_touching_indices(wrong):
    info = {
        "cluster_uuid": "u",
        "cluster_name": "scholarlens-local",
        "version": {"number": "8.19.23"},
    }
    info[wrong] = {"number": "7.0"} if wrong == "version" else "wrong"
    with pytest.raises(ValueError, match="identity"):
        check_identity(info, "u")


def test_existing_name_prevents_both_creates():
    class Occupied:
        def exists(self, *, index):
            return index.endswith("-ann")

        def create(self, **kwargs):
            raise AssertionError("unexpected write")

    class Fake:
        indices = Occupied()

        @staticmethod
        def info():
            return {
                "cluster_uuid": "u",
                "cluster_name": "scholarlens-local",
                "version": {"number": "8.19.23"},
            }

    with pytest.raises(ValueError, match="fresh"):
        create_indices(Fake(), "u", "evo-p2-00000000000000000000000000000000")
