from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from idea.cache import CacheStore
from idea.config import load_config
from idea.database import Database
from idea.providers import (
    ExaMcpProvider,
    FetchRequest,
    McpHttpClient,
    ProviderRunner,
    ProviderStatus,
    SearchQuery,
)


class McpProtocolTests(unittest.TestCase):
    def test_initialize_notification_and_tool_call_share_session(self) -> None:
        calls = []

        async def transport(payload, headers):
            calls.append((payload, headers))
            if payload["method"] == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"protocolVersion": "2025-03-26", "capabilities": {}},
                }, {"mcp-session-id": "session-1"}
            if payload["method"] == "notifications/initialized":
                return {}, {}
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"content": [{"type": "text", "text": "ok"}]},
            }, {}

        client = McpHttpClient("https://mcp.example.test", timeout_seconds=1, transport=transport)
        result = asyncio.run(client.call_tool("web_search_exa", {"query": "patent"}))
        self.assertEqual(result["content"][0]["text"], "ok")
        self.assertEqual([item[0]["method"] for item in calls], [
            "initialize", "notifications/initialized", "tools/call"
        ])
        self.assertEqual(calls[1][1]["Mcp-Session-Id"], "session-1")
        self.assertEqual(calls[2][0]["params"]["name"], "web_search_exa")

    def test_sse_decoder_extracts_json_data(self) -> None:
        payload = b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
        result = McpHttpClient._decode(payload, "text/event-stream")
        self.assertEqual(result["id"], 1)


class ExaProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.settings = load_config().search.providers.exa_mcp.model_copy(
            update={"max_attempts": 1}
        )
        self.calls = []

        async def caller(tool, arguments):
            self.calls.append((tool, arguments))
            if tool == self.settings.search_tool:
                return {
                    "structuredContent": {
                        "results": [
                            {
                                "title": "Cache affinity based scheduling",
                                "url": "https://patents.google.com/patent/EP0965918A2/en",
                                "text": "Measure cache footprint and thread affinity.",
                                "publishedDate": "1999-12-22",
                            },
                            {
                                "title": "Duplicate family result",
                                "url": "https://patents.google.com/patent/EP0965918A2/en",
                                "text": "duplicate",
                            },
                        ]
                    }
                }
            return {"content": [{"type": "text", "text": "Fetched patent content"}]}

        self.caller = caller

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def query():
        return SearchQuery(
            query_id="Q-EXA-1",
            text="cache scheduling",
            round_number=1,
            limit=10,
            query_type="technical_means",
        )

    def test_structured_search_results_are_normalized_and_deduplicated(self) -> None:
        provider = ExaMcpProvider(self.settings, caller=self.caller)
        hits = asyncio.run(provider.search(self.query()))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].publication_number, "EP0965918A2")
        self.assertEqual(hits[0].provider, "exa_mcp")
        self.assertIn("site:patents.google.com/patent", self.calls[0][1]["query"])

    def test_json_text_result_is_supported(self) -> None:
        async def json_caller(tool, arguments):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"results": [{
                            "title": "Patent", "url": "https://patents.google.com/patent/US1A1/en"
                        }]}),
                    }
                ]
            }

        hits = asyncio.run(ExaMcpProvider(self.settings, caller=json_caller).search(self.query()))
        self.assertEqual(hits[0].publication_number, "US1A1")

    def test_fetch_returns_traceable_fallback_document(self) -> None:
        provider = ExaMcpProvider(self.settings, caller=self.caller)
        request = FetchRequest(request_id="F-EXA-1", publication_number="EP0965918A2")
        result = asyncio.run(ProviderRunner().fetch(provider, request, timeout_seconds=1))
        self.assertEqual(result.status, ProviderStatus.SUCCESS)
        self.assertIn("Fetched patent content", result.document.description_text)
        self.assertFalse(result.document.raw_metadata["structured_sections"])

    def test_mcp_failure_is_not_success(self) -> None:
        async def failing(tool, arguments):
            raise ConnectionError("MCP down")

        provider = ExaMcpProvider(self.settings, caller=failing)
        result = asyncio.run(
            ProviderRunner().search(provider, self.query(), timeout_seconds=1)
        )
        self.assertEqual(result.status, ProviderStatus.ERROR)
        self.assertFalse(result.succeeded)

    def test_tool_response_cache_prevents_duplicate_call(self) -> None:
        root = Path(self.temp.name)
        database = Database(root / "idea.db")
        database.initialize()
        cache = CacheStore(root / "cache", database, max_bytes=1_000_000, low_watermark_bytes=900_000)
        provider = ExaMcpProvider(self.settings, cache=cache, caller=self.caller)
        asyncio.run(provider.search(self.query()))
        asyncio.run(provider.search(self.query()))
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
