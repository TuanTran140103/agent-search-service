from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.models.search import SearchByNameRequest, VectorSearchRequest
from src.services.search_service import search_service


class SearchByNameInput(BaseModel):
    query_text: str = Field(
        description="Search query string for fuzzy matching against document file names. Supports partial and similar name matching."
    )
    dataset_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional list of dataset IDs to restrict the search. If not provided, searches all datasets the user has access to.",
    )


class VectorSearchInput(BaseModel):
    query_text: str = Field(
        description="Natural language query for semantic search across document content. Describes the information you want to find."
    )
    dataset_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional list of dataset IDs to restrict the search. Also used as shard key for Qdrant routing.",
    )
    top_k: int = Field(
        default=10,
        description="Maximum number of search results to return. Default is 10.",
    )
    score_threshold: float = Field(
        default=0.3,
        description="Minimum similarity score threshold (0.0 to 1.0). Results below this threshold are filtered out.",
    )
    metadata_filter: Optional[dict] = Field(
        default=None,
        description="Optional metadata filter, e.g. {\"documentType\": \"Báo cáo\", \"year\": 2025}. Supports string, integer, float, and boolean values.",
    )


class ReadDocumentInput(BaseModel):
    document_id: str = Field(
        description="The unique ID (GUID) of the document to read."
    )
    content_type: Optional[str] = Field(
        default=None,
        description="Type of content to retrieve: 'summary' for document summary, 'fullContent' for full OCR text, or None for metadata only.",
    )


class ListDatasetDocumentsInput(BaseModel):
    dataset_id: str = Field(
        description="The unique ID (GUID) of the dataset whose documents should be listed."
    )


@tool(args_schema=SearchByNameInput)
async def search_by_name(
    query_text: str,
    dataset_ids: Optional[list[str]] = None,
) -> str:
    """Fuzzy search documents by file name using trigram similarity.
    Use this when the user knows part of the document name or wants to find documents by name."""
    req = SearchByNameRequest(queryText=query_text, datasetIds=dataset_ids)
    results = await search_service.search_by_name(req)
    return json.dumps([r.model_dump() for r in results], ensure_ascii=False)


@tool(args_schema=VectorSearchInput)
async def vector_search(
    query_text: str,
    dataset_ids: Optional[list[str]] = None,
    top_k: int = 10,
    score_threshold: float = 0.3,
    metadata_filter: Optional[dict] = None,
) -> str:
    """Semantic search across document content using vector embeddings.
    Use this to find information within documents based on meaning and context, not just keywords.
    Returns relevant document chunks with similarity scores."""
    req = VectorSearchRequest(
        queryText=query_text,
        datasetIds=dataset_ids,
        topK=top_k,
        scoreThreshold=score_threshold,
        metadataFilter=metadata_filter,
    )
    results = await search_service.vector_search(req)
    return json.dumps([r.model_dump() for r in results], ensure_ascii=False)


@tool(args_schema=ReadDocumentInput)
async def read_document(
    document_id: str,
    content_type: Optional[str] = None,
) -> str:
    """Read the full content or summary of a specific document by its ID.
    Use content_type='summary' to get a concise summary, 'fullContent' for the complete OCR-extracted text,
    or leave content_type unset to retrieve document metadata without content."""
    result = await search_service.read_document(document_id, content_type)
    return json.dumps(result.model_dump(), ensure_ascii=False)


@tool(args_schema=ListDatasetDocumentsInput)
async def list_dataset_documents(dataset_id: str) -> str:
    """List all documents available in a specific dataset.
    Use this to browse what documents exist in a dataset before searching."""
    results = await search_service.list_dataset_documents(dataset_id)
    return json.dumps([r.model_dump() for r in results], ensure_ascii=False)


SEARCH_TOOLS = [search_by_name, vector_search, read_document, list_dataset_documents]
