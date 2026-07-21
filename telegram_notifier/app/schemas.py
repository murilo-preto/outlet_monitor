"""Request/response models for the HTTP API."""

from __future__ import annotations

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
