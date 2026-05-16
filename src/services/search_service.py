from __future__ import annotations

import httpx
from typing import Optional
from src.core.config import settings
from src.models.search import (
    DocumentDetail,
    DocumentRef,
    SearchByNameRequest,
    VectorSearchRequest,
    VectorSearchResult,
)


class SearchService:
    def __init__(self):
        self.base_url = settings.search_api_base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def search_by_name(self, req: SearchByNameRequest) -> list[DocumentRef]:
        client = await self._get_client()
        resp = await client.post(
            "/documents/by-name",
            json=req.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return [DocumentRef(**item) for item in resp.json()]

    async def vector_search(self, req: VectorSearchRequest) -> list[VectorSearchResult]:
        client = await self._get_client()
        resp = await client.post(
            "/vector",
            json=req.model_dump(exclude_none=True),
        )
        resp.raise_for_status()
        return [VectorSearchResult(**item) for item in resp.json()]

    async def read_document(
        self,
        document_id: str,
        content_type: Optional[str] = None,
    ) -> DocumentDetail:
        client = await self._get_client()
        params = {}
        if content_type:
            params["contentType"] = content_type
        resp = await client.get(f"/documents/{document_id}", params=params)
        resp.raise_for_status()
        return DocumentDetail(**resp.json())

    async def list_dataset_documents(self, dataset_id: str) -> list[DocumentRef]:
        client = await self._get_client()
        resp = await client.get(f"/datasets/{dataset_id}/documents")
        resp.raise_for_status()
        return [DocumentRef(**item) for item in resp.json()]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


search_service = SearchService()
