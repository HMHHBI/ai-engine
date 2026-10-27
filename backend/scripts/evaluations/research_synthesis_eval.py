"""
Deterministic Research Synthesis & Citation Evaluator (Phase 2A / PR 1).

Evaluates structured multi-paper synthesis responses against versioned benchmark datasets.
Calculates deterministic retrieval and citation faithfulness metrics without requiring live LLM calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REQUIRED_FACETS = ("methodology", "datasets", "metrics", "findings", "limitations")

# Initial benchmark acceptance gates
DEFAULT_THRESHOLDS = {
    "evidence_recall_at_5": 0.80,
    "mrr_at_10": 0.70,
    "citation_precision": 0.90,
    "citation_coverage": 0.90,
    "unsupported_claim_rate": 0.05,
    "source_identity_accuracy": 1.00,
    "unselected_source_leakage_cases": 0,
    "facet_contract_conformance": 1.00,
    "unanswerable_case_behavior": 0.90,
}


class DatasetValidationError(ValueError):
    """Raised when the benchmark dataset fails structural validation."""


def validate_dataset(data: dict[str, Any]) -> None:
    """Validate research synthesis dataset against the v1 specification."""
    if not isinstance(data, dict):
        raise DatasetValidationError("Dataset must be a JSON object.")

    if data.get("schema_version") != "1.0":
        raise DatasetValidationError(f"Unsupported schema_version: {data.get('schema_version')}")

    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) == 0:
        raise DatasetValidationError("Dataset must contain a non-empty 'cases' list.")

    seen_case_ids: set[str] = set()

    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise DatasetValidationError(f"Case at index {idx} must be a JSON object.")

        case_id = case.get("case_id")
        if not case_id or not isinstance(case_id, str):
            raise DatasetValidationError(f"Case at index {idx} must have a valid non-empty 'case_id'.")

        if case_id in seen_case_ids:
            raise DatasetValidationError(f"Duplicate case_id detected: {case_id}")
        seen_case_ids.add(case_id)

        question = case.get("question")
        if not question or not isinstance(question, str):
            raise DatasetValidationError(f"Case {case_id} must have a non-empty 'question'.")

        documents = case.get("documents")
        if not isinstance(documents, list) or len(documents) < 2:
            raise DatasetValidationError(f"Case {case_id} must have at least 2 documents.")

        doc_keys = set()
        all_passage_ids = set()
        for doc in documents:
            key = doc.get("document_key")
            if not key or not isinstance(key, str):
                raise DatasetValidationError(f"Case {case_id} has invalid document_key.")
            if key in doc_keys:
                raise DatasetValidationError(f"Case {case_id} has duplicate document_key: {key}")
            doc_keys.add(key)

            passages = doc.get("relevant_passage_ids", [])
            for p in passages:
                all_passage_ids.add(p)

        claims = case.get("claims", [])
        for claim in claims:
            cid = claim.get("claim_id")
            if not cid:
                raise DatasetValidationError(f"Case {case_id} claim missing 'claim_id'.")
            exp_docs = claim.get("expected_document_keys", [])
            for ed in exp_docs:
                if ed not in doc_keys:
                    raise DatasetValidationError(f"Case {case_id} claim {cid} expects unknown document_key {ed}")
            exp_passages = claim.get("expected_passage_ids", [])
            for ep in exp_passages:
                if ep not in all_passage_ids:
                    raise DatasetValidationError(f"Case {case_id} claim {cid} expects unknown passage_id {ep}")


@dataclass
class CaseEvaluationResult:
    case_id: str
    passed: bool
    evidence_recall_at_5: float
    mrr_at_10: float
    citation_precision: float
    citation_coverage: float
    unsupported_claim_rate: float
    source_identity_accuracy: float
    unselected_source_leakage: bool
    facet_conformance: float
    unanswerable_handled: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class BenchmarkSummary:
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    total_cases: int
    evaluated_cases: int
    passed_cases: int
    metrics: dict[str, float]
    threshold_results: dict[str, dict[str, Any]]
    all_passed: bool
    case_results: list[dict[str, Any]] = field(default_factory=list)


def calculate_retrieval_metrics(
    retrieved_passage_ids: Sequence[str],
    relevant_passage_ids: Sequence[str],
) -> tuple[float, float]:
    """Calculate Evidence Recall@5 and MRR@10 deterministically."""
    if not relevant_passage_ids:
        return 1.0, 1.0

    relevant_set = set(relevant_passage_ids)
    top_5 = retrieved_passage_ids[:5]
    hits_in_5 = len([pid for pid in top_5 if pid in relevant_set])
    recall_at_5 = min(1.0, hits_in_5 / len(relevant_set))

    mrr = 0.0
    for rank, pid in enumerate(retrieved_passage_ids[:10], start=1):
        if pid in relevant_set:
            mrr = 1.0 / rank
            break

    return recall_at_5, mrr


def score_case_synthesis(
    case: dict[str, Any],
    candidate_result: dict[str, Any],
) -> CaseEvaluationResult:
    """Score a single candidate synthesis against the case specification."""
    case_id = case["case_id"]
    errors = []

    # 1. Documents & Passages Mapping
    allowed_doc_keys = {d["document_key"] for d in case["documents"]}
    all_expected_passages = [
        pid for doc in case["documents"] for pid in doc.get("relevant_passage_ids", [])
    ]

    retrieved_passages = candidate_result.get("retrieved_passage_ids", [])
    recall_at_5, mrr_at_10 = calculate_retrieval_metrics(retrieved_passages, all_expected_passages)

    # 2. Facet Conformance
    facets = candidate_result.get("facets", {})
    matched_facets = sum(
        1 for f in REQUIRED_FACETS if isinstance(facets.get(f), str) and len(facets[f].strip()) > 0
    )
    facet_conformance = matched_facets / len(REQUIRED_FACETS)
    if facet_conformance < 1.0:
        errors.append(f"Incomplete facets: {matched_facets}/{len(REQUIRED_FACETS)} present")

    # 3. Citations & Unselected-source leakage
    citations = candidate_result.get("citations", [])
    unselected_leakage = False
    valid_source_identities = 0

    for cit in citations:
        doc_key = cit.get("document_key")
        if doc_key not in allowed_doc_keys:
            unselected_leakage = True
            errors.append(f"Citation references unselected document: {doc_key}")
        if cit.get("page_number") is not None and cit.get("chunk_id") is not None:
            valid_source_identities += 1

    source_identity_accuracy = (
        valid_source_identities / len(citations) if citations else (1.0 if not unselected_leakage else 0.0)
    )

    # 4. Claims & Citation Precision / Coverage
    expected_claims = case.get("claims", [])
    verified_claims = 0
    supported_citations = 0

    cited_passage_keys = {
        cit.get("passage_id") for cit in citations if cit.get("passage_id")
    }

    for claim in expected_claims:
        exp_passages = set(claim.get("expected_passage_ids", []))
        if exp_passages and (exp_passages & cited_passage_keys):
            verified_claims += 1

    for cit in citations:
        passage_id = cit.get("passage_id")
        if passage_id and passage_id in all_expected_passages:
            supported_citations += 1

    citation_precision = (
        supported_citations / len(citations) if citations else 1.0
    )
    citation_coverage = (
        verified_claims / len(expected_claims) if expected_claims else 1.0
    )
    unsupported_claim_rate = max(0.0, 1.0 - citation_coverage)

    # 5. Unanswerable handling
    unanswerable_questions = case.get("unanswerable_questions", [])
    handled_unanswerable = True
    if unanswerable_questions:
        notes = candidate_result.get("limitations_or_uncertainty", "")
        handled_unanswerable = (
            any(q.lower() in notes.lower() for q in unanswerable_questions)
            or "insufficient evidence" in notes.lower()
            or "unreported" in notes.lower()
        )

    passed = (
        recall_at_5 >= DEFAULT_THRESHOLDS["evidence_recall_at_5"]
        and mrr_at_10 >= DEFAULT_THRESHOLDS["mrr_at_10"]
        and citation_precision >= DEFAULT_THRESHOLDS["citation_precision"]
        and citation_coverage >= DEFAULT_THRESHOLDS["citation_coverage"]
        and unsupported_claim_rate <= DEFAULT_THRESHOLDS["unsupported_claim_rate"]
        and source_identity_accuracy >= DEFAULT_THRESHOLDS["source_identity_accuracy"]
        and not unselected_leakage
        and facet_conformance >= DEFAULT_THRESHOLDS["facet_contract_conformance"]
        and handled_unanswerable
    )

    return CaseEvaluationResult(
        case_id=case_id,
        passed=passed,
        evidence_recall_at_5=recall_at_5,
        mrr_at_10=mrr_at_10,
        citation_precision=citation_precision,
        citation_coverage=citation_coverage,
        unsupported_claim_rate=unsupported_claim_rate,
        source_identity_accuracy=source_identity_accuracy,
        unselected_source_leakage=unselected_leakage,
        facet_conformance=facet_conformance,
        unanswerable_handled=handled_unanswerable,
        errors=errors,
    )


def evaluate_dataset_benchmark(
    dataset: dict[str, Any],
    candidate_responses: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> BenchmarkSummary:
    """Evaluate entire benchmark dataset and produce a structured summary."""
    validate_dataset(dataset)
    active_thresholds = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        active_thresholds.update(thresholds)

    raw_json = json.dumps(dataset, sort_keys=True)
    dataset_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    cases = dataset["cases"]
    results = []

    leakage_count = 0
    passed_cases = 0

    for case in cases:
        case_id = case["case_id"]
        candidate = candidate_responses.get(case_id, {})
        res = score_case_synthesis(case, candidate)
        results.append(res)
        if res.unselected_source_leakage:
            leakage_count += 1
        if res.passed:
            passed_cases += 1

    total = len(cases)
    avg_recall = sum(r.evidence_recall_at_5 for r in results) / total
    avg_mrr = sum(r.mrr_at_10 for r in results) / total
    avg_precision = sum(r.citation_precision for r in results) / total
    avg_coverage = sum(r.citation_coverage for r in results) / total
    avg_unsupported = sum(r.unsupported_claim_rate for r in results) / total
    avg_source_id = sum(r.source_identity_accuracy for r in results) / total
    avg_facet = sum(r.facet_conformance for r in results) / total
    avg_unanswerable = sum(1.0 if r.unanswerable_handled else 0.0 for r in results) / total

    metric_summary = {
        "evidence_recall_at_5": round(avg_recall, 4),
        "mrr_at_10": round(avg_mrr, 4),
        "citation_precision": round(avg_precision, 4),
        "citation_coverage": round(avg_coverage, 4),
        "unsupported_claim_rate": round(avg_unsupported, 4),
        "source_identity_accuracy": round(avg_source_id, 4),
        "unselected_source_leakage_cases": leakage_count,
        "facet_contract_conformance": round(avg_facet, 4),
        "unanswerable_case_behavior": round(avg_unanswerable, 4),
    }

    threshold_results = {}
    all_passed = True

    for metric_name, target in active_thresholds.items():
        val = metric_summary[metric_name]
        if metric_name in ("unsupported_claim_rate", "unselected_source_leakage_cases"):
            passed_gate = bool(val <= target)
        else:
            passed_gate = bool(val >= target)

        if not passed_gate:
            all_passed = False

        threshold_results[metric_name] = {
            "score": val,
            "target": target,
            "passed": passed_gate,
        }

    return BenchmarkSummary(
        dataset_id=dataset.get("dataset_id", "unknown"),
        dataset_version=dataset.get("schema_version", "1.0"),
        dataset_hash=dataset_hash,
        total_cases=total,
        evaluated_cases=len(results),
        passed_cases=passed_cases,
        metrics=metric_summary,
        threshold_results=threshold_results,
        all_passed=all_passed,
        case_results=[asdict(r) for r in results],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research synthesis evaluation benchmark.")
    parser.add_argument(
        "--dataset",
        type=str,
        default="scripts/evaluations/research_synthesis_dataset_v1.json",
        help="Path to the JSON benchmark dataset.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write the output JSON report.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}", file=sys.stderr)
        return 1

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        validate_dataset(data)
    except DatasetValidationError as exc:
        print(f"Dataset Validation Failed: {exc}", file=sys.stderr)
        return 1

    # Running offline contract evaluation
    summary = evaluate_dataset_benchmark(data, candidate_responses={})
    report = asdict(summary)

    print(f"Dataset ID: {summary.dataset_id} (hash: {summary.dataset_hash[:8]}...)")
    print(f"Total Cases: {summary.total_cases}")
    print("Aggregate Metrics:")
    for k, v in summary.metrics.items():
        print(f"  - {k}: {v}")

    if args.output:
        out_file = Path(args.output)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote report to {out_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
