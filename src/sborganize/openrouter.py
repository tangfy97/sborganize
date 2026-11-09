"""Explicit opt-in cloud refinement. No redirects, proxies, retries or model fallbacks."""

import http.client
import json
import os

DEFAULT_MODEL = "qwen/qwen3.5-flash-02-23"


def placement_schema(targets: list[str]) -> dict:
    properties = {
        "purpose_known": {"type": "boolean"},
        "domain": {"type": "string", "minLength": 1, "maxLength": 80},
        "region": {"type": "string", "enum": ["CN", "HK", "GLOBAL", "unknown"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "target": {"type": "string", "enum": targets},
        "reason": {"type": "string", "minLength": 1, "maxLength": 160},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class OpenRouterUnavailable(RuntimeError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OpenRouterUnavailable("Model JSON contains duplicate object keys.")
        result[key] = value
    return result


class OpenRouterProvider:
    def __init__(self, model: str = DEFAULT_MODEL, *, api_key: str | None = None):
        self.model = model
        self._key = (
            api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        ).strip()

    def probe(self) -> dict:
        return {
            "available": bool(self._key),
            "reason": "configured" if self._key else "key_missing",
            "detail": f"OpenRouter opt-in · {self.model}"
            if self._key
            else "Set OPENROUTER_API_KEY locally; do not paste it into chat.",
        }

    def classify(self, request: dict) -> dict:
        if not self._key:
            raise OpenRouterUnavailable("OPENROUTER_API_KEY is not set.")
        return self._generate(request, placement_schema(request["targets"]), 256)

    def review_batch(self, request: dict) -> dict:
        item = placement_schema(request["targets"])
        schema = {
            "type": "object",
            "properties": {
                "placements": {
                    "type": "object",
                    "properties": {app_id: item for app_id in request["app_ids"]},
                    "required": request["app_ids"],
                    "additionalProperties": False,
                }
            },
            "required": ["placements"],
            "additionalProperties": False,
        }
        return self._generate(request, schema, 4096)

    def _generate(self, request: dict, schema: dict, max_tokens: int) -> dict:
        if not self._key:
            raise OpenRouterUnavailable("OPENROUTER_API_KEY is not set.")
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "reasoning": {"enabled": False},
            "messages": [
                {"role": "system", "content": request["instructions"]},
                {"role": "user", "content": request["prompt"]},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "Placement",
                    "strict": True,
                    "schema": schema,
                },
            },
            "provider": {
                "require_parameters": True,
                "data_collection": "deny",
                "allow_fallbacks": False,
            },
        }
        connection = http.client.HTTPSConnection("openrouter.ai", timeout=45)
        try:
            connection.request(
                "POST",
                "/api/v1/chat/completions",
                json.dumps(body),
                {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            raw = response.read(65537)
            if response.status != 200:
                detail = ""
                try:
                    message = json.loads(raw).get("error", {}).get("message", "")
                    if isinstance(message, str):
                        detail = message.replace(self._key, "[redacted]")[:300]
                except (ValueError, AttributeError):
                    pass
                raise OpenRouterUnavailable(
                    f"OpenRouter request failed (HTTP {response.status}). {detail}".strip()
                )
            if len(raw) > 65536:
                raise OpenRouterUnavailable("OpenRouter returned an oversized response.")
            data = json.loads(raw)
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise OpenRouterUnavailable("OpenRouter response was incomplete.")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise OpenRouterUnavailable("OpenRouter returned no JSON message content.")
            content = content.replace(self._key, "[redacted]")
            return json.loads(content, object_pairs_hook=unique_object)
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
        ) as exc:
            raise OpenRouterUnavailable("OpenRouter request or JSON response failed.") from exc
        finally:
            connection.close()
