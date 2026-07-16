from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from idea.config import load_config
from idea.model_client import ModelClientError, StructuredModelClient, runtime_api_key


def valid_parser_output():
    return {
        "title": "Cache scheduling",
        "technical_domains": ["computer storage"],
        "application_scenario": "data center",
        "technical_problem": "reduce cache misses",
        "features": [
            {
                "feature_id": "F1",
                "feature_text": "schedule jobs using cache locality",
                "source_type": "explicit",
                "source_span": {"start": 0, "end": 10, "text": "cache idea"},
                "required": True,
            }
        ],
        "claimed_effects": ["fewer cache misses"],
        "subject_types": ["method"],
        "scope_breadth": "narrow",
        "assignee_focus": [],
        "inferred_items": [],
    }


class StructuredModelClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        auth = Path(self.temp.name) / "auth.json"
        auth.write_text(json.dumps({"agent-plan": {"apiKey": "test-secret"}}), encoding="utf-8")
        self.settings = load_config().model.model_copy(
            update={"auth_file": auth, "structured_output_retries": 1}
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_response_is_parsed_and_schema_validated(self) -> None:
        calls = []

        async def transport(payload, headers):
            calls.append((payload, headers))
            return {
                "id": "response-1",
                "choices": [{"message": {"content": json.dumps(valid_parser_output())}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }

        result = asyncio.run(
            StructuredModelClient(self.settings, transport=transport).complete(
                "patent-idea-parser", system_prompt="Parse the idea.", input_payload={"idea": "cache idea"}
            )
        )
        self.assertEqual(result.output.features[0].feature_id, "F1")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.usage["completion_tokens"], 20)
        self.assertEqual(calls[0][0]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0][1]["Authorization"], "Bearer test-secret")

    def test_invalid_json_retries_with_validation_summary(self) -> None:
        responses = ["not-json", json.dumps(valid_parser_output())]
        payloads = []

        async def transport(payload, headers):
            payloads.append(payload)
            return {"choices": [{"message": {"content": responses.pop(0)}}]}

        result = asyncio.run(
            StructuredModelClient(self.settings, transport=transport).complete(
                "patent-idea-parser", system_prompt="Parse.", input_payload={"idea": "cache"}
            )
        )
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(payloads[1]["messages"]), 4)
        self.assertIn("failed validation", payloads[1]["messages"][-1]["content"])

    def test_schema_invalid_output_exhausts_retry_without_leaking_key(self) -> None:
        async def transport(payload, headers):
            return {"choices": [{"message": {"content": "{}"}}]}

        with self.assertRaises(ModelClientError) as caught:
            asyncio.run(
                StructuredModelClient(self.settings, transport=transport).complete(
                    "patent-idea-parser", system_prompt="Parse.", input_payload={"idea": "cache"}
                )
            )
        self.assertNotIn("test-secret", str(caught.exception))

    def test_markdown_json_fence_is_tolerated_deterministically(self) -> None:
        async def transport(payload, headers):
            content = "```json\n" + json.dumps(valid_parser_output()) + "\n```"
            return {"choices": [{"message": {"content": content}}]}

        result = asyncio.run(
            StructuredModelClient(self.settings, transport=transport).complete(
                "patent-idea-parser", system_prompt="Parse.", input_payload={"idea": "cache"}
            )
        )
        self.assertEqual(result.output.title, "Cache scheduling")

    def test_missing_credential_fails_before_transport(self) -> None:
        settings = self.settings.model_copy(update={"auth_file": Path(self.temp.name) / "missing.json"})
        with self.assertRaisesRegex(ModelClientError, "credential"):
            StructuredModelClient(settings).api_key()

    def test_runtime_key_overrides_disk_only_inside_context(self) -> None:
        client = StructuredModelClient(self.settings)
        self.assertEqual(client.api_key(), "test-secret")
        with runtime_api_key("ephemeral-test-token"):
            self.assertEqual(client.api_key(), "ephemeral-test-token")
        self.assertEqual(client.api_key(), "test-secret")


if __name__ == "__main__":
    unittest.main()
