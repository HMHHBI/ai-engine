from decimal import Decimal
import pytest
from app.services.usage_service import normalize_usage, new_usage_ids
from app.services.pricing_service import _decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {
                "input_tokens": 12,
                "output_tokens": 8,
                "total_tokens": 20,
            },
            (12, 8, 20, "provider_reported"),
        ),
        (
            {
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
            },
            (12, 8, 20, "provider_reported"),
        ),
        (
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            (0, 0, 0, "provider_reported"),
        ),
        (
            None,
            (None, None, None, "unavailable"),
        ),
        (
            {},
            (None, None, None, "unavailable"),
        ),
    ],
)
def test_normalize_usage(raw, expected):
    assert normalize_usage(raw) == expected


def test_normalize_usage_calculates_total_when_missing():
    assert normalize_usage(
        {
            "input_tokens": 12,
            "output_tokens": 8,
        }
    ) == (12, 8, 20, "provider_reported")


def test_normalize_usage_rejects_negative_token_count():
    input_tokens, output_tokens, total_tokens, source = normalize_usage(
        {
            "input_tokens": -1,
            "output_tokens": 5,
            "total_tokens": 4,
        }
    )
    assert input_tokens is None
    assert output_tokens == 5
    assert total_tokens == 4
    assert source == "provider_reported"


def test_normalize_usage_rejects_boolean_as_token_count():
    assert normalize_usage(
        {
            "input_tokens": True,
            "output_tokens": False,
        }
    ) == (None, None, None, "unavailable")


def test_decimal_uses_exact_decimal_representation():
    assert _decimal("0.125", "rate") == Decimal("0.125")


@pytest.mark.parametrize(
    "value",
    ["-1", "NaN", "Infinity", "-Infinity", "not-a-number"],
)
def test_decimal_rejects_invalid_or_negative_values(value):
    with pytest.raises(ValueError):
        _decimal(value, "rate")


def test_new_usage_ids_uniqueness():
    r1, k1 = new_usage_ids()
    r2, k2 = new_usage_ids()
    assert r1 != r2
    assert k1 != k2
    assert k1.startswith(f"usage_{r1}_")
