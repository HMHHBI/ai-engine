import httpx
from typing import List, Optional
from app.core.config import settings


class EmbeddingService:
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Splits raw text into overlapping chunks."""
        words = text.split()
        if not words:
            return []

        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i : i + chunk_size])
            chunks.append(chunk)
            if i + chunk_size >= len(words):
                break
        return chunks

    @staticmethod
    async def generate_embedding(text: str) -> Optional[List[float]]:
        """
        Generates vector embeddings locally using Ollama's nomic-embed-text model.
        """
        ollama_url = getattr(
            settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
        )
        model_name = getattr(settings, "OLLAMA_EMBED_MODEL", "nomic-embed-text")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": model_name, "prompt": text},
                )
                response.raise_for_status()
                res_json = response.json()
                return res_json.get("embedding")
        except Exception as e:
            print(f"Error generating local embedding: {str(e)}")
            return None
