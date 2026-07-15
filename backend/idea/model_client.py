from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from .agent_schemas import AgentModel, agent_json_schema, validate_agent_output
from .config import ModelSettings


ModelTransport = Callable[[dict[str, Any], dict[str, str]], Awaitable[dict[str, Any]]]


class ModelClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentCallResult:
    agent_name: str
    model: str
    output: AgentModel
    attempts: int
    duration_ms: int
    usage: dict[str, int]
    response_id: str | None


class StructuredModelClient:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        transport: ModelTransport | None = None,
    ):
        self.settings = settings
        self.transport = transport or self._http_transport

    async def complete(
        self,
        agent_name: str,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
    ) -> AgentCallResult:
        schema = agent_json_schema(agent_name)
        messages = [
            {
                "role": "system",
                "content": (
                    system_prompt.strip()
                    + "\n\nReturn only one JSON object that validates against the supplied JSON Schema. "
                    "Do not use markdown fences. Do not invent tool calls or evidence IDs."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"input": input_payload, "output_schema": schema},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        started = time.monotonic()
        errors = []
        total_attempts = self.settings.structured_output_retries + 1
        for attempt in range(1, total_attempts + 1):
            response = await self.transport(self._payload(messages), self._headers())
            try:
                content = self._content(response)
                parsed = json.loads(self._strip_fence(content))
                output = validate_agent_output(agent_name, parsed)
                usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
                return AgentCallResult(
                    agent_name=agent_name,
                    model=self.settings.default,
                    output=output,
                    attempts=attempt,
                    duration_ms=round((time.monotonic() - started) * 1000),
                    usage={
                        key: int(value)
                        for key, value in usage.items()
                        if isinstance(value, (int, float))
                    },
                    response_id=response.get("id"),
                )
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
                errors.append(f"{type(exc).__name__}: {str(exc)[:400]}")
                if attempt >= total_attempts:
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": self._safe_previous_content(response),
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous JSON failed validation. Correct the structure and return only JSON. "
                            f"Validation summary: {errors[-1]}"
                        ),
                    }
                )
        raise ModelClientError(
            f"structured output failed after {total_attempts} attempts: {' | '.join(errors)}"
        )

    def api_key(self) -> str:
        key = os.environ.get(self.settings.api_key_env, "").strip()
        if key:
            return key
        try:
            auth = json.loads(self.settings.auth_file.read_text(encoding="utf-8-sig"))
            key = str(auth.get(self.settings.auth_provider, {}).get("apiKey") or "").strip()
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelClientError("model credential file is missing or invalid") from exc
        if not key:
            raise ModelClientError("model credential is not configured")
        return key

    def _payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "model": self.settings.default,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_output_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
        }

    async def _http_transport(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        try:
            return await self._post(payload, headers, trust_env=True)
        except (ImportError, httpx.ProxyError, httpx.ConnectError):
            return await self._post(payload, headers, trust_env=False)

    async def _post(
        self, payload: dict[str, Any], headers: dict[str, str], *, trust_env: bool
    ) -> dict[str, Any]:
        url = str(self.settings.base_url).rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            trust_env=trust_env,
            follow_redirects=True,
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        try:
            value = response.json()
        except json.JSONDecodeError as exc:
            raise ModelClientError("model response is not JSON") from exc
        if not isinstance(value, dict):
            raise ModelClientError("model response root is not an object")
        return value

    @staticmethod
    def _content(response: dict[str, Any]) -> str:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelClientError("model response has no assistant content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelClientError("model assistant content is empty")
        return content

    @staticmethod
    def _safe_previous_content(response: dict[str, Any]) -> str:
        try:
            content = StructuredModelClient._content(response)
        except ModelClientError:
            return "{}"
        return content[:12000]

    @staticmethod
    def _strip_fence(content: str) -> str:
        stripped = content.strip()
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        return match.group(1).strip() if match else stripped
