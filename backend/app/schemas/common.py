# ── app/schemas/common.py ────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar("T")

class PageResponse(BaseModel, Generic[T]):
    data: List[T]
    total: int
    page: int
    page_size: int

class MsgResponse(BaseModel):
    detail: str
