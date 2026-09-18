import io
import pytest
from app.storage.local import LocalStorageBackend
from app.storage.keys import build_document_key


def test_local_storage_lifecycle(tmp_path):
    storage = LocalStorageBackend(root=tmp_path)
    key = build_document_key(user_id=1)
    test_data = b"%PDF-1.4 test binary stream data"

    # 1. Save
    saved_key = storage.save(key, io.BytesIO(test_data), content_type="application/pdf")
    assert saved_key == key
    assert storage.exists(key) is True

    # 2. Read
    stream = storage.get_stream(key)
    assert stream.read() == test_data

    # 3. Delete
    storage.delete(key)
    assert storage.exists(key) is False


def test_path_traversal_prevention(tmp_path):
    storage = LocalStorageBackend(root=tmp_path)

    with pytest.raises(ValueError, match="escapes the storage root"):
        storage.save("../malicious.pdf", io.BytesIO(b"data"), content_type="application/pdf")


def test_build_document_key_validation():
    with pytest.raises(ValueError):
        build_document_key(user_id=0)

    key = build_document_key(user_id=42)
    assert key.startswith("raw_pdfs/42/")
    assert key.endswith(".pdf")
