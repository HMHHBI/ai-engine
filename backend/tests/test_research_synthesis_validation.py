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
        "C3": {
            "citation_id": "C3",
            "document_id": 30,
            "filename": "report-c.pdf",
            "chunk_id": 303,
            "page_number": 5,
            "excerpt": "Evaluation on benchmark.",
        },
    }


def response(answer, citations):
    return json.dumps({
        "answer": answer,
        "citations": citations,
    })


def facet_response(facets, citations):
    return json.dumps({
        "facets": facets,
        "citations": citations,
    })


def valid_facets_dict():
    return {
        "methodology": "Method A vs Method B [C1].",
        "datasets": "Trained on ImageNet [C2].",
        "metrics": "Evaluated on F1 score [C1].",
        "findings": "Significant gain observed [C1] [C2].",
        "limitations": "Tested on small batch only [C3].",
    }


def test_accepts_matching_citations_legacy_answer(citation_lookup):
    result = _validate_model_response(
        response("Revenue increased [C1].", ["C1"]),
        citation_lookup,
    )
    assert result["answer"] == "Revenue increased [C1]."
    assert [c["citation_id"] for c in result["citations"]] == ["C1"]


def test_accepts_structured_facets(citation_lookup):
    facets = valid_facets_dict()
    result = _validate_model_response(
        facet_response(facets, ["C1", "C2", "C3"]),
        citation_lookup,
    )
    assert "facets" in result
    assert result["facets"]["methodology"] == "Method A vs Method B [C1]."
    assert result["facets"]["limitations"] == "Tested on small batch only [C3]."
    assert [c["citation_id"] for c in result["citations"]] == ["C1", "C2", "C3"]
    # Check that composite answer is generated
    assert "## Methodology" in result["answer"]
    assert "## Limitations" in result["answer"]


def test_rejects_missing_required_facet(citation_lookup):
    facets = valid_facets_dict()
    del facets["limitations"]
    with pytest.raises(SynthesisValidationError, match="Missing required facet"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2"]),
            citation_lookup,
        )


def test_rejects_empty_facet_value(citation_lookup):
    facets = valid_facets_dict()
    facets["metrics"] = "   "
    with pytest.raises(SynthesisValidationError, match="must be a non-empty string"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2", "C3"]),
            citation_lookup,
        )


def test_rejects_facet_citation_not_in_array(citation_lookup):
    facets = valid_facets_dict()
    # Omits C3 from citations array
    with pytest.raises(SynthesisValidationError, match="do not match"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2"]),
            citation_lookup,
        )


def test_rejects_facet_citation_unknown(citation_lookup):
    facets = valid_facets_dict()
    facets["findings"] = "Claim with unknown source [C99]."
    with pytest.raises(SynthesisValidationError, match="does not reference retrieved evidence"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2", "C3", "C99"]),
            citation_lookup,
        )


@pytest.mark.parametrize(
    ("answer", "citations"),
    [
        ("Claim supported by [C999].", ["C999"]),
        ("Claim supported by [C1].", []),
        ("Claim supported by [C1].", ["C1", "C2"]),
        ("Claim supported by [C1].", ["C1", "C1"]),
        ("Claim supported by [C0].", ["C0"]),
        ("Claim supported by [C-1].", ["C-1"]),
        ("Claim supported by [C1a].", ["C1a"]),
        ("Claim supported by [ C1 ].", ["C1"]),
        ("Claim supported by [C1, C2].", ["C1", "C2"]),
    ],
)
def test_rejects_invalid_citation_scenarios(citation_lookup, answer, citations):
    with pytest.raises(SynthesisValidationError):
        _validate_model_response(response(answer, citations), citation_lookup)


def test_accepts_insufficient_evidence_without_citations(citation_lookup):
    result = _validate_model_response(
        response(
            "Insufficient evidence: the provided documents do not contain data on this topic.",
            [],
        ),
        citation_lookup,
    )
    assert result["citations"] == []
