"""
OpenRouter LLM engine for conv-proxy.

Supports streaming, cancellation, tool calling, and multiple models.
Default: openai/gpt-oss-120b (free, 131K context, excellent tool calling).
"""
from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Generator, Optional, Any

import requests


@dataclass
class OpenRouterEngine:
    """OpenRouter API engine with streaming and tool support."""

    api_key: str = ""
    model: str = "openai/gpt-oss-120b"
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    reasoning: bool = True
    temperature: float = 0.3
    max_tokens: int = 200

    # Internal state
    _session: Optional[requests.Session] = field(default=None, repr=False)
    _cancel_event: Optional[threading.Event] = field(default=None, repr=False)
    _active_response: Optional[requests.Response] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://conv-proxy.local",
        })

    @property
    def headers(self) -> dict:
        return self._session.headers

    def _build_payload(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "stream": stream,
        }
        if self.reasoning:
            payload["reasoning"] = {"enabled": True}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        return payload

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict:
        """
        Non-streaming chat. Returns full message dict including tool_calls.

        Returns: {
            "content": str,
            "tool_calls": list[dict] | None,
            "reasoning": str | None,
            "latency_ms": float,
            "usage": dict,
        }
        """
        payload = self._build_payload(messages, tools, stream=False, **kwargs)
        t0 = time.monotonic()
        resp = self._session.post(self.base_url, json=payload, timeout=30)
        latency = (time.monotonic() - t0) * 1000

        data = resp.json()
        if "error" in data:
            err = data["error"]
            # Auto-retry on rate limit (once)
            if err.get("code") == 429 and not kwargs.get("_retried"):
                import time as _t
                _t.sleep(2)
                return self.chat(messages, tools, _retried=True, **kwargs)
            raise RuntimeError(f"OpenRouter error: {err}")

        choice = data["choices"][0]
        msg = choice["message"]

        return {
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
            "reasoning": msg.get("reasoning_content") or msg.get("reasoning"),
            "latency_ms": latency,
            "usage": data.get("usage", {}),
        }

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        cancel_event: threading.Event | None = None,
        **kwargs,
    ) -> Generator[dict, None, None]:
        """
        Streaming chat. Yields delta dicts:
        - {"type": "content", "text": str}
        - {"type": "tool_call", "index": int, "name": str, "arguments": str}
        - {"type": "tool_call_delta", "index": int, "arguments": str}
        - {"type": "reasoning", "text": str}
        - {"type": "done", "finish_reason": str}
        - {"type": "error", "message": str}

        Set cancel_event to abort mid-stream.
        """
        payload = self._build_payload(messages, tools, stream=True, **kwargs)
        self._cancel_event = cancel_event or threading.Event()

        with self._lock:
            resp = self._session.post(
                self.base_url, json=payload, stream=True, timeout=30
            )
            self._active_response = resp

        try:
            if resp.status_code != 200:
                err = resp.json()
                yield {"type": "error", "message": str(err.get("error", {}).get("message", resp.text))}
                return

            # Track tool call assembly
            tool_calls: dict[int, dict] = {}

            for line in resp.iter_lines():
                if self._cancel_event.is_set():
                    yield {"type": "cancelled"}
                    return

                if not line:
                    continue

                text = line.decode("utf-8")
                if not text.startswith("data: "):
                    continue

                data_str = text[6:]
                if data_str == "[DONE]":
                    yield {"type": "done", "finish_reason": "stop"}
                    return

                try:
                    parsed = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "error" in parsed:
                    yield {"type": "error", "message": parsed["error"].get("message", "")}
                    return

                choices = parsed.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                finish = choices[0].get("finish_reason")

                # Content delta
                content = delta.get("content")
                if content:
                    yield {"type": "content", "text": content}

                # Reasoning delta
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}

                # Tool call deltas
                tc_deltas = delta.get("tool_calls", [])
                for tc in tc_deltas:
                    idx = tc.get("index", 0)
                    fn = tc.get("function", {})

                    if idx not in tool_calls:
                        tool_calls[idx] = {"name": fn.get("name", ""), "arguments": ""}

                    if fn.get("name"):
                        tool_calls[idx]["name"] = fn["name"]

                    if fn.get("arguments"):
                        tool_calls[idx]["arguments"] += fn["arguments"]

                if finish:
                    # Emit assembled tool calls
                    if finish == "tool_calls":
                        for idx in sorted(tool_calls.keys()):
                            tc_data = tool_calls[idx]
                            # Fix missing opening brace (some providers strip it in streaming)
                            args = tc_data["arguments"].strip()
                            if args and not args.startswith("{"):
                                args = "{" + args
                            yield {
                                "type": "tool_call",
                                "index": idx,
                                "name": tc_data["name"],
                                "arguments": args,
                            }
                    yield {"type": "done", "finish_reason": finish}
                    return

        finally:
            with self._lock:
                if self._active_response:
                    self._active_response.close()
                    self._active_response = None

    def cancel(self):
        """Cancel the active streaming request."""
        if self._cancel_event:
            self._cancel_event.set()
        with self._lock:
            if self._active_response:
                self._active_response.close()
                self._active_response = None

    def close(self):
        """Clean up session."""
        if self._session:
            self._session.close()
