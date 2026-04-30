import io
from pypdf import PdfReader

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"
        return full_text.strip()
    except Exception as e:
        return f"Error reading PDF: {str(e)}"