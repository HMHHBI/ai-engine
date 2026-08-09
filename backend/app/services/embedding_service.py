import os
import httpx
from typing import List, Optional

from app.core.config import settings


class EmbeddingService:
    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> List[str]:
        """
        Split raw text into overlapping word-based chunks.

        Example:
        chunk_size = 500
        overlap = 50

        Chunk 1: words 0-499
        Chunk 2: words 450-949
        Chunk 3: words 900-1399
        """

        if not text or not text.strip():
            return []

        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")

        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be >= 0 and smaller than chunk_size")

        words = text.split()

        if not words:
            return []

        chunks: List[str] = []

        step = chunk_size - overlap

        for i in range(0, len(words), step):
            chunk_words = words[i : i + chunk_size]

            if not chunk_words:
                break

            chunks.append(" ".join(chunk_words))

            # Stop after the final chunk.
            if i + chunk_size >= len(words):
                break

        return chunks

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
