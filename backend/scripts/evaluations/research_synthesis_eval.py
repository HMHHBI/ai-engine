"""
Deterministic Research Synthesis & Citation Evaluator (Phase 2A / PR 1).

Evaluates structured multi-paper synthesis responses against versioned benchmark datasets.
Calculates deterministic retrieval and claim-linked citation faithfulness metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

STANDARD_FACETS = ("methodology", "datasets", "metrics", "findings", "limitations")

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


class PredictionValidationError(ValueError):
    """Raised when candidate predictions do not align with dataset specifications."""


def get_git_revision() -> str:
    """Resolve current git revision or CI commit SHA."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    try:
        output = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return output.decode("utf-8").strip()
    except Exception:
        return "unknown"


def validate_dataset(data: dict[str, Any], min_cases: int = 30) -> None:
    """Validate research synthesis dataset against the v1 specification."""
    if not isinstance(data, dict):
        raise DatasetValidationError("Dataset must be a JSON object.")

    if data.get("schema_version") != "1.0":
        raise DatasetValidationError(f"Unsupported schema_version: {data.get('schema_version')}")

    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) < min_cases:
        raise DatasetValidationError(f"Dataset must contain at least {min_cases} cases, found {len(cases) if isinstance(cases, list) else 0}.")

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
        if not question or not isinstance(question, str) or not question.strip():
            raise DatasetValidationError(f"Case {case_id} must have a non-empty string 'question'.")

        documents = case.get("documents")
        if not isinstance(documents, list) or len(documents) < 2:
            raise DatasetValidationError(f"Case {case_id} must have at least 2 documents.")

        selected_keys = case.get("selected_document_keys")
        if not isinstance(selected_keys, list) or len(selected_keys) < 1:
            raise DatasetValidationError(f"Case {case_id} must define non-empty 'selected_document_keys'.")

        doc_keys = set()
        seen_passages_in_case: set[str] = set()
        for doc in documents:
            if not isinstance(doc, dict):
                raise DatasetValidationError(f"Case {case_id} documents must be objects.")
            key = doc.get("document_key")
            if not key or not isinstance(key, str):
                raise DatasetValidationError(f"Case {case_id} has invalid document_key.")
            if key in doc_keys:
                raise DatasetValidationError(f"Case {case_id} has duplicate document_key: {key}")
            doc_keys.add(key)

            passages = doc.get("relevant_passage_ids", [])
            if not isinstance(passages, list):
                raise DatasetValidationError(f"Case {case_id} doc {key} relevant_passage_ids must be a list.")
            for p in passages:
                if not isinstance(p, str):
                    raise DatasetValidationError(f"Case {case_id} passage ID must be a string.")
                if p in seen_passages_in_case:
                    raise DatasetValidationError(f"Case {case_id} has duplicate passage_id: {p}")
                seen_passages_in_case.add(p)

        for sk in selected_keys:
            if sk not in doc_keys:
                raise DatasetValidationError(f"Case {case_id} selected_document_key '{sk}' not found in documents.")

        required_facets = case.get("required_facets")
        if not isinstance(required_facets, list) or not required_facets:
            raise DatasetValidationError(f"Case {case_id} must define a non-empty 'required_facets' list.")

        claims = case.get("claims", [])
        if not isinstance(claims, list):
            raise DatasetValidationError(f"Case {case_id} 'claims' must be a list.")

        seen_claim_ids = set()
        for claim in claims:
            cid = claim.get("claim_id")
            if not cid or not isinstance(cid, str):
                raise DatasetValidationError(f"Case {case_id} claim missing string 'claim_id'.")
            if cid in seen_claim_ids:
                raise DatasetValidationError(f"Case {case_id} duplicate claim_id: {cid}")
            seen_claim_ids.add(cid)

            exp_docs = claim.get("expected_document_keys", [])
            for ed in exp_docs:
                if ed not in doc_keys:
                    raise DatasetValidationError(f"Case {case_id} claim {cid} expects unknown document_key: {ed}")
            exp_passages = claim.get("expected_passage_ids", [])
            for ep in exp_passages:
                if ep not in seen_passages_in_case:
                    raise DatasetValidationError(f"Case {case_id} claim {cid} expects unknown passage_id: {ep}")


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
    git_revision: str
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
    is_unanswerable: bool = False,
) -> tuple[float, float]:
    """
    Calculate Evidence Recall@5 and MRR@10 deterministically.
    If no relevant passages exist on an answerable query, returns (0.0, 0.0).
    """
    if not relevant_passage_ids:
        if is_unanswerable:
            return 1.0, 1.0
        return 0.0, 0.0

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

    # 1. Document & Passage Ownership Mapping
    selected_doc_keys = set(case.get("selected_document_keys", []))
    passage_to_doc: dict[str, str] = {}
    selected_expected_passages: list[str] = []

    for doc in case["documents"]:
        d_key = doc["document_key"]
        for pid in doc.get("relevant_passage_ids", []):
            passage_to_doc[pid] = d_key
            if d_key in selected_doc_keys:
                selected_expected_passages.append(pid)

    is_unanswerable = len(case.get("unanswerable_questions", [])) > 0 and len(selected_expected_passages) == 0

    # 2. Retrieval Metrics
    retrieved_passages = candidate_result.get("retrieved_passage_ids", [])
    recall_at_5, mrr_at_10 = calculate_retrieval_metrics(
        retrieved_passages, selected_expected_passages, is_unanswerable=is_unanswerable
    )

    # 3. Facet Conformance (Must exactly match case required_facets with non-empty strings)
    facets = candidate_result.get("facets", {})
    required_facets = set(case.get("required_facets", []))
    provided_facets = set(facets.keys()) if isinstance(facets, dict) else set()

    missing_facets = required_facets - provided_facets
    extra_facets = provided_facets - required_facets
    invalid_content = any(not isinstance(facets.get(f), str) or not facets[f].strip() for f in required_facets)

    if missing_facets or extra_facets or invalid_content:
        facet_conformance = 0.0
        if missing_facets:
            errors.append(f"Missing facets: {sorted(missing_facets)}")
        if extra_facets:
            errors.append(f"Unexpected extra facets: {sorted(extra_facets)}")
        if invalid_content:
            errors.append("One or more required facets have empty or non-string values")
    else:
        facet_conformance = 1.0

    # 4. Citations, Ownership & Unselected-Source Leakage
    citations = candidate_result.get("citations", [])
    unselected_leakage = False
    valid_source_identities = 0

    for cit in citations:
        doc_key = cit.get("document_key")
        passage_id = cit.get("passage_id")

        # Check leakage against selected set
        if doc_key not in selected_doc_keys:
            unselected_leakage = True
            errors.append(f"Unselected source cited: {doc_key}")

        # Check passage ownership
        owner_doc = passage_to_doc.get(passage_id)
        if owner_doc and owner_doc != doc_key:
            errors.append(f"Passage ownership mismatch: {passage_id} belongs to {owner_doc}, cited under {doc_key}")
        elif (
            cit.get("page_number") is not None
            and cit.get("chunk_id") is not None
            and doc_key in selected_doc_keys
            and owner_doc == doc_key
        ):
            valid_source_identities += 1

    source_identity_accuracy = (
        valid_source_identities / len(citations) if citations else (1.0 if not unselected_leakage else 0.0)
    )

    # 5. Claim-Linked Citation Precision, Coverage, and Unsupported Claims
    gold_claims = {c["claim_id"]: c for c in case.get("claims", [])}
    predicted_claims = candidate_result.get("predicted_claims", [])

    total_citations = 0
    supported_citations = 0
    unsupported_pred_claims = 0

    for p_claim in predicted_claims:
        claim_id = p_claim.get("claim_id")
        claim_citations = p_claim.get("citations", [])
        total_citations += len(claim_citations)

        claim_supported = False
        gold_c = gold_claims.get(claim_id)
        if gold_c:
            expected_passages = set(gold_c.get("expected_passage_ids", []))
            for cit in claim_citations:
                c_pid = cit.get("passage_id")
                c_doc = cit.get("document_key")
                if c_pid in expected_passages and passage_to_doc.get(c_pid) == c_doc:
                    supported_citations += 1
                    claim_supported = True
        else:
            errors.append(f"Unknown predicted claim_id: {claim_id}")

        if not claim_supported:
            unsupported_pred_claims += 1

    citation_precision = (
        supported_citations / total_citations if total_citations > 0 else (1.0 if not predicted_claims else 0.0)
    )

    # Coverage: gold claims supported by predicted claims
    covered_gold_claims = 0
    for cid, gc in gold_claims.items():
        exp_p = set(gc.get("expected_passage_ids", []))
        for p_claim in predicted_claims:
            if p_claim.get("claim_id") == cid:
                for cit in p_claim.get("citations", []):
                    if cit.get("passage_id") in exp_p and passage_to_doc.get(cit.get("passage_id")) == cit.get("document_key"):
                        covered_gold_claims += 1
                        break

    citation_coverage = covered_gold_claims / len(gold_claims) if gold_claims else 1.0
    unsupported_claim_rate = (
        unsupported_pred_claims / len(predicted_claims) if predicted_claims else 0.0
    )

    # 6. Unanswerable Handling
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
    dataset_bytes: bytes | None = None,
    thresholds: dict[str, float] | None = None,
    min_cases: int = 30,
) -> BenchmarkSummary:
    """Evaluate entire benchmark dataset and produce a structured summary."""
    validate_dataset(dataset, min_cases=min_cases)
    active_thresholds = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        active_thresholds.update(thresholds)

    if dataset_bytes is not None:
        dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    else:
        raw_json = json.dumps(dataset, sort_keys=True)
        dataset_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    git_rev = get_git_revision()
    cases = dataset["cases"]
    results = []

    leakage_count = 0
    passed_cases = 0

    for case in cases:
        case_id = case["case_id"]
        candidate = candidate_responses.get(case_id)
        if candidate is None:
            raise PredictionValidationError(f"Missing prediction for dataset case_id: {case_id}")
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
        git_revision=git_rev,
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
        "--predictions",
        type=str,
        default=None,
        help="Path to predictions JSON file. If omitted, runs in validate-only mode.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the benchmark dataset without scoring predictions.",
    )
    parser.add_argument(
        "--min-cases",
        type=int,
        default=30,
        help="Minimum required cases in dataset (default: 30).",
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

    raw_bytes = dataset_path.read_bytes()
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
        validate_dataset(data, min_cases=args.min_cases)
    except Exception as exc:
        print(f"Dataset Validation Failed: {exc}", file=sys.stderr)
        return 1

    if args.validate_only or not args.predictions:
        print(f"Dataset '{data.get('dataset_id')}' validated successfully ({len(data.get('cases', []))} cases).")
        return 0

    pred_path = Path(args.predictions)
    if not pred_path.exists():
        print(f"Error: Predictions file not found at {pred_path}", file=sys.stderr)
        return 1

    try:
        predictions = json.loads(pred_path.read_text(encoding="utf-8"))
        summary = evaluate_dataset_benchmark(
            data,
            candidate_responses=predictions,
            dataset_bytes=raw_bytes,
            min_cases=args.min_cases,
        )
    except PredictionValidationError as exc:
        print(f"Prediction Validation Failed: {exc}", file=sys.stderr)
        return 1

    report = asdict(summary)
    print(f"Dataset ID: {summary.dataset_id} (hash: {summary.dataset_hash[:8]}...)")
    print(f"Revision: {summary.git_revision}")
    print(f"Total Cases: {summary.total_cases} | Passed: {summary.passed_cases}")
    print("Aggregate Metrics:")
    for k, v in summary.metrics.items():
        status = "✓" if summary.threshold_results[k]["passed"] else "✗"
        print(f"  [{status}] {k}: {v} (threshold: {summary.threshold_results[k]['target']})")

    if args.output:
        out_file = Path(args.output)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote report to {out_file}")

    return 0 if summary.all_passed else 2


if __name__ == "__main__":
    sys.exit(main())
