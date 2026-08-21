"""Full-text search across every converted document."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import search as search_service

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchHit(BaseModel):
    job_id: str
    file_id: str
    filename: str
    snippet: str


@router.get("", response_model=list[SearchHit])
async def search(
    q: str = Query("", max_length=200),
    limit: int = Query(25, ge=1, le=100),
) -> list[SearchHit]:
    """Search the Markdown of every completed conversion.

    An empty or whitespace-only query returns nothing rather than everything:
    a blank search box should not dump the whole library.
    """
    return [SearchHit(**hit) for hit in search_service.search(q.strip(), limit)]
