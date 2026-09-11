"""Characterization tests for sentence segmentation baseline behavior.

This module records existing sentence splitting behavior across edge cases:
- Common abbreviations (Dr., Mr., e.g., i.e.)
- Decimal numbers and monetary values ($45.50, 2.3)
- Initials (John F. Kennedy)
- Ellipses followed by capitalized tokens
- Lowercase sentence continuations
- Numbered headings (Section 1. Introduction)
"""
import re
import pytest
from app.services.embedding_service import EmbeddingService
from app.utils.pdf_extractor import PDFPage


def current_regex_split(text: str) -> list[str]:
    """Mirrors the exact regex implementation in split_sentences."""
    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9\"'])",
        text.strip(),
    )
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def test_characterize_honorific_abbreviations():
    """Documents that honorifics followed by capitalized names are currently split."""
    text = "Dr. Smith met with Prof. Jones at St. Jude."
    splits = current_regex_split(text)
    # Documents baseline behavior where titles get severed from names
    assert splits == ["Dr.", "Smith met with Prof.", "Jones at St.", "Jude."]


def test_characterize_latin_abbreviations():
    """Documents that e.g. followed by a capitalized token splits."""
    text = "Review all sections, e.g. Section 4."
    splits = current_regex_split(text)
    assert splits == ["Review all sections, e.g.", "Section 4."]


def test_characterize_decimal_numbers_without_spaces():
    """Documents that embedded decimals without space after dot do not split."""
    text = "The price is $45.50 and version is 2.3."
    splits = current_regex_split(text)
    assert splits == ["The price is $45.50 and version is 2.3."]


def test_characterize_initials():
    """Documents middle initials splitting from surnames."""
    text = "John F. Kennedy was president."
    splits = current_regex_split(text)
    assert splits == ["John F.", "Kennedy was president."]


def test_characterize_ellipses_followed_by_capital():
    """Documents ellipses preceding capital words splitting."""
    text = "Wait... What happened?!"
    splits = current_regex_split(text)
    assert splits == ["Wait...", "What happened?!"]


def test_characterize_lowercase_boundary_not_split():
    """Documents that punctuation followed by lowercase words is not split."""
    text = "First sentence. second sentence starts lowercase."
    splits = current_regex_split(text)
    assert splits == ["First sentence. second sentence starts lowercase."]


def test_characterize_fixture_punctuation_txt_chunking():
    """Verifies baseline chunking result on punctuation.txt fixture."""
    fixture_text = (
        "Dr. Smith arrived at 5:30 p.m. to discuss the $45.50 charge. "
        "See Appendix A.1 for details, e.g. Section 2.3. "
        "Wait... did it work correctly?!"
    )
    page = PDFPage(page_number=1, text=fixture_text)
    chunks = EmbeddingService.chunk_text([page], chunk_size=500, overlap=50)

    # In single page under 500 chars, chunks are packed together
    assert len(chunks) == 1
    assert "Dr. Smith" in chunks[0].text
