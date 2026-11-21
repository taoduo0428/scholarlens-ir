from hashlib import sha256

from backend.research.claim_verifier import new_claim
from backend.research.synthesis import judge


def test_authentic_quote_does_not_validate_wrong_value_or_dimension():
    quote = "The instrument recorded an accuracy of 82%."
    source = {"evidence_id": "e1", "paper_id": "p1", "quote": quote,
              "quote_hash": sha256(quote.encode()).hexdigest()}
    sources = {"e1": source}
    claim = new_claim("q1", "The instrument recorded an accuracy of 92%.", "fact", [source])
    verdict = judge(claim, [claim], sources, "What accuracy was recorded?")
    assert verdict["provenance_valid"] and verdict["semantic_support"] != "supported"
    direct = new_claim("q1", quote, "fact", [source])
    assert judge(direct, [direct], sources, "What voltage was measured?")["reason"] == "requested_dimension_missing"
    assert not judge(direct, [direct], {"e1": {**source, "quote": quote + "!"}}, "What accuracy?")["provenance_valid"]
