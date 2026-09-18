from __future__ import annotations

from uuid import uuid4


def build_document_key(user_id: int) -> str:
    """
    Build the canonical object key for a document PDF.
    Format: raw_pdfs/{user_id}/{uuid}.pdf
    """
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    return f"raw_pdfs/{user_id}/{uuid4()}.pdf"
