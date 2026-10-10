from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from app.db.models import ModelPricing

MILLION = Decimal("1000000")
COST_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True)
class PriceQuote:
    amount: Decimal
    currency: str
    pricing_version: str
    snapshot: dict[str, str]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
        if result.is_nan() or result.is_infinite():
            raise ValueError(f"{field} must be a finite number")
        if result < 0:
            raise ValueError(f"{field} cannot be negative")
        return result
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value for {field}: {value}") from exc


def resolve_price(
    db: Session,
    *,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = None,
    invocation_time: datetime | None = None,
) -> PriceQuote | None:
    if input_tokens is None and output_tokens is None:
        return None

    at_time = invocation_time or datetime.now(timezone.utc)

    pricing = (
        db.query(ModelPricing)
        .filter(
            ModelPricing.provider == provider,
            ModelPricing.model == model,
            ModelPricing.effective_from <= at_time,
            or_(
                ModelPricing.effective_until.is_(None),
                ModelPricing.effective_until > at_time,
            ),
        )
        .order_by(ModelPricing.effective_from.desc())
        .first()
    )

    if not pricing:
        return None

    inp_rate = _decimal(pricing.input_rate_per_million, "input_rate_per_million")
    out_rate = _decimal(pricing.output_rate_per_million, "output_rate_per_million")
    cached_rate = (
        _decimal(pricing.cached_input_rate_per_million, "cached_input_rate_per_million")
        if pricing.cached_input_rate_per_million is not None
        else None
    )

    regular_input = Decimal(max(0, input_tokens or 0))
    cached_input = Decimal(max(0, cached_input_tokens or 0)) if cached_rate is not None else Decimal(0)
    if cached_rate is not None and regular_input >= cached_input:
        billed_input = regular_input - cached_input
    else:
        billed_input = regular_input
        cached_input = Decimal(0)

    output = Decimal(max(0, output_tokens or 0))

    cost_input = (billed_input * inp_rate) / MILLION
    cost_cached = (cached_input * cached_rate) / MILLION if cached_rate is not None else Decimal(0)
    cost_output = (output * out_rate) / MILLION

    total_cost = (cost_input + cost_cached + cost_output).quantize(COST_QUANTUM, rounding=ROUND_HALF_EVEN)

    snapshot = {
        "input_rate_per_million": str(inp_rate),
        "output_rate_per_million": str(out_rate),
        "currency": pricing.currency,
        "pricing_version": pricing.pricing_version,
    }
    if cached_rate is not None:
        snapshot["cached_input_rate_per_million"] = str(cached_rate)

    return PriceQuote(
        amount=total_cost,
        currency=pricing.currency,
        pricing_version=pricing.pricing_version,
        snapshot=snapshot,
    )
