import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be read or contains no usable text."""


@dataclass(frozen=True)
class PDFPage:
    """Text extracted from a single PDF page."""

    page_number: int
    text: str


def extract_text_from_pdf(
    file_source: Union[str, Path, bytes],
) -> List[PDFPage]:
    """
    Extract text from a PDF page-by-page.

    Each returned PDFPage preserves the original PDF page number.
    """

    try:
        if isinstance(file_source, (str, Path)):
            doc = fitz.open(str(file_source))

        elif isinstance(file_source, bytes):
            doc = fitz.open(stream=file_source, filetype="pdf")

        else:
            raise PDFExtractionError(
                "Unsupported file source type. " "Expected bytes or a file path."
            )

        with doc:
            if doc.is_encrypted:
                raise PDFExtractionError(
                    "This PDF is password-protected and cannot be read."
                )

            if len(doc) == 0:
                raise PDFExtractionError("This PDF contains no pages.")

            pages: List[PDFPage] = []

            for page_number, page in enumerate(doc, start=1):
                text = page.get_text(
                    "text",
                    sort=True,
                ).strip()

                if text:
                    pages.append(
                        PDFPage(
                            page_number=page_number,
                            text=text,
                        )
                    )
                else:
                    logger.warning(
                        "Page %s contains no readable text.",
                        page_number,
                    )

            if not pages:
                raise PDFExtractionError(
                    "No readable text was found in this PDF. "
                    "It may be a scanned or image-only PDF."
                )

            return pages

    except fitz.FileDataError as exc:
        logger.error("Corrupted PDF: %s", exc)

        raise PDFExtractionError("The PDF is corrupted and cannot be read.") from exc

    except PDFExtractionError:
        raise

    except Exception as exc:
        logger.exception("Unexpected error while extracting PDF.")

        raise PDFExtractionError(f"Internal PDF extraction error: {exc}") from exc
