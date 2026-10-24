from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

EXPORT_SCHEMA_VERSION = "1.0"


def _isoformat(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _citation_sort_key(citation: dict[str, Any]) -> tuple[int, int, int, str]:
    citation_id = str(citation.get("citation_id", ""))
    match = re.fullmatch(r"C([1-9][0-9]*)", citation_id)
    citation_number = int(match.group(1)) if match else 2**31 - 1

    try:
        document_id = int(citation.get("document_id", 0))
    except (TypeError, ValueError):
        document_id = 0

    try:
        chunk_id = int(citation.get("chunk_id", 0))
    except (TypeError, ValueError):
        chunk_id = 0

    return citation_number, document_id, chunk_id, citation_id


def _sanitize_filename_component(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip("-")
    return value[:64] or "workspace"


def research_export_filename(
    *,
    workspace_name: str,
    workspace_id: int,
    run_id: int,
    export_format: str,
) -> str:
    if export_format not in {"markdown", "json"}:
        raise ValueError("Unsupported research export format.")

    workspace_slug = _sanitize_filename_component(workspace_name)
    extension = "md" if export_format == "markdown" else "json"

    return (
        f"research-{workspace_slug}-workspace-{workspace_id}"
        f"-run-{run_id}.{extension}"
    )


def build_research_export_bundle(run: Any) -> dict[str, Any]:
    """
    Build a deterministic export bundle from a completed ResearchRun ORM object.

    The caller must load run.workspace and run.document_associations before
    calling this function.
    """
    if run.status != "completed":
        raise ValueError("Only completed research runs can be exported.")

    workspace = run.workspace
    if workspace is None:
        raise ValueError("The research run has no associated workspace.")

    stored_answer = run.answer or {}
    answer_text = stored_answer.get("answer")

    if not isinstance(answer_text, str) or not answer_text.strip():
        raise ValueError("The completed research run has no synthesized answer.")

    raw_citations = stored_answer.get("citations") or []
    if not isinstance(raw_citations, list):
        raise ValueError("The research run contains invalid citation data.")

    facets_data = stored_answer.get("facets")
    facets = facets_data if isinstance(facets_data, dict) else None

    associations = sorted(
        list(run.document_associations or []),
        key=lambda association: (
            int(association.document_id),
            int(association.id),
        ),
    )

    source_documents: list[dict[str, Any]] = []
    filename_by_document_id: dict[int, str] = {}

    for association in associations:
        document = association.document
        provenance = association.provenance or {}

        document_id = int(association.document_id)
        filename = (
            getattr(document, "filename", None)
            or provenance.get("filename")
            or f"document-{document_id}"
        )

        filename_by_document_id[document_id] = str(filename)

        candidate_chunks = provenance.get("candidate_chunks") or []
        if not isinstance(candidate_chunks, list):
            candidate_chunks = []

        normalized_chunks = []
        for chunk in candidate_chunks:
            if not isinstance(chunk, dict):
                continue

            try:
                chunk_id = int(chunk["chunk_id"])
            except (KeyError, TypeError, ValueError):
                continue

            page_number = chunk.get("page_number")
            try:
                page_number = int(page_number) if page_number is not None else None
            except (TypeError, ValueError):
                page_number = None

            score = chunk.get("score")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None

            normalized_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "page_number": page_number,
                    "score": score,
                }
            )

        normalized_chunks.sort(
            key=lambda chunk: (
                chunk["chunk_id"],
                chunk["page_number"] if chunk["page_number"] is not None else -1,
            )
        )

        source_documents.append(
            {
                "document_id": document_id,
                "filename": str(filename),
                "provenance": {
                    "candidate_chunks": normalized_chunks,
                    "citations": sorted(
                        [
                            item
                            for item in (provenance.get("citations") or [])
                            if isinstance(item, dict)
                        ],
                        key=_citation_sort_key,
                    ),
                },
                "association_created_at": _isoformat(
                    getattr(association, "created_at", None)
                ),
            }
        )

    source_documents.sort(
        key=lambda document: (
            document["document_id"],
            document["filename"].casefold(),
        )
    )

    bibliography: list[dict[str, Any]] = []
    seen_citation_ids: set[str] = set()

    for citation in sorted(
        [item for item in raw_citations if isinstance(item, dict)],
        key=_citation_sort_key,
    ):
        citation_id = str(citation.get("citation_id", "")).strip()
        if not citation_id or citation_id in seen_citation_ids:
            continue

        seen_citation_ids.add(citation_id)

        try:
            document_id = int(citation["document_id"])
            chunk_id = int(citation["chunk_id"])
        except (KeyError, TypeError, ValueError):
            continue

        page_number = citation.get("page_number")
        try:
            page_number = int(page_number) if page_number is not None else None
        except (TypeError, ValueError):
            page_number = None

        filename = (
            citation.get("filename")
            or filename_by_document_id.get(document_id)
            or f"document-{document_id}"
        )

        excerpt = citation.get("excerpt")
        if not isinstance(excerpt, str):
            excerpt = ""
        excerpt = excerpt.strip()

        bibliography.append(
            {
                "citation_id": citation_id,
                "document_id": document_id,
                "filename": str(filename),
                "chunk_id": chunk_id,
                "page_number": page_number,
                "excerpt": excerpt,
            }
        )

    bibliography.sort(key=_citation_sort_key)

    bundle: dict[str, Any] = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "workspace": {
            "id": int(workspace.id),
            "name": str(workspace.name),
            "created_by": int(workspace.created_by),
            "created_at": _isoformat(workspace.created_at),
            "updated_at": _isoformat(workspace.updated_at),
        },
        "research_run": {
            "id": int(run.id),
            "workspace_id": int(run.workspace_id),
            "requester_id": int(run.requester_id),
            "query": str(run.query),
            "status": str(run.status),
            "created_at": _isoformat(run.created_at),
            "completed_at": _isoformat(run.completed_at),
            "metadata": run.run_metadata or {},
        },
        "answer": answer_text.strip(),
        "bibliography": bibliography,
        "source_documents": source_documents,
    }

    if facets is not None:
        bundle["facets"] = facets

    return bundle


def render_research_markdown(bundle: dict[str, Any]) -> str:
    workspace = bundle["workspace"]
    run = bundle["research_run"]

    lines = [
        f"# Research Report: {run['query']}",
        "",
        "## Run Information",
        "",
        f"- **Run ID:** {run['id']}",
        f"- **Status:** {run['status']}",
        f"- **Workspace:** {workspace['name']} (ID {workspace['id']})",
        f"- **Requester ID:** {run['requester_id']}",
        f"- **Created at:** {run['created_at'] or 'Unknown'}",
        f"- **Completed at:** {run['completed_at'] or 'Unknown'}",
        f"- **Export schema version:** {bundle['export_schema_version']}",
        "",
        "## Research Query",
        "",
        run["query"],
        "",
    ]

    facets = bundle.get("facets")
    if facets and isinstance(facets, dict):
        lines.extend(["## Comparative Facets", ""])
        for facet_name, facet_content in facets.items():
            lines.extend([f"### {facet_name.capitalize()}", "", str(facet_content).strip(), ""])
    else:
        lines.extend([
            "## Synthesized Answer",
            "",
            bundle["answer"],
            "",
        ])

    lines.extend([
        "## Bibliography",
        "",
    ])

    bibliography = bundle["bibliography"]

    if not bibliography:
        lines.extend(["No citations were recorded for this research run.", ""])
    else:
        for citation in bibliography:
            citation_id = citation["citation_id"]
            filename = citation["filename"].replace("\n", " ").strip()
            excerpt = citation["excerpt"].replace("\n", " ").strip()
            page = (
                str(citation["page_number"])
                if citation["page_number"] is not None
                else "Unknown"
            )

            lines.extend(
                [
                    f"### [{citation_id}] {filename}",
                    "",
                    f"- **Document ID:** {citation['document_id']}",
                    f"- **Chunk ID:** {citation['chunk_id']}",
                    f"- **Page:** {page}",
                    "",
                    "> "
                    + (
                        excerpt.replace("\r", " ")
                        if excerpt
                        else "No excerpt recorded."
                    ),
                    "",
                ]
            )

    lines.extend(
        [
            "## Source Documents",
            "",
        ]
    )

    source_documents = bundle["source_documents"]

    if not source_documents:
        lines.extend(["No source-document provenance records were found.", ""])
    else:
        for document in source_documents:
            lines.append(
                f"- **{document['filename']}** "
                f"(document ID {document['document_id']})"
            )

            chunks = document["provenance"]["candidate_chunks"]
            if chunks:
                chunk_descriptions = []
                for chunk in chunks:
                    page = (
                        str(chunk["page_number"])
                        if chunk["page_number"] is not None
                        else "unknown"
                    )
                    chunk_descriptions.append(
                        f"chunk {chunk['chunk_id']} (page {page})"
                    )
                lines.append("  - Candidate evidence: " + ", ".join(chunk_descriptions))

        lines.append("")

    lines.extend(
        [
            "## Reproducibility Metadata",
            "",
            "```json",
            json.dumps(
                run["metadata"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def render_research_json(bundle: dict[str, Any]) -> str:
    return (
        json.dumps(
            bundle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def render_research_export(
    bundle: dict[str, Any],
    *,
    export_format: str,
) -> tuple[str, str]:
    if export_format == "markdown":
        return render_research_markdown(bundle), "text/markdown; charset=utf-8"

    if export_format == "json":
        return render_research_json(bundle), "application/json; charset=utf-8"

    raise ValueError("Unsupported research export format.")


def content_disposition_attachment(filename: str) -> str:
    """
    Return an attachment Content-Disposition value with an ASCII filename
    fallback and RFC 5987 filename* parameter.
    """
    safe_ascii = re.sub(r"[^A-Za-z0-9._-]", "-", filename)
    safe_ascii = safe_ascii.strip(".-") or "research-export"
    encoded = quote(filename, safe="!#$&+-.^_`|~")
    return f'attachment; filename="{safe_ascii}"; ' f"filename*=UTF-8''{encoded}"
