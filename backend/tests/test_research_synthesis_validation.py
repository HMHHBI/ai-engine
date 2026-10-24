import json
from typing import Any

import pytest

from app.services.research_synthesis import (
    REQUIRED_FACETS,
    SynthesisValidationError,
    _validate_model_response,
)


@pytest.fixture
def citation_lookup() -> dict[str, dict[str, Any]]:
    return {
        "C1": {
            "citation_id": "C1",
            "document_id": 10,
            "filename": "report-a.pdf",
            "chunk_id": 101,
            "page_number": 3,
            "excerpt": "Evidence chunk 1",
        },
        "C2": {
            "citation_id": "C2",
            "document_id": 20,
            "filename": "report-b.pdf",
            "chunk_id": 202,
            "page_number": 4,
            "excerpt": "Evidence chunk 2",
        },
        "C3": {
            "citation_id": "C3",
            "document_id": 30,
            "filename": "report-c.pdf",
            "chunk_id": 303,
            "page_number": None,
            "excerpt": "Evidence chunk 3",
        },
    }


def response(answer: str, citations: list[str]) -> str:
    return json.dumps({"answer": answer, "citations": citations})


def facet_response(facets: dict[str, str], citations: list[str]) -> str:
    return json.dumps({"facets": facets, "citations": citations})


def valid_facets_dict() -> dict[str, str]:
    return {
        "methodology": "Comparative methodology overview [C1].",
        "datasets": "Evaluation on benchmark datasets [C2].",
        "metrics": "Reported accuracy and latency metrics [C3].",
        "findings": "Key consensus findings [C1] and distinctions [C2].",
        "limitations": "Acknowledged evaluation limitations [C3].",
    }


def test_rejects_legacy_answer_without_facets(citation_lookup):
    with pytest.raises(
        SynthesisValidationError,
        match="must contain all required facets",
    ):
        _validate_model_response(
            response("Revenue increased [C1].", ["C1"]),
            citation_lookup,
        )


def test_answer_is_generated_from_validated_facets(citation_lookup):
    payload = {
        "facets": valid_facets_dict(),
        "answer": "Unverified claim [C99].",
        "citations": ["C1", "C2", "C3"],
    }
    result = _validate_model_response(
        json.dumps(payload),
        citation_lookup,
    )
    assert "[C99]" not in result["answer"]
    assert "## Methodology" in result["answer"]
    assert result["facets"] == valid_facets_dict()


def test_accepts_structured_facets(citation_lookup):
    facets = valid_facets_dict()
    result = _validate_model_response(
        facet_response(facets, ["C1", "C2", "C3"]),
        citation_lookup,
    )
    assert result["facets"] == facets
    assert "## Methodology" in result["answer"]
    assert len(result["citations"]) == 3


def test_rejects_missing_required_facet(citation_lookup):
    facets = valid_facets_dict()
    del facets["limitations"]
    with pytest.raises(SynthesisValidationError, match="Missing required facet"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2", "C3"]),
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
    facets = valid_facets_dict()  # uses C1, C2, C3
    with pytest.raises(SynthesisValidationError, match="Inline citations and the citations array do not match"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2"]),  # C3 omitted from array
            citation_lookup,
        )


def test_rejects_facet_citation_unknown(citation_lookup):
    facets = valid_facets_dict()
    facets["limitations"] = "Limitations unsupported [C99]."
    with pytest.raises(SynthesisValidationError, match="citation that does not reference retrieved evidence"):
        _validate_model_response(
            facet_response(facets, ["C1", "C2", "C3", "C99"]),
            citation_lookup,
        )


@pytest.mark.parametrize(
    ("answer", "citations"),
    [
        ("Claim supported by [C999].", ["C999"]),
        ("Claim supported by [C1].", ["C1", "C2"]),
        ("Claim supported by [C1].", []),
        ("Claim supported by [C1].", ["C1", "C1"]),
        ("Claim supported by [C0].", ["C0"]),
        ("Claim supported by [C-1].", ["C-1"]),
        ("Claim supported by [C1a].", ["C1a"]),
        ("Claim supported by [ C1 ].", ["C1"]),
        ("Claim supported by [c1].", ["C1"]),
        ("Claim supported by [ c1 ].", ["C1"]),
        ("Claim supported by [C1, C2].", ["C1", "C2"]),
    ],
)
def test_rejects_invalid_citation_scenarios(answer: str, citations: list[str], citation_lookup):
    facets = {
        "methodology": answer,
        "datasets": "Dataset text [C1].",
        "metrics": "Metrics text [C1].",
        "findings": "Findings text [C1].",
        "limitations": "Limitations text [C1].",
    }
    with pytest.raises(SynthesisValidationError):
        _validate_model_response(facet_response(facets, citations), citation_lookup)


def test_accepts_insufficient_evidence_without_citations(citation_lookup):
    message = (
        "Insufficient evidence: the provided documents "
        "do not contain data on this topic."
    )
    facets = {
        "methodology": message,
        "datasets": message,
        "metrics": message,
        "findings": message,
        "limitations": message,
    }
    result = _validate_model_response(
        facet_response(facets, []),
        citation_lookup,
    )
    assert result["citations"] == []
    assert result["facets"] == facets
    assert "## Methodology" in result["answer"]
