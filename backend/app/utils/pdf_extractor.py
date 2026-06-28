import logging
import fitz  # PyMuPDF library
from pathlib import Path
from typing import Union

# Logger setup taake errors ka track rahe
logger = logging.getLogger(__name__)

class PDFExtractionError(Exception):
    """Custom error jab PDF read karne me koi masla aaye"""
    pass

def extract_text_from_pdf(file_source: Union[str, Path, bytes]) -> str:
    """
    PDF se text extract karne ka robust tareqa.
    file_source me aap file ke bytes ya file ka path (string/Path) de sakte hain.
    """
    try:
        # 1. Check karna ke data kis shakal me aya hai
        if isinstance(file_source, (str, Path)):
            doc = fitz.open(str(file_source))
        elif isinstance(file_source, bytes):
            doc = fitz.open(stream=file_source, filetype="pdf")
        else:
            raise PDFExtractionError("Unsupported file source type. Bytes ya File Path lazmi hai.")
            
        with doc:
            # 2. Guardrails: Security aur Validation check
            if doc.is_encrypted:
                raise PDFExtractionError("Yeh PDF password-protected (encrypted) hai. Hum isse read nahi kar sakte.")
            if len(doc) == 0:
                raise PDFExtractionError("Is PDF ke andar koi page nahi hai (Empty PDF).")

            full_text = []
            
            # 3. Page by page text nikalna
            for page_num, page in enumerate(doc):
                # Naye PyMuPDF me 'text' sab se safe aur standard option hai format structure ke liye
                # Agar visual order maintain karna ho toh 'sort=True' lagaya jata hai
                page_text = page.get_text("text", sort=True)
                
                if page_text.strip():
                    full_text.append(page_text)
                else:
                    logger.warning(f"Page {page_num + 1} khali hai ya isme sirf image/scanned copy hai.")

            if not full_text:
                raise PDFExtractionError("PDF me koi readable text nahi mila. Shayed yeh scanned images hain.")

            # Pages ko alag karne ke liye clear delimiter lagayein
            return "\n\n--- Page Break ---\n\n".join(full_text).strip()

    except fitz.FileDataError as e:
        logger.error(f"Corrupted PDF error: {str(e)}")
        raise PDFExtractionError("PDF file kharab (corrupted) hai aur read nahi ho sakti.")
    except Exception as e:
        logger.exception("PDF extract karte hue koi unexpected error aya.")
        raise PDFExtractionError(f"Internal extraction error: {str(e)}")