"""
Unit tests for research synthesis evaluation harness and metrics (Phase 2A).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.evaluations.research_synthesis_eval import (
    DatasetValidationError,
    PredictionValidationError,
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
                "selected_document_keys": ["paper-a", "paper-b"],
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
                    {
                        "document_key": "paper-unselected",
                        "fixture": "fixtures/c.pdf",
                        "relevant_passage_ids": ["p-c-1"],
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
    with pytest.raises(DatasetValidationError, match="at least 30 cases"):
        validate_dataset({"schema_version": "1.0", "cases": []})


def test_validate_dataset_rejects_duplicate_case_ids(valid_dataset_payload):
    dup = dict(valid_dataset_payload["cases"][0])
    valid_dataset_payload["cases"].append(dup)
    with pytest.raises(DatasetValidationError, match="Duplicate case_id detected"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_dataset_rejects_unknown_claim_document(valid_dataset_payload):
    valid_dataset_payload["cases"][0]["claims"][0]["expected_document_keys"] = ["nonexistent-paper"]
    with pytest.raises(DatasetValidationError, match="expects unknown document_key"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_dataset_rejects_duplicate_passage_ids(valid_dataset_payload):
    valid_dataset_payload["cases"][0]["documents"][1]["relevant_passage_ids"] = ["p-a-1"]
    with pytest.raises(DatasetValidationError, match="duplicate passage_id"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_calculate_retrieval_metrics_exact_math():
    retrieved = ["p1", "p2", "p3", "p4", "p5", "p6"]
    relevant = ["p3", "p7"]

    recall_at_5, mrr = calculate_retrieval_metrics(retrieved, relevant)
    assert recall_at_5 == 0.5  # 1 hit ('p3') out of 2 relevant passages
    assert mrr == pytest.approx(1.0 / 3.0)  # First hit is at rank 3


def test_calculate_retrieval_metrics_empty_relevant_answerable():
    # An answerable case with empty gold passages must NOT receive 1.0
    recall_at_5, mrr = calculate_retrieval_metrics(["p1"], [], is_unanswerable=False)
    assert recall_at_5 == 0.0
    assert mrr == 0.0


def test_calculate_retrieval_metrics_empty_relevant_unanswerable():
    # An unanswerable case correctly expects empty gold passages
    recall_at_5, mrr = calculate_retrieval_metrics(["p1"], [], is_unanswerable=True)
    assert recall_at_5 == 1.0
    assert mrr == 1.0


def test_score_case_synthesis_detects_passage_ownership_mismatch(valid_dataset_payload):
    # Passage p-b-1 belongs to paper-b, but cited under paper-a
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {
                "document_key": "paper-a",
                "passage_id": "p-b-1",
                "page_number": 1,
                "chunk_id": 1,
            }
        ],
        "predicted_claims": [],
    }
    result = score_case_synthesis(case, candidate)
    assert result.source_identity_accuracy == 0.0
    assert any("Passage ownership mismatch" in e for e in result.errors)


def test_score_case_synthesis_detects_unselected_source_leakage(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {
                "document_key": "paper-unselected",
                "passage_id": "p-c-1",
                "page_number": 1,
                "chunk_id": 99,
            }
        ],
        "predicted_claims": [],
    }
    result = score_case_synthesis(case, candidate)
    assert result.unselected_source_leakage is True
    assert result.passed is False


def test_score_case_synthesis_rejects_extra_facet_keys(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {
            "methodology": "m",
            "datasets": "d",
            "metrics": "met",
            "findings": "f",
            "limitations": "l",
            "extra_unexpected_facet": "invalid",
        },
        "citations": [],
        "predicted_claims": [],
    }
    result = score_case_synthesis(case, candidate)
    assert result.facet_conformance == 0.0
    assert any("Unexpected extra facets" in e for e in result.errors)


def test_score_case_synthesis_claim_linked_precision_and_unsupported(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {"document_key": "paper-a", "passage_id": "p-a-1", "page_number": 1, "chunk_id": 1}
        ],
        "predicted_claims": [
            {
                "claim_id": "claim-1",
                "citations": [
                    {"document_key": "paper-a", "passage_id": "p-a-1"}
                ],
            },
            {
                "claim_id": "claim-unsupported",
                "citations": [],
            },
        ],
    }
    result = score_case_synthesis(case, candidate)
    assert result.citation_precision == 1.0
    assert result.citation_coverage == 1.0
    assert result.unsupported_claim_rate == 0.5  # 1 out of 2 predicted claims is unsupported


def test_evaluate_dataset_benchmark_rejects_missing_prediction(valid_dataset_payload):
    with pytest.raises(PredictionValidationError, match="Missing prediction"):
        evaluate_dataset_benchmark(valid_dataset_payload, candidate_responses={}, min_cases=1)


def test_evaluate_dataset_benchmark_fails_threshold_and_detects_exit_code(valid_dataset_payload, tmp_path):
    case = valid_dataset_payload["cases"][0]
    # Prediction that completely fails retrieval and coverage
    failing_predictions = {
        "case-001": {
            "retrieved_passage_ids": ["irrelevant-p"],
            "facets": {f: "content" for f in case["required_facets"]},
            "citations": [],
            "predicted_claims": [
                {"claim_id": "claim-1", "citations": []}
            ],
        }
    }
    summary = evaluate_dataset_benchmark(
        valid_dataset_payload,
        candidate_responses=failing_predictions,
        min_cases=1,
    )
    assert summary.all_passed is False
    assert summary.threshold_results["evidence_recall_at_5"]["passed"] is False
    assert summary.threshold_results["citation_coverage"]["passed"] is False


def test_cli_validate_only_mode(tmp_path, monkeypatch):
    import sys
    from scripts.evaluations.research_synthesis_eval import main

    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_text(json.dumps({
        "schema_version": "1.0",
        "dataset_id": "cli-test",
        "cases": [
            {
                "case_id": "c1",
                "question": "q",
                "selected_document_keys": ["d1"],
                "documents": [
                    {"document_key": "d1", "relevant_passage_ids": ["p1"]},
                    {"document_key": "d2", "relevant_passage_ids": ["p2"]},
                ],
                "required_facets": ["methodology"],
                "claims": [],
            }
        ]
    }))

    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file), "--validate-only", "--min-cases", "1"])
    # Should validate and return 0
    assert main() == 0
