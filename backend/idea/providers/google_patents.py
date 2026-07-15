from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from ..cache import CacheStore
from ..config import GooglePatentsSettings
from .base import FetchRequest, FetchedDocument, SearchHit, SearchProvider, SearchQuery


HttpGetter = Callable[[str], Awaitable[bytes]]


def _classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


class _GoogleSearchParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.records: list[dict[str, str]] = []
        self.record: dict[str, str] | None = None
        self.depth = 0
        self.capture: str | None = None
        self.capture_tag: str | None = None

    def handle_starttag(self, tag: str, attrs_list):
        attrs = dict(attrs_list)
        classes = _classes(attrs)
        if self.record is None and (
            (tag == "article" and "result" in classes) or tag == "search-result-item"
        ):
            self.record = {}
            self.depth = 1
        elif self.record is not None:
            self.depth += 1

        if self.record is None:
            return
        if tag == "a" and "/patent/" in (attrs.get("href") or ""):
            href = attrs.get("href") or ""
            self.record.setdefault("url", urljoin(self.base_url, href))
            publication = _publication_from_url(href)
            if publication:
                self.record.setdefault("publication_number", publication)
        field = self._field(tag, classes)
        if field:
            if field in {
                "publication_number",
                "application_number",
                "priority_date",
                "filing_date",
                "publication_date",
                "assignee",
            }:
                self.record[field] = ""
            self.capture = field
            self.capture_tag = tag

    def handle_endtag(self, tag: str):
        if self.record is None:
            return
        if self.capture_tag == tag:
            self.capture = None
            self.capture_tag = None
        self.depth -= 1
        if self.depth == 0:
            if self.record.get("url") or self.record.get("publication_number"):
                self.records.append(self.record)
            self.record = None

    def handle_data(self, data: str):
        if self.record is None or self.capture is None:
            return
        text = " ".join(data.split())
        if not text:
            return
        previous = self.record.get(self.capture, "")
        self.record[self.capture] = f"{previous} {text}".strip()

    @staticmethod
    def _field(tag: str, classes: set[str]) -> str | None:
        if tag == "h3" or "title" in classes:
            return "title"
        mapping = {
            "publication-number": "publication_number",
            "application-number": "application_number",
            "priority-date": "priority_date",
            "filing-date": "filing_date",
            "publication-date": "publication_date",
            "assignee": "assignee",
            "abstract": "snippet",
            "snippet": "snippet",
        }
        for class_name, field in mapping.items():
            if class_name in classes:
                return field
        return None


def _publication_from_url(url: str) -> str | None:
    parts = urlparse(url).path.split("/")
    try:
        value = parts[parts.index("patent") + 1]
    except (ValueError, IndexError):
        return None
    return value.replace(" ", "").upper() or None


def parse_search_html(content: str, base_url: str) -> list[dict[str, str]]:
    parser = _GoogleSearchParser(base_url)
    parser.feed(content)
    return parser.records


class GooglePatentsProvider(SearchProvider):
    name = "google_patents_local"

    def __init__(
        self,
        settings: GooglePatentsSettings,
        *,
        cache: CacheStore | None = None,
        http_getter: HttpGetter | None = None,
    ):
        self.settings = settings
        self.cache = cache
        self.http_getter = http_getter
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0

    def build_search_url(self, query: SearchQuery) -> str:
        parameters = {
            "q": query.text,
            "num": query.limit,
            "page": max(0, query.round_number - 1),
        }
        if query.countries:
            parameters["country"] = ",".join(query.countries)
        return str(self.settings.base_url).rstrip("/") + "/?" + urlencode(parameters)

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        url = self.build_search_url(query)
        content = await self._get(url)
        records = parse_search_html(content.decode("utf-8", errors="replace"), str(self.settings.base_url))
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for record in records:
            publication = (record.get("publication_number") or "").replace(" ", "").upper()
            identity = publication or record.get("url", "")
            if not identity or identity in seen:
                continue
            seen.add(identity)
            hits.append(
                SearchHit(
                    provider=self.name,
                    provider_rank=len(hits) + 1,
                    title=record.get("title", ""),
                    url=record.get("url", ""),
                    publication_number=publication or None,
                    application_number=record.get("application_number"),
                    snippet=record.get("snippet", ""),
                    priority_date=record.get("priority_date"),
                    filing_date=record.get("filing_date"),
                    publication_date=record.get("publication_date"),
                    assignee=record.get("assignee"),
                    raw=record,
                )
            )
            if len(hits) >= query.limit:
                break
        return hits

    async def fetch(self, request: FetchRequest) -> FetchedDocument:
        raise NotImplementedError("full-text parsing is implemented by IDEA-GPAT-002")

    async def _get(self, url: str) -> bytes:
        cache_key = f"gpat:http:{url}"
        if self.cache is not None:
            try:
                with self.cache.lease(cache_key) as path:
                    return path.read_bytes()
            except KeyError:
                pass

        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                await self._wait_for_rate_limit()
                if self.http_getter is not None:
                    content = await self.http_getter(url)
                else:
                    content = await self._http_get_with_proxy_fallback(url)
                if self.cache is not None:
                    self.cache.put_bytes(cache_key, "searches", content)
                return content
            except Exception as exc:
                last_error = exc
                if attempt < self.settings.max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))
        assert last_error is not None
        raise last_error

    async def _http_get_with_proxy_fallback(self, url: str) -> bytes:
        try:
            return await self._http_get(url, trust_env=self.settings.trust_environment_proxy)
        except (ImportError, httpx.ProxyError, httpx.ConnectError):
            if not self.settings.fallback_to_direct or not self.settings.trust_environment_proxy:
                raise
            return await self._http_get(url, trust_env=False)

    async def _http_get(self, url: str, *, trust_env: bool) -> bytes:
        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            headers={"User-Agent": self.settings.user_agent},
            follow_redirects=True,
            trust_env=trust_env,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            wait = self.settings.min_request_interval_seconds - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()
