from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pymupdf


@dataclass(frozen=True)
class AcademicPaperFixture:
    filename: str
    pdf_bytes: bytes
    expected_page_count: int
    page_markers: Dict[int, str]


def _render_pages_to_pdf(
    pages_text: list[str],
    *,
    encrypt_password: str | None = None,
) -> bytes:
    doc = pymupdf.open()
    try:
        for body in pages_text:
            page = doc.new_page(width=612, height=792)
            if body:
                rect = pymupdf.Rect(54, 54, 558, 738)
                page.insert_textbox(
                    rect,
                    body,
                    fontsize=11,
                    fontname="helv",
                    align=pymupdf.TEXT_ALIGN_LEFT,
                )
        if encrypt_password:
            return doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw=encrypt_password,
                owner_pw=encrypt_password,
            )
        return doc.tobytes()
    finally:
        doc.close()


def build_academic_paper_pdf(
    *,
    paper_id: str = "PAPER-A",
    title: str = "Deterministic Hybrid Retrieval for Academic Copilots",
    methodology_phrase: str = "HNSW pgvector cosine indexing with 768-dimensional embeddings",
    findings_phrase: str = "p95 retrieval latency dropped by 43 percent across 5000 chunks",
) -> AcademicPaperFixture:
    page_1 = (
        f"{title} ({paper_id})\n\n"
        "Abstract\n"
        "This study evaluates deterministic citation provenance and hybrid vector-lexical "
        "retrieval pipelines for multi-document academic synthesis systems."
    )
    page_2 = (
        "1. Methodology\n\n"
        f"Our experimental benchmark utilizes {methodology_phrase}. "
        "Every extracted paragraph retains strict page-level provenance boundaries."
    )
    page_3 = (
        "2. Empirical Findings\n\n"
        f"Across controlled corpus sweeps, {findings_phrase} while maintaining "
        "100 percent exact page citation accuracy."
    )

    pdf_bytes = _render_pages_to_pdf([page_1, page_2, page_3])
    return AcademicPaperFixture(
        filename=f"{paper_id.lower()}_hybrid_retrieval.pdf",
        pdf_bytes=pdf_bytes,
        expected_page_count=3,
        page_markers={
            1: title,
            2: methodology_phrase,
            3: findings_phrase,
        },
    )


def build_sparse_blank_page_pdf() -> AcademicPaperFixture:
    page_1 = "Page One Introduction: Baseline transformer architecture overview."
    page_2 = "   \n\t  "
    page_3 = "Page Three Conclusion: Verified page numbering skips blank middle page."

    pdf_bytes = _render_pages_to_pdf([page_1, page_2, page_3])
    return AcademicPaperFixture(
        filename="sparse_blank_middle_page.pdf",
        pdf_bytes=pdf_bytes,
        expected_page_count=2,
        page_markers={
            1: "Baseline transformer architecture overview",
            3: "Verified page numbering skips blank middle page",
        },
    )


def build_two_column_pdf() -> bytes:
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=612, height=792)
        left_col = pymupdf.Rect(40, 60, 290, 400)
        right_col = pymupdf.Rect(320, 60, 570, 400)
        page.insert_textbox(
            left_col,
            "Left Column Section: Neuromorphic spiking cores reduce idle power draw.",
            fontsize=11,
            fontname="helv",
        )
        page.insert_textbox(
            right_col,
            "Right Column Section: Tensor accelerators sustain dense matrix throughput.",
            fontsize=11,
            fontname="helv",
        )
        return doc.tobytes()
    finally:
        doc.close()


def build_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=612, height=792)
        shape = page.new_shape()
        shape.draw_rect(pymupdf.Rect(100, 100, 300, 300))
        shape.finish(color=(0, 0, 1), fill=(0.8, 0.8, 1))
        shape.commit()
        return doc.tobytes()
    finally:
        doc.close()


def build_encrypted_pdf(password: str = "secret123") -> bytes:
    return _render_pages_to_pdf(
        ["Confidential research findings protected by AES-256."],
        encrypt_password=password,
    )
