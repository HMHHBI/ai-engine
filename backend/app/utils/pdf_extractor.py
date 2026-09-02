from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

import fitz

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be safely processed."""


@dataclass(frozen=True)
class PDFPage:
    page_number: int
    text: str


def extract_text_from_pdf(file_source: Union[str, Path, bytes]) -> List[PDFPage]:
    try:
        if isinstance(file_source, (str, Path)):
            doc = fitz.open(str(file_source))
        elif isinstance(file_source, bytes):
            if len(file_source) < 5 or file_source[:5] != b"%PDF-":
                raise PDFExtractionError("The uploaded file is not a valid PDF.")
            doc = fitz.open(stream=file_source, filetype="pdf")
        else:
            raise PDFExtractionError("Unsupported PDF source type.")

        with doc:
            if doc.is_encrypted:
                raise PDFExtractionError("Password-protected PDFs are not supported.")

            page_count = len(doc)
            if page_count == 0:
                raise PDFExtractionError("The PDF contains no pages.")

            if page_count > settings.MAX_PDF_PAGES:
                raise PDFExtractionError(
                    "The PDF exceeds the maximum allowed page count."
                )

            pages: List[PDFPage] = []
            total_chars = 0

            for page_number, page in enumerate(doc, start=1):
                text = page.get_text("text", sort=True).strip()
                if not text:
                    continue

                total_chars += len(text)
                if total_chars > settings.MAX_EXTRACTED_TEXT_CHARS:
                    raise PDFExtractionError(
                        "The extracted PDF text exceeds the maximum allowed document size."
                    )

                pages.append(PDFPage(page_number=page_number, text=text))

            if not pages:
                raise PDFExtractionError("No readable text was found in this PDF.")

            return pages

    except PDFExtractionError:
        raise
    except fitz.FileDataError as exc:
        logger.warning(
            "Rejected malformed PDF during extraction: %s", type(exc).__name__
        )
        raise PDFExtractionError("The uploaded PDF is invalid or corrupted.") from exc
    except Exception as exc:
        logger.exception("Unexpected PDF extraction failure.")
        raise PDFExtractionError("The PDF could not be processed.") from exc
