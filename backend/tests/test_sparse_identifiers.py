import pytest
from app.repositories.vector_repo import VectorRepository


def test_sparse_tsquery_preserves_incident_and_hyphenated_identifiers():
    # INC-4821 should extract constituent components (INC, 4821) without squashing into INC4821
    ts_query = VectorRepository._build_sparse_tsquery("INC-4821")
    tokens = [t.strip() for t in ts_query.split("|")]
    assert "INC" in tokens
    assert "4821" in tokens
    assert "INC4821" not in tokens

    ts_query_12 = VectorRepository._build_sparse_tsquery("INC-4812")
    tokens_12 = [t.strip() for t in ts_query_12.split("|")]
    assert "INC" in tokens_12 and "4812" in tokens_12

    ts_query_27 = VectorRepository._build_sparse_tsquery("INC-4827")
    tokens_27 = [t.strip() for t in ts_query_27.split("|")]
    assert "INC" in tokens_27 and "4827" in tokens_27


def test_sparse_tsquery_preserves_request_id_and_versions():
    # X-Request-ID should retain X, Request, ID without destructive concatenation
    ts_req = VectorRepository._build_sparse_tsquery("X-Request-ID")
    tokens_req = [t.strip() for t in ts_req.split("|")]
    assert "X" in tokens_req
    assert "Request" in tokens_req
    assert "ID" in tokens_req
    assert "XRequestID" not in tokens_req

    # /api/v2/
    ts_api = VectorRepository._build_sparse_tsquery("/api/v2/")
    tokens_api = [t.strip() for t in ts_api.split("|")]
    assert "api" in tokens_api
    assert "v2" in tokens_api

    # isolated versions
    assert VectorRepository._build_sparse_tsquery("v1") == "v1"
    assert VectorRepository._build_sparse_tsquery("v2") == "v2"


def test_sparse_tsquery_preserves_http_status_codes_and_decimals():
    # HTTP 404
    ts_http = VectorRepository._build_sparse_tsquery("HTTP 404")
    tokens_http = [t.strip() for t in ts_http.split("|")]
    assert "HTTP" in tokens_http
    assert "404" in tokens_http

    # 0.70 and 0.15 decimals
    ts_dec1 = VectorRepository._build_sparse_tsquery("threshold 0.70")
    assert "'0.70'" in ts_dec1 or "0.70" in ts_dec1

    ts_dec2 = VectorRepository._build_sparse_tsquery("0.15 error rate")
    assert "'0.15'" in ts_dec2 or "0.15" in ts_dec2
