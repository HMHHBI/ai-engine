"""Characterization and invariant tests for EmbeddingService.chunk_text behavior.

Locks down production chunking invariants (500-char target, 50-char overlap)
and verifies defect resolutions (P3-03).
"""

from __future__ import annotations

from app.services.embedding_service import EmbeddingService
from app.utils.pdf_extractor import PDFPage


def test_chunk_indices_are_sequential_and_zero_indexed():
    pages = [
        PDFPage(
            page_number=1,
            text="Sentence one is clear. Sentence two is informative. Sentence three adds more context. " * 8,
        )
    ]
    chunks = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    for expected_idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == expected_idx
        assert chunk.page_number == 1


def test_empty_or_whitespace_pages_produce_no_chunks():
    pages = [
        PDFPage(page_number=1, text=""),
        PDFPage(page_number=2, text="   \n\n\t  "),
    ]
    chunks = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)
    assert chunks == []


def test_empty_input_list_produces_empty_chunks():
    chunks = EmbeddingService.chunk_text([], chunk_size=500, overlap=50)
    assert chunks == []


def test_page_boundaries_are_strictly_preserved():
    pages = [
        PDFPage(page_number=1, text="Short text on page one."),
        PDFPage(page_number=2, text="Short text on page two."),
        PDFPage(page_number=3, text="Short text on page three."),
    ]
    chunks = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)

    assert len(chunks) == 3
    assert chunks[0].page_number == 1
    assert chunks[0].text == "Short text on page one."
    assert chunks[1].page_number == 2
    assert chunks[1].text == "Short text on page two."
    assert chunks[2].page_number == 3
    assert chunks[2].text == "Short text on page three."


def test_chunking_is_deterministic():
    text = (
        "Determinism check. A language model requires deterministic preprocessing pipelines. "
        "Every single execution must yield exact identical output slices."
    )
    pages = [PDFPage(page_number=1, text=text)]

    run_1 = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)
    run_2 = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)

    assert len(run_1) == len(run_2)
    for c1, c2 in zip(run_1, run_2):
        assert c1.chunk_index == c2.chunk_index
        assert c1.page_number == c2.page_number
        assert c1.text == c2.text


def test_multilingual_unicode_content_does_not_crash():
    pages = [
        PDFPage(
            page_number=1,
            text=(
                "Urdu: ہاسن اے آئی انجن ایک جدید آر اے جی پلیٹ فارم ہے۔ "
                "Arabic: محرك الذكاء الاصطناعي يدعم معالجة النصوص. "
                "German: Präzise Algorithmen für Umlaute wie ä, ö, und ü."
            ),
        )
    ]
    chunks = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)
    assert len(chunks) >= 1
    assert "ہاسن اے آئی" in chunks[0].text


def test_oversized_unbreakable_token_is_split_within_chunk_limit():
    """Invariant test: unbroken tokens exceeding chunk_size must be split
    so no chunk exceeds chunk_size.
    """
    long_token = "A" * 600
    pages = [PDFPage(page_number=1, text=long_token)]
    chunks = EmbeddingService.chunk_text(pages, chunk_size=500, overlap=50)

    # Must be split into chunks each <= 500 chars
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.text) <= 500
    # Complete text must be preserved
    assert "".join(c.text for c in chunks) == long_token


def test_string_input_compatibility():
    """Characterization test: raw str input assigns page_number=0 in current baseline."""
    raw_str = "String input fallback check. This tests the str overload of chunk_text."
    chunks = EmbeddingService.chunk_text(raw_str, chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].page_number == 0
    assert chunks[0].chunk_index == 0
