"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PriceChange(BaseModel):
    name: str = Field(..., min_length=1, description="Product name")
    new_price: float = Field(..., description="Current price")
    old_price: float | None = Field(
        None, description="Previous price. Omit for newly listed products."
    )
    url: str | None = Field(None, description="Optional product link")
    category: str | None = Field(
        None,
        description=(
            "Product line this belongs to, e.g. 'Yoga' or 'V Series'. Drives the "
            "filter menu. Falls back to guessing from the name when omitted."
        ),
    )
    event: Literal["price", "new", "relisted"] | None = Field(
        None,
        description=(
            "What happened: a price move, a first-ever listing, or a product "
            "returning to the outlet after being sold out. Only the caller "
            "knows — inferred from old_price when omitted."
        ),
    )
    all_time_low: bool | None = Field(
        None,
        description=(
            "Whether this is the cheapest the product has ever been recorded "
            "at. None means there is not enough price history to tell, which "
            "is not the same as False — only the caller keeps that history."
        ),
    )


class NotifyRequest(BaseModel):
    changes: list[PriceChange] = Field(..., min_length=1)
    title: str | None = Field(None, description="Optional custom report header")


class NotifyResponse(BaseModel):
    subscribers: int
    sent: int
    skipped: int  # subscribers whose filters matched nothing in this payload
    failed: int
    removed: int


class CountResponse(BaseModel):
    count: int


class AlertRequest(BaseModel):
    """An operational message for the operator, not a price report."""

    text: str = Field(..., min_length=1)
    level: Literal["warning", "error"] = "warning"


class AlertResponse(BaseModel):
    # 0 when no admin chat is configured, which is a valid state, not an error.
    sent: int
