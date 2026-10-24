from app.api.chat import _build_source_payload
from app.repositories.chat_repo import _normalize_sources
from app.schemas.chat_schema import RetrievedSourceOut


def test_retrieved_source_out_preserves_legacy_fields():
    source = RetrievedSourceOut.model_validate(
        {
            "id": 41,
            "document_id": 7,
            "page_number": 3,
            "chunk_index": 5,
            "distance": 0.12,
            "snippet": "Example source passage.",
        }
    )
    result = source.model_dump()
    assert result["id"] == 41
    assert result["document_id"] == 7
    assert result["page_number"] == 3
    assert result["chunk_index"] == 5
    assert result["distance"] == 0.12
    assert result["snippet"] == "Example source passage."
    assert result["chunk_id"] == 41
    assert result["excerpt"] == "Example source passage."
    assert result["document_title"] is None


def test_retrieved_source_out_accepts_new_fields_without_legacy_aliases():
    source = RetrievedSourceOut.model_validate(
        {
            "chunk_id": 42,
            "document_id": 8,
            "page_number": 4,
            "chunk_index": 2,
            "distance": 0.05,
            "excerpt": "Modern citation excerpt.",
            "document_title": "Attention Is All You Need.pdf",
        }
    )
    result = source.model_dump()
    assert result["id"] == 42
    assert result["chunk_id"] == 42
    assert result["snippet"] == "Modern citation excerpt."
    assert result["excerpt"] == "Modern citation excerpt."
    assert result["document_title"] == "Attention Is All You Need.pdf"


def test_build_source_payload_formats_correctly():
    raw_chunks = [
        {
            "id": 101,
            "document_id": 10,
            "page_number": 1,
            "chunk_index": 0,
            "distance": 0.015,
            "content": "A raw chunk text content.",
        }
    ]
    payload = _build_source_payload(
        raw_chunks,
        document_title="Research_Paper.pdf",
    )
    assert len(payload) == 1
    item = payload[0]
    assert item["id"] == 101
    assert item["chunk_id"] == 101
    assert item["document_title"] == "Research_Paper.pdf"
    assert item["excerpt"] == "A raw chunk text content."
    assert item["snippet"] == "A raw chunk text content."


def test_chat_repo_normalize_sources_preserves_new_fields():
    raw_sources = [
        {
            "id": 200,
            "document_id": 15,
            "page_number": 5,
            "chunk_index": 1,
            "distance": 0.02,
            "snippet": "Persisted snippet text.",
            "chunk_id": 200,
            "document_title": "Paper_V2.pdf",
            "excerpt": "Persisted snippet text.",
        }
    ]
    normalized = _normalize_sources(raw_sources)
    assert normalized is not None
    assert len(normalized) == 1
    assert normalized[0]["chunk_id"] == 200
    assert normalized[0]["document_title"] == "Paper_V2.pdf"
    assert normalized[0]["excerpt"] == "Persisted snippet text."
