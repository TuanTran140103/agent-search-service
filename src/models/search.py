from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SearchByNameRequest(BaseModel):
    queryText: str
    datasetIds: Optional[list[str]] = None


class DocumentRef(BaseModel):
    documentId: str
    datasetId: str
    fileName: str


class MetadataFilter(BaseModel):
    pass


class VectorSearchRequest(BaseModel):
    queryText: str
    datasetIds: Optional[list[str]] = None
    metadataFilter: Optional[dict] = None
    scoreThreshold: float = 0.3
    topK: int = 10


class VectorSearchResult(BaseModel):
    documentId: str
    datasetId: str
    fileName: str
    content: Optional[str] = None
    chunkType: Optional[str] = None
    score: float


class DocumentDetail(BaseModel):
    documentId: str
    datasetId: str
    fileName: str
    content: Optional[str] = None
    contentType: Optional[str] = None
