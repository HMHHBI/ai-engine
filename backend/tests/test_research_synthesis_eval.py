"""
Unit tests for research synthesis evaluation harness and metrics (Phase 2A).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

from scripts.evaluations.research_synthesis_eval import (
    DatasetValidationError,
    PredictionValidationError,
    calculate_retrieval_metrics,
    evaluate_dataset_benchmark,
    main,
    score_case_synthesis,
    validate_dataset,
    validate_predictions_structure,
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
                "known_conflicts": ["Contradiction 1"],
                "unanswerable_questions": ["Question 1"],
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
        validate_dataset({"schema_version": "1.0", "dataset_id": "d", "cases": []})


def test_validate_dataset_rejects_missing_dataset_id():
    with pytest.raises(DatasetValidationError, match="non-empty string 'dataset_id'"):
        validate_dataset({"schema_version": "1.0", "cases": []}, min_cases=0)


def test_validate_dataset_rejects_duplicate_case_ids(valid_dataset_payload):
    dup = dict(valid_dataset_payload["cases"][0])
    valid_dataset_payload["cases"].append(dup)
    with pytest.raises(DatasetValidationError, match="Duplicate case_id detected"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_dataset_rejects_gold_claim_with_unselected_document(valid_dataset_payload):
    # claim expects paper-unselected, which is not in selected_document_keys
    valid_dataset_payload["cases"][0]["claims"][0]["expected_document_keys"] = ["paper-unselected"]
    with pytest.raises(DatasetValidationError, match="expects unselected document_key"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_dataset_rejects_duplicate_passage_ids(valid_dataset_payload):
    valid_dataset_payload["cases"][0]["documents"][1]["relevant_passage_ids"] = ["p-a-1"]
    with pytest.raises(DatasetValidationError, match="duplicate passage_id"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_dataset_rejects_duplicate_required_facets(valid_dataset_payload):
    valid_dataset_payload["cases"][0]["required_facets"] = ["methodology", "methodology"]
    with pytest.raises(DatasetValidationError, match="duplicate required_facet"):
        validate_dataset(valid_dataset_payload, min_cases=1)


def test_validate_predictions_structure_rejects_missing_and_extra_cases(valid_dataset_payload):
    # Missing case
    with pytest.raises(PredictionValidationError, match="Missing predictions for cases"):
        validate_predictions_structure({}, valid_dataset_payload["cases"])

    # Extra unexpected case
    preds = {
        "case-001": {},
        "case-unexpected": {},
    }
    with pytest.raises(PredictionValidationError, match="Extra unexpected prediction"):
        validate_predictions_structure(preds, valid_dataset_payload["cases"])


def test_calculate_retrieval_metrics_exact_math():
    retrieved = ["p1", "p2", "p3", "p4", "p5", "p6"]
    relevant = ["p3", "p7"]

    recall_at_5, mrr = calculate_retrieval_metrics(retrieved, relevant)
    assert recall_at_5 == 0.5
    assert mrr == pytest.approx(1.0 / 3.0)


def test_calculate_retrieval_metrics_empty_relevant():
    assert calculate_retrieval_metrics(["p1"], [], is_unanswerable=False) == (0.0, 0.0)
    assert calculate_retrieval_metrics(["p1"], [], is_unanswerable=True) == (1.0, 1.0)


def test_score_case_synthesis_detects_retrieval_leakage(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        # p-c-1 belongs to paper-unselected
        "retrieved_passage_ids": ["p-a-1", "p-c-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {"document_key": "paper-a", "passage_id": "p-a-1", "page_number": 1, "chunk_id": 1}
        ],
        "predicted_claims": [
            {
                "claim_id": "claim-1",
                "citations": [
                    {"document_key": "paper-a", "passage_id": "p-a-1"}
                ]
            }
        ],
    }
    result = score_case_synthesis(case, candidate)
    assert result.unselected_source_leakage is True
    assert result.passed is False
    assert any("belongs to unselected document" in e for e in result.errors)


def test_score_case_synthesis_detects_citation_discrepancy(valid_dataset_payload):
    case = valid_dataset_payload["cases"][0]
    candidate = {
        "retrieved_passage_ids": ["p-a-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        # Top level has paper-a, claim has paper-b
        "citations": [
            {"document_key": "paper-a", "passage_id": "p-a-1", "page_number": 1, "chunk_id": 1}
        ],
        "predicted_claims": [
            {
                "claim_id": "claim-1",
                "citations": [
                    {"document_key": "paper-b", "passage_id": "p-b-1"}
                ]
            }
        ],
    }
    result = score_case_synthesis(case, candidate)
    assert result.passed is False
    assert any("Inconsistency detected between top-level citations" in e for e in result.errors)


def test_cli_requires_mode_and_rejects_omitted_predictions(tmp_path, monkeypatch):
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

    # 1. No --predictions and no --validate-only -> exit 1
    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file)])
    assert main() == 1

    # 2. Both --predictions and --validate-only -> exit 1
    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file), "--validate-only", "--predictions", "dummy.json"])
    assert main() == 1

    # 3. Explicit --validate-only -> exit 0
    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file), "--validate-only", "--min-cases", "1"])
    assert main() == 0


def test_cli_returns_code_2_on_threshold_failure(tmp_path, monkeypatch):
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
                "claims": [
                    {"claim_id": "cl-1", "expected_document_keys": ["d1"], "expected_passage_ids": ["p1"]}
                ],
            }
        ]
    }))

    pred_file = tmp_path / "preds.json"
    # Zero citations, completely fails threshold
    pred_file.write_text(json.dumps({
        "c1": {
            "retrieved_passage_ids": [],
            "facets": {"methodology": "text"},
            "citations": [],
            "predicted_claims": [
                {"claim_id": "cl-1", "citations": []}
            ]
        }
    }))

    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file), "--predictions", str(pred_file), "--min-cases", "1"])
    assert main() == 2


def test_cli_returns_code_0_on_passing_predictions(tmp_path, monkeypatch):
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
                "claims": [
                    {"claim_id": "cl-1", "expected_document_keys": ["d1"], "expected_passage_ids": ["p1"]}
                ],
            }
        ]
    }))

    pred_file = tmp_path / "preds.json"
    pred_file.write_text(json.dumps({
        "c1": {
            "retrieved_passage_ids": ["p1"],
            "facets": {"methodology": "text"},
            "citations": [
                {"document_key": "d1", "passage_id": "p1", "page_number": 1, "chunk_id": 1}
            ],
            "predicted_claims": [
                {
                    "claim_id": "cl-1",
                    "citations": [
                        {"document_key": "d1", "passage_id": "p1"}
                    ]
                }
            ]
        }
    }))

    monkeypatch.setattr(sys, "argv", ["prog", "--dataset", str(dataset_file), "--predictions", str(pred_file), "--min-cases", "1"])
    assert main() == 0


def test_comparative_claim_coverage_requires_all_expected_documents(valid_dataset_payload):
    # Set up a comparative claim requiring evidence from both paper-a and paper-b
    case = valid_dataset_payload["cases"][0]
    case["claims"] = [
        {
            "claim_id": "comparative-claim",
            "expected_document_keys": ["paper-a", "paper-b"],
            "expected_passage_ids": ["p-a-1", "p-b-1"],
        }
    ]

    # Candidate cites only paper-a
    partial_candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {"document_key": "paper-a", "passage_id": "p-a-1", "page_number": 1, "chunk_id": 1}
        ],
        "predicted_claims": [
            {
                "claim_id": "comparative-claim",
                "citations": [
                    {"document_key": "paper-a", "passage_id": "p-a-1"}
                ]
            }
        ],
    }
    res_partial = score_case_synthesis(case, partial_candidate)
    # Must fail coverage because paper-b was not cited
    assert res_partial.citation_coverage == 0.0

    # Candidate cites both paper-a and paper-b
    complete_candidate = {
        "retrieved_passage_ids": ["p-a-1", "p-b-1"],
        "facets": {f: "content" for f in case["required_facets"]},
        "citations": [
            {"document_key": "paper-a", "passage_id": "p-a-1", "page_number": 1, "chunk_id": 1},
            {"document_key": "paper-b", "passage_id": "p-b-1", "page_number": 1, "chunk_id": 2},
        ],
        "predicted_claims": [
            {
                "claim_id": "comparative-claim",
                "citations": [
                    {"document_key": "paper-a", "passage_id": "p-a-1"},
                    {"document_key": "paper-b", "passage_id": "p-b-1"},
                ]
            }
        ],
    }
    res_complete = score_case_synthesis(case, complete_candidate)
    assert res_complete.citation_coverage == 1.0


def test_validate_predictions_rejects_malformed_nested_types(valid_dataset_payload):
    # Non-string retrieved passage ID
    bad_retrieval = {
        "case-001": {
            "retrieved_passage_ids": [123],
            "facets": {},
        }
    }
    with pytest.raises(PredictionValidationError, match="non-string retrieved_passage_id"):
        validate_predictions_structure(bad_retrieval, valid_dataset_payload["cases"])

    # Non-string citation document_key
    bad_cit_key = {
        "case-001": {
            "retrieved_passage_ids": ["p-a-1"],
            "citations": [{"document_key": 999, "passage_id": "p-a-1"}],
        }
    }
    with pytest.raises(PredictionValidationError, match="missing string 'document_key'"):
        validate_predictions_structure(bad_cit_key, valid_dataset_payload["cases"])


def test_validate_dataset_rejects_malformed_claim_nested_types(valid_dataset_payload):
    # Non-string expected_document_key in gold claim
    valid_dataset_payload["cases"][0]["claims"][0]["expected_document_keys"] = [12345]
    with pytest.raises(DatasetValidationError, match="non-string expected_document_key"):
        validate_dataset(valid_dataset_payload, min_cases=1)
