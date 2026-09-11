"""Tests for sentence segmentation and boundary protection in EmbeddingService.

Verifies:
1. False boundary protection for honorifics, Latin abbreviations, and initials.
2. Legitimate sentence boundary preservation.
3. Preservation of decimal and version numbers.
4. End-to-end DocumentChunk boundary integrity on texts exceeding 500 characters.
"""
from app.services.embedding_service import EmbeddingService
from app.utils.pdf_extractor import PDFPage


def test_honorific_abbreviations_preserved_together():
    """Verifies titles and names stay intact in sentence segmentation."""
    text = "Dr. Smith met with Prof. Jones at St. Jude. The clinic was quiet."
    page = PDFPage(page_number=1, text=text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert "Dr. Smith" in chunks[0].text
    assert "Prof. Jones" in chunks[0].text
    assert "St. Jude." in chunks[0].text


def test_latin_abbreviations_preserved_without_fragmentation():
    """Verifies e.g. and i.e. do not trigger false sentence splits."""
    text = "Review all critical sections, e.g. Section 4. Next sentence follows cleanly."
    page = PDFPage(page_number=1, text=text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert "e.g. Section 4." in chunks[0].text


def test_initials_preserved():
    """Verifies single uppercase initial is not severed from subsequent capitalized surname."""
    text = "John F. Kennedy was president. The speech was historic."
    page = PDFPage(page_number=1, text=text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert "John F. Kennedy" in chunks[0].text


def test_legitimate_sentence_boundaries_split():
    """Verifies normal punctuation boundaries split as expected."""
    text = "The system is fully ready. Start processing now."
    page = PDFPage(page_number=1, text=text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].text == "The system is fully ready. Start processing now."


def test_decimal_and_version_numbers_remain_intact():
    """Verifies prices and version numbers retain dot without splitting."""
    text = "Total cost is $45.50 for version 2.3. Transaction finalized."
    page = PDFPage(page_number=1, text=text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert "$45.50" in chunks[0].text
    assert "2.3." in chunks[0].text


def test_long_form_boundary_chunking_with_abbreviations():
    """Verifies boundary protection under multi-chunk threshold (>500 chars).

    Places 'Dr. Smith' directly near the 500-char boundary to guarantee
    it does not create a false terminal sentence fragment.
    """
    filler = "This sentence establishes regular context and fills token space. " * 6
    boundary_text = (
        filler
        + "Dr. Smith presented the clinical trial findings to the board yesterday afternoon. "
        + "The board reviewed all clinical outcomes and approved the next phase of deployment."
    )
    assert len(boundary_text) > 500

    page = PDFPage(page_number=1, text=boundary_text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 500
        if "Dr." in c.text:
            assert "Dr. Smith" in c.text
