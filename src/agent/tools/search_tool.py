from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, Field

from src.models.search import (
    DocumentDetail,
    DocumentRef,
    SearchByNameRequest,
    VectorSearchRequest,
    VectorSearchResult,
)
from src.services.search_service import search_service


class SearchByNameInput(BaseModel):
    query_text: str = Field(
        description="Search query string for fuzzy matching against document file names. Supports partial and similar name matching."
    )


class VectorSearchInput(BaseModel):
    query_text: str = Field(
        description="Natural language query for semantic search across document content. Describes the information you want to find."
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


class GetDocumentsInput(BaseModel):
    n: int = Field(
        default=10,
        description="Number of most recently accessed documents to return. Maximum is 50.",
    )


@tool(args_schema=SearchByNameInput)
async def search_by_name(
    query_text: str,
    runtime: ToolRuntime,
) -> list[DocumentRef]:
    """Fuzzy search documents by file name using trigram similarity.
    Use this when the user knows part of the document name or wants to find documents by name."""
    dataset_ids = runtime.config["configurable"].get("dataset_ids")
    req = SearchByNameRequest(queryText=query_text, datasetIds=dataset_ids)
    results = await search_service.search_by_name(req)
    return [r.model_dump(mode="json") for r in results]


@tool(args_schema=VectorSearchInput)
async def vector_search(
    query_text: str,
    runtime: ToolRuntime,
    top_k: int = 10,
    score_threshold: float = 0.3,
    metadata_filter: Optional[dict] = None,
) -> list[VectorSearchResult]:
    """Semantic search across document content using vector embeddings.
    Use this to find information within documents based on meaning and context, not just keywords.
    Returns relevant document chunks with similarity scores."""
    dataset_ids = runtime.config["configurable"].get("dataset_ids")
    req = VectorSearchRequest(
        queryText=query_text,
        datasetIds=dataset_ids,
        topK=top_k,
        scoreThreshold=score_threshold,
        metadataFilter=metadata_filter,
    )
    results = await search_service.vector_search(req)
    return [r.model_dump(mode="json") for r in results]


@tool(args_schema=ReadDocumentInput)
async def read_document(
    document_id: str,
    content_type: Optional[str] = None,
) -> DocumentDetail:
    """Read the full content or summary of a specific document by its ID.
    Use content_type='summary' to get a concise summary, 'fullContent' for the complete OCR-extracted text,
    or leave content_type unset to retrieve document metadata without content."""
    result = await search_service.read_document(document_id, content_type)
    return result.model_dump(mode="json")


@tool(args_schema=GetDocumentsInput)
async def get_documents(
    n: int,
    runtime: ToolRuntime,
) -> list[DocumentRef]:
    """Retrieve the most recently accessed documents across the user's datasets.
    Use this to browse recent documents or find documents the user has worked with."""
    dataset_ids = runtime.config["configurable"].get("dataset_ids")
    results = await search_service.get_recent_documents(n=n, dataset_ids=dataset_ids)
    return [r.model_dump(mode="json") for r in results]


SEARCH_TOOLS = [search_by_name, vector_search, read_document, get_documents]

# ── LangChain 1.4.0 workaround: _injected_args_keys returns empty set on
#    StructuredTool, causing ToolRuntime to be dropped by _parse_input after
#    schema validation.  Manually populate the cached property so that
#    _parse_input preserves injected runtime/state keys.
from langgraph.prebuilt.tool_node import _get_all_injected_args
for _t in SEARCH_TOOLS:
    _injected = _get_all_injected_args(_t)
    _keys = set()
    if _injected.state:
        _keys.update(_injected.state)
    if _injected.store:
        _keys.add(_injected.store)
    if _injected.runtime:
        _keys.add(_injected.runtime)
    _t._injected_args_keys = frozenset(_keys)
