from .base import (
    FetchRequest,
    FetchedDocument,
    ProviderResult,
    ProviderRunner,
    ProviderStatus,
    SearchHit,
    SearchProvider,
    SearchQuery,
)
from .google_patents import GooglePatentsProvider, parse_search_html

__all__ = [
    "FetchRequest",
    "FetchedDocument",
    "ProviderResult",
    "ProviderRunner",
    "ProviderStatus",
    "SearchHit",
    "SearchProvider",
    "SearchQuery",
    "GooglePatentsProvider",
    "parse_search_html",
]
