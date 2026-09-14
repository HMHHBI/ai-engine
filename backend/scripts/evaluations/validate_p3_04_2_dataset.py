#!/usr/bin/env python3
"""
Validate the P3-04.2 RAG retrieval golden dataset against the seeded chunk manifest.

Usage:
    python3 scripts/evaluations/validate_p3_04_2_dataset.py

Optional final-gate check:
    python3 scripts/evaluations/validate_p3_04_2_dataset.py --require-five-docs
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_DATASET = (
    Path(__file__).resolve().parent / "rag_quality_dataset_p3_04_v2.json"
)
DEFAULT_MANIFEST = (
    Path(__file__).resolve().parent
    / "retrieval_quality_chunk_manifest.json"
)

ALLOWED_QUERY_TYPES = {
    "semantic",
    "exact_term",
    "identifier",
    "numeric",
    "abbreviation",
    "multi_hop",
}

EXPECTED_TOTAL = 120
EXPECTED_TYPE_COUNTS = {
    "semantic": 30,
    "exact_term": 20,
    "identifier": 20,
    "numeric": 15,
    "abbreviation": 15,
    "multi_hop": 20,
}
EXPECTED_DOCUMENT_COUNT = 5


class ValidationError(Exception):
    """Raised when the golden dataset violates an evaluation invariant."""


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"Missing file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"Expected JSON object: {path}")
    return value


def build_manifest_index(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValidationError("Manifest must contain a non-empty 'documents' list.")

    chunks_by_id: dict[int, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValidationError("Every manifest document must be an object.")

        document_key = document.get("document_key")
        document_id = document.get("document_id")
        chunks = document.get("chunks")

        if not isinstance(document_key, str) or not document_key:
            raise ValidationError("Every manifest document needs document_key.")
        if not isinstance(document_id, int):
            raise ValidationError(
                f"{document_key}: document_id must be an integer."
            )
        if not isinstance(chunks, list) or not chunks:
            raise ValidationError(
                f"{document_key}: chunks must be a non-empty list."
            )

        expected_indexes = list(range(len(chunks)))
        actual_indexes = [chunk.get("chunk_index") for chunk in chunks]
        if actual_indexes != expected_indexes:
            raise ValidationError(
                f"{document_key}: chunk indexes are not exactly "
                f"0..{len(chunks) - 1}."
            )

        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise ValidationError(
                    f"{document_key}: every chunk must be an object."
                )

            chunk_id = chunk.get("chunk_id")
            if not isinstance(chunk_id, int):
                raise ValidationError(
                    f"{document_key}: chunk_id must be an integer."
                )
            if chunk_id in chunks_by_id:
                raise ValidationError(
                    f"Duplicate manifest chunk_id: {chunk_id}"
                )
            if chunk.get("document_id") != document_id:
                raise ValidationError(
                    f"Chunk {chunk_id}: document_id does not match its parent."
                )
            if chunk.get("chat_id") != document.get("chat_id"):
                raise ValidationError(
                    f"Chunk {chunk_id}: chat_id does not match its parent."
                )
            content = chunk.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValidationError(
                    f"Chunk {chunk_id}: content must be non-empty."
                )
            if len(content) > 500:
                raise ValidationError(
                    f"Chunk {chunk_id}: content exceeds 500 characters."
                )

            chunks_by_id[chunk_id] = {
                **chunk,
                "document_key": document_key,
            }

    return chunks_by_id


def validate_dataset(
    dataset: dict[str, Any],
    chunks_by_id: dict[int, dict[str, Any]],
    ) -> list[str]:
    errors: list[str] = []

    if dataset.get("version") != "2.0":
        errors.append("Dataset version must be 2.0.")

    queries = dataset.get("queries")
    if not isinstance(queries, list):
        errors.append("Dataset must contain a 'queries' list.")
        return errors

    if len(queries) != EXPECTED_TOTAL:
        errors.append(
            f"Expected exactly {EXPECTED_TOTAL} queries; got {len(queries)}."
        )

    seen_query_ids: set[str] = set()
    type_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()

    manifest_document_keys = {
        chunk["document_key"] for chunk in chunks_by_id.values()
    }

    dataset_documents = dataset.get("corpus", {}).get("documents", [])
    dataset_document_keys = {
        item.get("document_key")
        for item in dataset_documents
        if isinstance(item, dict)
    }

    if dataset_document_keys != manifest_document_keys:
        errors.append(
            "Dataset corpus document keys must exactly match manifest document keys."
        )

    if len(manifest_document_keys) != EXPECTED_DOCUMENT_COUNT:
        errors.append(
            f"Expected exactly {EXPECTED_DOCUMENT_COUNT} manifest documents; "
            f"found {len(manifest_document_keys)}."
        )

    for index, item in enumerate(queries, start=1):
        prefix = f"queries[{index}]"

        if not isinstance(item, dict):
            errors.append(f"{prefix}: query must be an object.")
            continue

        query_id = item.get("query_id")
        query_type = item.get("query_type")
        document_key = item.get("document_key")
        user_id = item.get("user_id")
        document_id = item.get("document_id")
        query = item.get("query")
        relevant_ids = item.get("relevant_chunk_ids")

        if not isinstance(query_id, str) or not query_id:
            errors.append(f"{prefix}: missing query_id.")
        elif query_id in seen_query_ids:
            errors.append(f"{prefix}: duplicate query_id '{query_id}'.")
        else:
            seen_query_ids.add(query_id)

        if query_type not in ALLOWED_QUERY_TYPES:
            errors.append(
                f"{prefix}: invalid query_type '{query_type}'."
            )
        else:
            type_counts[query_type] += 1

        if not isinstance(document_key, str) or not document_key:
            errors.append(f"{prefix}: missing document_key.")
        else:
            document_counts[document_key] += 1
            if document_key not in manifest_document_keys:
                errors.append(
                    f"{prefix}: unknown document_key '{document_key}'."
                )

        if user_id != 1:
            errors.append(f"{prefix}: user_id must be 1 for this isolated corpus.")

        if not isinstance(document_id, int):
            errors.append(f"{prefix}: document_id must be an integer.")

        if not isinstance(query, str) or not query.strip():
            errors.append(f"{prefix}: query must be non-empty.")

        if not isinstance(relevant_ids, list) or not relevant_ids:
            errors.append(
                f"{prefix}: relevant_chunk_ids must be a non-empty list."
            )
            continue

        if len(relevant_ids) != len(set(relevant_ids)):
            errors.append(f"{prefix}: duplicate relevant_chunk_ids.")

        if query_type == "multi_hop" and len(relevant_ids) < 2:
            errors.append(
                f"{prefix}: multi_hop query must reference at least two chunks."
            )

        for chunk_id in relevant_ids:
            if not isinstance(chunk_id, int):
                errors.append(
                    f"{prefix}: relevant chunk ID must be an integer."
                )
                continue

            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                errors.append(
                    f"{prefix}: orphan relevant_chunk_id {chunk_id}."
                )
                continue

            if chunk["document_key"] != document_key:
                errors.append(
                    f"{prefix}: cross-document label: chunk {chunk_id} "
                    f"belongs to {chunk['document_key']}."
                )

            if chunk["document_id"] != document_id:
                errors.append(
                    f"{prefix}: chunk {chunk_id} does not belong to "
                    f"document_id {document_id}."
                )

    if type_counts != Counter(EXPECTED_TYPE_COUNTS):
        errors.append(
            "Query-type distribution mismatch: "
            f"expected {EXPECTED_TYPE_COUNTS}, got {dict(type_counts)}."
        )

    expected_document_total = 24
    for document_key in sorted(manifest_document_keys):
        if document_counts[document_key] != expected_document_total:
            errors.append(
                f"{document_key}: expected {expected_document_total} queries; "
                f"got {document_counts[document_key]}."
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    try:
        dataset = load_json(args.dataset)
        manifest = load_json(args.manifest)
        chunks_by_id = build_manifest_index(manifest)
        errors = validate_dataset(
            dataset,
            chunks_by_id,
            
        )
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        return 1

    if errors:
        print("=" * 72)
        print("P3-04.2 GOLDEN DATASET VALIDATION: FAIL")
        print("=" * 72)
        for error in errors:
            print(f"- {error}")
        return 1

    query_count = len(dataset["queries"])
    type_counts = Counter(item["query_type"] for item in dataset["queries"])
    document_keys = sorted(
        {item["document_key"] for item in dataset["queries"]}
    )

    print("=" * 72)
    print("P3-04.2 GOLDEN DATASET VALIDATION: PASS")
    print("=" * 72)
    print(f"Dataset:          {args.dataset}")
    print(f"Manifest:         {args.manifest}")
    print(f"Queries:           {query_count}")
    print(f"Documents:         {len(document_keys)}")
    print(f"Query types:       {dict(type_counts)}")
    print("Orphan labels:     0")
    print("Cross-doc labels:  0")
    print("Duplicate IDs:     0")
    print("Chunk >500 chars:  0")
    print("=" * 72)

    if len(document_keys) == 4:
        print(
            "NOTE: Dataset validation passes for the currently seeded "
            "four-document corpus."
        )
        print(
            "FINAL GATE: add production_rag_spec.pdf to the isolated corpus, "
            "regenerate the manifest, and extend the dataset to five documents "
            "before declaring P3-04.2 closed."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
