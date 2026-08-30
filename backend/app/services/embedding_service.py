import os
import httpx
from typing import List, Optional, Union
from dataclasses import dataclass

from app.core.config import settings
from app.utils.pdf_extractor import PDFPage


@dataclass(frozen=True)
class DocumentChunk:
    """A chunk of document text with its source metadata."""

    text: str
    page_number: int
    chunk_index: int

class EmbeddingService:
    @staticmethod
    def chunk_text(
        pages: Union[List[PDFPage], str],
        chunk_size: int = 1200,
        overlap: int = 200,
    ) -> List[DocumentChunk]:
        """
        Split PDF text into semantic-ish chunks using paragraph and
        sentence boundaries instead of blindly splitting by words.

        Chunk size and overlap are measured approximately in characters.

        For PDF input, chunks remain page-aware and never cross page boundaries.
        """

        if not pages:
            return []

        if chunk_size <= 0:
            raise ValueError(
                "chunk_size must be greater than 0"
            )

        if overlap < 0 or overlap >= chunk_size:
            raise ValueError(
                "overlap must be >= 0 and smaller than chunk_size"
            )

        def normalize_text(text: str) -> str:
            """Normalize PDF whitespace without destroying paragraph structure."""
            lines = [line.strip() for line in text.splitlines()]

            paragraphs = []
            current = []

            for line in lines:
                if not line:
                    if current:
                        paragraphs.append(" ".join(current))
                        current = []
                    continue

                current.append(line)

            if current:
                paragraphs.append(" ".join(current))

            return "\n\n".join(paragraphs).strip()

        def split_sentences(text: str) -> List[str]:
            """
            Lightweight sentence splitter.

            This intentionally avoids adding a heavyweight NLP dependency.
            """
            import re

            sentences = re.split(
                r"(?<=[.!?])\s+(?=[A-Z0-9\"'])",
                text.strip(),
            )

            return [sentence.strip() for sentence in sentences if sentence.strip()]

        def split_long_text(text: str) -> List[str]:
            """
            Split text that is larger than chunk_size while still preferring
            word boundaries.
            """
            words = text.split()

            pieces = []
            current_words = []
            current_length = 0

            for word in words:
                additional_length = len(word)
                if current_words:
                    additional_length += 1

                if current_words and current_length + additional_length > chunk_size:
                    pieces.append(" ".join(current_words))
                    current_words = [word]
                    current_length = len(word)
                else:
                    current_words.append(word)
                    current_length += additional_length

            if current_words:
                pieces.append(" ".join(current_words))

            return pieces

        def create_chunks_for_page(
            page_text: str,
            page_number: int,
            start_index: int,
        ) -> tuple[List[DocumentChunk], int]:

            text = normalize_text(page_text)

            if not text:
                return [], start_index

            paragraphs = [
                paragraph.strip()
                for paragraph in text.split("\n\n")
                if paragraph.strip()
            ]

            # Convert paragraphs into sentence groups.
            units: List[str] = []

            for paragraph in paragraphs:

                if len(paragraph) <= chunk_size:
                    sentences = split_sentences(paragraph)

                    if sentences:
                        units.extend(sentences)
                    else:
                        units.append(paragraph)

                else:
                    # Very large paragraph: sentence splitting first.
                    sentences = split_sentences(paragraph)

                    if sentences:
                        for sentence in sentences:
                            if len(sentence) <= chunk_size:
                                units.append(sentence)
                            else:
                                units.extend(split_long_text(sentence))
                    else:
                        units.extend(split_long_text(paragraph))

            chunks: List[DocumentChunk] = []

            current_units: List[str] = []
            current_length = 0

            for unit in units:

                unit_length = len(unit)

                additional_length = (
                    unit_length if not current_units else unit_length + 1
                )

                # -----------------------------------------------------
                # Current chunk can accept this unit.
                # -----------------------------------------------------

                if current_units and current_length + additional_length > chunk_size:
                    chunk_text = " ".join(current_units).strip()

                    chunks.append(
                        DocumentChunk(
                            text=chunk_text,
                            page_number=page_number,
                            chunk_index=start_index,
                        )
                    )

                    start_index += 1

                    # -------------------------------------------------
                    # Build overlap from the end of the previous chunk.
                    # Prefer complete sentences/units.
                    # -------------------------------------------------

                    overlap_units = []
                    overlap_length = 0

                    for previous_unit in reversed(current_units):

                        extra_length = (
                            len(previous_unit)
                            if not overlap_units
                            else len(previous_unit) + 1
                        )

                        if overlap_length + extra_length > overlap:
                            break

                        overlap_units.insert(0, previous_unit)
                        overlap_length += extra_length

                    current_units = overlap_units
                    current_length = overlap_length

                # -----------------------------------------------------
                # Add current unit.
                # -----------------------------------------------------

                if not current_units:
                    current_units = [unit]
                    current_length = unit_length

                elif current_length + unit_length + 1 <= chunk_size:
                    current_units.append(unit)
                    current_length += unit_length + 1

                else:
                    # This can happen when the overlap itself is large.
                    chunk_text = " ".join(current_units).strip()

                    chunks.append(
                        DocumentChunk(
                            text=chunk_text,
                            page_number=page_number,
                            chunk_index=start_index,
                        )
                    )

                    start_index += 1

                    current_units = [unit]
                    current_length = unit_length

            # ---------------------------------------------------------
            # Final chunk.
            # ---------------------------------------------------------

            if current_units:
                chunks.append(
                    DocumentChunk(
                        text=" ".join(current_units).strip(),
                        page_number=page_number,
                        chunk_index=start_index,
                    )
                )

                start_index += 1

            return chunks, start_index

        # ---------------------------------------------------------
        # PDF / PAGE-AWARE INPUT
        # ---------------------------------------------------------

        if isinstance(pages, list):

            chunks: List[DocumentChunk] = []

            chunk_index = 0

            for page in pages:

                if not isinstance(page, PDFPage):
                    raise TypeError(
                        "Expected every item to be a PDFPage."
                    )

                page_chunks, chunk_index = create_chunks_for_page(
                    page.text,
                    page.page_number,
                    chunk_index,
                )
                
                chunks.extend(page_chunks)

            return chunks

        # ---------------------------------------------------------
        # LEGACY STRING INPUT
        # ---------------------------------------------------------

        if isinstance(pages, str):

            text = pages.strip()

            if not text:
                return []

            chunks, _ = create_chunks_for_page(
                text,
                page_number=0,
                start_index=0,
            )
            return chunks

        raise TypeError(
            "pages must be a list of PDFPage objects or a string."
        )

    @staticmethod
    async def generate_embedding(
        text: str,
        model_provider: str,
    ) -> Optional[List[float]]:
        """
        Generate an embedding for the supplied text.

        Supported providers:
        - Gemini
        - Ollama / Llama

        Gemini uses:
            gemini-embedding-001

        Ollama uses:
            settings.OLLAMA_EMBED_MODEL
            default: nomic-embed-text
        """

        # ---------------------------------------------------------
        # BASIC VALIDATION
        # ---------------------------------------------------------

        if not text or not text.strip():
            print("⚠️ Cannot generate embedding: empty text.")
            return None

        if not model_provider:
            print("⚠️ Cannot generate embedding: provider is missing.")
            return None

        clean_provider = model_provider.lower().strip()

        # =========================================================
        # 1. GEMINI EMBEDDINGS
        # =========================================================

        if "gemini" in clean_provider:

            gemini_key = getattr(
                settings,
                "GEMINI_API_KEY",
                None,
            ) or os.getenv("GEMINI_API_KEY")

            if not gemini_key:
                print("❌ Gemini API Key is missing.")
                return None

            # Current supported Gemini text embedding model.
            model_name = "gemini-embedding-001"

            # Gemini REST embedContent endpoint.
            url = (
                "https://generativelanguage.googleapis.com/"
                f"v1beta/models/{model_name}:embedContent"
            )

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": gemini_key,
            }

            payload = {
                "model": f"models/{model_name}",
                "content": {"parts": [{"text": text.strip()}]},
                "outputDimensionality": 768,
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:

                    response = await client.post(
                        url,
                        headers=headers,
                        json=payload,
                    )

                # -------------------------------------------------
                # SUCCESS
                # -------------------------------------------------

                if response.status_code == 200:

                    data = response.json()

                    embedding = data.get("embedding", {}).get("values")

                    if not embedding:
                        print(
                            "❌ Gemini returned a successful response "
                            "but no embedding values."
                        )
                        print(f"Response: {data}")
                        return None

                    print(
                        f"✅ Gemini embedding generated "
                        f"({len(embedding)} dimensions)."
                    )

                    return embedding

                # -------------------------------------------------
                # ERROR
                # -------------------------------------------------

                print(
                    f"❌ Gemini REST Embedding Error "
                    f"({response.status_code}): "
                    f"{response.text}"
                )

                return None

            except httpx.TimeoutException:
                print("❌ Gemini Embedding Error: " "request timed out.")
                return None

            except httpx.RequestError as e:
                print(f"❌ Gemini Embedding Network Error: {str(e)}")
                return None

            except Exception as e:
                print(f"❌ Gemini Embedding Call Exception: {str(e)}")
                return None

        # =========================================================
        # 2. LOCAL OLLAMA EMBEDDINGS
        # =========================================================

        elif "ollama" in clean_provider or "llama" in clean_provider:

            ollama_url = (
                getattr(
                    settings,
                    "OLLAMA_BASE_URL",
                    None,
                )
                or "http://host.docker.internal:11434"
            )

            model_name = (
                getattr(
                    settings,
                    "OLLAMA_EMBED_MODEL",
                    None,
                )
                or "nomic-embed-text"
            )

            # Remove accidental trailing slash.
            ollama_url = ollama_url.rstrip("/")

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:

                    response = await client.post(
                        f"{ollama_url}/api/embeddings",
                        json={
                            "model": model_name,
                            "prompt": text.strip(),
                        },
                    )

                response.raise_for_status()

                data = response.json()

                embedding = data.get("embedding")

                if not embedding:
                    print("❌ Ollama returned no embedding.")
                    print(f"Response: {data}")
                    return None

                print(
                    f"✅ Ollama embedding generated " f"({len(embedding)} dimensions)."
                )

                return embedding

            except httpx.TimeoutException:
                print("❌ Local Ollama Embedding Error: " "request timed out.")
                return None

            except httpx.RequestError as e:
                print(f"❌ Local Ollama Network Error: {str(e)}")
                return None

            except Exception as e:
                print(f"❌ Local Ollama Embedding Error: {str(e)}")
                return None

        # =========================================================
        # UNKNOWN PROVIDER
        # =========================================================

        else:

            print(f"⚠️ Provider '{model_provider}' does not match " "Gemini or Ollama.")

            return None
