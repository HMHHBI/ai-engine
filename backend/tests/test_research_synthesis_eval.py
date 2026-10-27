"""
Unit tests for research synthesis evaluation harness and metrics (Phase 2A).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.evaluations.research_synthesis_eval import (
    DatasetValidationError,
    calculate_retrieval_metrics,
    evaluate_dataset_benchmark,
    score_case_synthesis,
    validate_dataset,
    DEFAULT_THRESHOLDS,
)


@pytest.fixture
def valid_dataset_payload() -> dict:
    return {
        "schema_version": "1.0",
        "dataset_id": "test-dataset",
        "cases": [
            {
                "case_id": "case-001",
                "question": "Compare paper A and paper B.",
                "documents": [
                    {
                        "document_key": "paper-a",
                        "fixture": "fixtures/a.pdf",
                        "relevant_passage_ids": ["p-a-1"],
                    },
                    {
                        "document_key": "paper-b",
                        "fixture": "fixtures/b.pdf",
                        "relevant_passage_ids": ["p-b-1"],
                    },
                ],
                "required_facets": ["methodology", "datasets", "metrics", "findings", "limitations"],
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "expected_document_keys": ["paper-a"],
                        "expected_passage_ids": ["p-a-1"],
                    }
                ],
            }
        ],
    }


def test_validate_dataset_rejects_missing_cases():
    with pytest.raises(DatasetValidationError, match="non-empty 'cases' list"):
        validate_dataset({"schema_version": "1.0", "cases": []})


def test_validate_dataset_rejects_duplicate_case_ids(valid_dataset_payload):
    dup = dict(valid_dataset_payload["cases"][0])
    valid_dataset_payload["cases"].append(dup)
    with pytest.raises(DatasetValidationError, match="Duplicate case_id detected"):
        validate_dataset(valid_dataset_payload)


def test_validate_dataset_rejects_unknown_claim_document(valid_dataset_payload):
    valid_dataset_payload["cases"][0]["claims"][0]["expected_document_keys"] = ["nonexistent-paper"]
    with pytest.raises(DatasetValidationError, match="expects unknown document_key"):
        validate_dataset(valid_dataset_payload)


def test_calculate_retrieval_metrics_exact_math():
    retrieved = ["p1", "p2", "p3", "p4", "p5", "p6"]
    relevant = ["p3", "p7"]

    recall_at_5, mrr = calculate_retrieval_metrics(retrieved, relevant)
    assert recall_at_5 == 0.5  # 1 hit ('p3') out of 2 relevant passages
    assert mrr == pytest.approx(1.0 / 3.0)  # First hit is at rank 3


def test_calculate_retrieval_metrics_empty_relevant():
    recall_at_5, mrr = calculate_retrieval_metrics(["p1"], [])
    assert recall_at_5 == 1.0
    assert mrr == 1.0


def test_score_case_synthesis_detects_unselected_leakage(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {
            "methodology": "A",
            "datasets": "B",
            "metrics": "C",
            "findings": "D",
            "limitations": "E",
        },
        "citations": [
            {
                "document_key": "unauthorized-doc",
                "passage_id": "p-x-1",
                "page_number": 1,
                "chunk_id": 99,
            }
        ],
    }
    result = score_case_synthesis(case, candidate)
    assert result.unselected_source_leakage is True
    assert result.passed is False


def test_evaluate_dataset_benchmark_passes_for_ideal_candidate(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate_responses = {
        "case-001": {
            "retrieved_passage_ids": ["p-a-1", "p-b-1"],
            "facets": {
                "methodology": "Methodology details",
                "datasets": "Dataset details",
                "metrics": "Accuracy 95%",
                "findings": "Consistent gains",
                "limitations": "Small corpus",
            },
            "citations": [
                {
                    "document_key": "paper-a",
                    "passage_id": "p-a-1",
                    "page_number": 1,
                    "chunk_id": 1,
                }
            ],
            "limitations_or_uncertainty": "insufficient evidence noted where required",
        }
    }

    summary = evaluate_dataset_benchmark(valid_dataset_payload, candidate_responses)
    assert summary.all_passed is True
    assert summary.metrics["unselected_source_leakage_cases"] == 0
    assert summary.metrics["facet_contract_conformance"] == 1.0
    assert summary.metrics["citation_coverage"] == 1.0
    assert summary.metrics["citation_precision"] == 1.0
