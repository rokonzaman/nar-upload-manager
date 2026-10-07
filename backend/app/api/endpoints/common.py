"""Shared helpers for endpoints."""

import math
from typing import Any, List, TypeVar

from app.schemas.schemas import Page

T = TypeVar("T")


def paginate(query, page: int, page_size: int) -> Page[Any]:
    """Execute a SQLAlchemy query with offset/limit and wrap in a Page."""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    total = query.count()
    items: List[Any] = query.offset((page - 1) * page_size).limit(page_size).all()
    return Page(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )
