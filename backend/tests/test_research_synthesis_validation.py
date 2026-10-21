import json
import pytest
from app.services.research_synthesis import (
    SynthesisValidationError,
    _validate_model_response,
)

@pytest.fixture
def citation_lookup():
    return {
        "C1": {
            "citation_id": "C1",
            "document_id": 10,
            "filename": "report-a.pdf",
            "chunk_id": 101,
            "page_number": 1,
            "excerpt": "Revenue increased.",
        },
        "C2": {
            "citation_id": "C2",
            "document_id": 20,
            "filename": "report-b.pdf",
            "chunk_id": 202,
            "page_number": 2,
            "excerpt": "Costs decreased.",
        },
    }

def response(answer, citations):
    return json.dumps({
        "answer": answer,
        "citations": citations,
    })

def test_accepts_matching_citations(citation_lookup):
    result = _validate_model_response(
        response("Revenue increased [C1].", ["C1"]),
        citation_lookup,
    )
    assert result["answer"] == "Revenue increased [C1]."
    assert [c["citation_id"] for c in result["citations"]] == ["C1"]

@pytest.mark.parametrize(
    ("answer", "citations"),
    [
        ("Claim supported by [C999].", ["C999"]),
        ("Claim supported by [C1].", []),
        ("Claim supported by [C1].", ["C1", "C2"]),
        ("Claim supported by [C1].", ["C1", "C1"]),
        ("Claim supported by [C0].", ["C0"]),
        ("Claim supported by [C1] and [C1, C2].", ["C1"]),
        ("Claim supported by [C1, C2].", ["C1", "C2"]),
    ],
)
def test_rejects_invalid_or_mismatched_citations(citation_lookup, answer, citations):
    with pytest.raises(SynthesisValidationError):
        _validate_model_response(response(answer, citations), citation_lookup)

def test_accepts_insufficient_evidence(citation_lookup):
    result = _validate_model_response(
        response("Insufficient evidence provided to answer.", []),
        citation_lookup,
    )
    assert result["citations"] == []
