# OpenRouter Streaming + Tool Calling Reference (Python/FastAPI proxy)

Sources:
- Streaming: https://openrouter.ai/docs/api/reference/streaming
- API Reference (overview & headers): https://openrouter.ai/docs/api/reference/overview
- Tool/Function calling guide: https://openrouter.ai/docs/guides/features/tool-calling
- Errors & debugging: https://openrouter.ai/docs/api/reference/errors-and-debugging
- Limits: https://openrouter.ai/docs/api/reference/limits
- OpenAPI schema: https://openrouter.ai/openapi.json

This is a consolidated, implementation‑ready reference focused on SSE streaming, tool calls, cancellation, errors, and rate limits. Examples are Python‑oriented for a FastAPI streaming proxy.

---

## 1) Endpoint + Auth + Optional Headers

**Endpoint:** `POST https://openrouter.ai/api/v1/chat/completions`

**Headers:**
- `Authorization: Bearer <OPENROUTER_API_KEY>`
- `Content-Type: application/json`
- Optional (identifies your app in OpenRouter rankings/UI):
  - `HTTP-Referer: <YOUR_SITE_URL>`
  - `X-Title: <YOUR_SITE_NAME>`

---

## 2) Request Body (Streaming + Tools)

OpenRouter is OpenAI‑compatible. To enable streaming, set `stream: true`.

Relevant request fields (from API reference):
```json
{
  "model": "openai/gpt-5.2",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_gutenberg_books",
        "description": "Search Gutenberg",
        "parameters": {
          "type": "object",
          "properties": {
            "search_terms": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["search_terms"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

**Tool calling note (OpenRouter docs):** the `tools` array must be included in *every* request where tool calls are possible (both the “tool request” and the “tool result” follow‑up), so the router can validate tool schema each call.

---

## 3) SSE Streaming Format

OpenRouter uses **Server‑Sent Events (SSE)** for streaming.

### 3.1 SSE Event Lines
- Data events are lines beginning with `data: `
- End‑of‑stream signal is the literal: `data: [DONE]`
- OpenRouter may send SSE **comment lines** (keep‑alive) that begin with `:`
  - Example: `: OPENROUTER PROCESSING`
  - These are valid SSE comments and **must be ignored** by JSON parsers.

### 3.2 Typical SSE Loop (Python, requests)
```python
import json, requests

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
  "Authorization": f"Bearer {OPENROUTER_API_KEY}",
  "Content-Type": "application/json",
}

payload = {
  "model": "openai/gpt-5.2",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": True,
}

buffer = ""
with requests.post(url, headers=headers, json=payload, stream=True) as r:
    for chunk in r.iter_content(chunk_size=1024, decode_unicode=True):
        buffer += chunk
        while True:
            line_end = buffer.find("\n")
            if line_end == -1:
                break
            line = buffer[:line_end].strip()
            buffer = buffer[line_end + 1:]

            if not line:
                continue
            if line.startswith(":"):
                # SSE comment / keep-alive
                continue
            if not line.startswith("data: "):
                continue

            data = line[6:]
            if data == "[DONE]":
                break

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            # streaming content is in choices[0].delta.content
            delta = event["choices"][0]["delta"]
            content = delta.get("content")
            if content:
                print(content, end="", flush=True)
```

---

## 4) Streaming Delta Structure

OpenRouter uses OpenAI‑style “chunk” events. Each SSE `data:` line is a JSON object shaped like:

```json
{
  "id": "cmpl-...",
  "object": "chat.completion.chunk",
  "created": 1234567890,
  "model": "openai/gpt-5.2",
  "provider": "openai",
  "choices": [
    {
      "index": 0,
      "delta": {
        "role": "assistant",
        "content": "partial text",
        "tool_calls": [
          {
            "index": 0,
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "search_gutenberg_books",
              "arguments": "{\"search_terms\": [\"James\", \"Joyce\"]}"
            }
          }
        ]
      },
      "finish_reason": null
    }
  ]
}
```

Key points from OpenAPI schema (`openrouter.ai/openapi.json`):
- `choices[].delta` is a **ChatStreamingMessageChunk**.
- `delta.tool_calls` is an array of **ChatStreamingMessageToolCall** objects:
  - `{ index, id?, type: "function", function: { name, arguments } }`
- `function.arguments` is a **string** (usually JSON). In streaming, it can arrive **incrementally** across multiple deltas — append the `arguments` strings by tool call index/id.

### Finish reason values
From OpenAPI (`ChatCompletionFinishReason` enum):
```
"tool_calls", "stop", "length", "content_filter", "error"
```
Commonly used in streaming:
- `tool_calls` → model is requesting tool execution
- `stop` → normal end
- `length` → hit token limit
- `content_filter` → blocked content
- `error` → mid‑stream error (see §7)

---

## 5) Tool / Function Calling (Non‑Streaming)

### Step 1 — Send tools
```json
{
  "model": "google/gemini-3-flash-preview",
  "messages": [{"role": "user", "content": "What are the titles of some James Joyce books?"}],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_gutenberg_books",
        "description": "Search for books in the Project Gutenberg library",
        "parameters": {
          "type": "object",
          "properties": {
            "search_terms": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["search_terms"]
        }
      }
    }
  ]
}
```

### Step 2 — Model returns `tool_calls` with `finish_reason: "tool_calls"`
```json
{
  "choices": [
    {
      "finish_reason": "tool_calls",
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "search_gutenberg_books",
              "arguments": "{\"search_terms\": [\"James\", \"Joyce\"]}"
            }
          }
        ]
      }
    }
  ]
}
```

### Step 3 — Return tool results (must include tools again)
```json
{
  "model": "google/gemini-3-flash-preview",
  "messages": [
    {"role": "user", "content": "What are the titles of some James Joyce books?"},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "function": {
            "name": "search_gutenberg_books",
            "arguments": "{\"search_terms\": [\"James\", \"Joyce\"]}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "[{\"id\": 4300, \"title\": \"Ulysses\"}]"
    }
  ],
  "tools": [ ...same tool schema as Step 1... ]
}
```

---

## 6) Tool Calls in **Streaming** Deltas

When streaming, tool calls appear in the **delta** field:

```json
{
  "choices": [
    {
      "delta": {
        "tool_calls": [
          {
            "index": 0,
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "search_gutenberg_books",
              "arguments": "{\"search_terms\": [\"James\""
            }
          }
        ]
      }
    }
  ]
}
```

Subsequent chunks will **continue** the same tool call (same `index`/`id`) with more `function.arguments` text:

```json
{
  "choices": [
    {
      "delta": {
        "tool_calls": [
          {
            "index": 0,
            "function": {"arguments": ", \"Joyce\"]}"}
          }
        ]
      }
    }
  ]
}
```

**Implementation notes for streaming tool calls:**
- Accumulate tool call arguments by **index** (and/or `id` once provided).
- Combine all `arguments` substrings to build a valid JSON string before parsing.
- Expect `finish_reason: "tool_calls"` at the end of tool‑request phase.

---

## 7) Error Handling (Streaming vs Non‑Streaming)

### 7.1 Pre‑stream errors (HTTP status != 200)
If an error occurs *before any tokens are sent*, OpenRouter returns standard JSON:
```json
{
  "error": {"code": 400, "message": "Invalid model specified"}
}
```
Common codes: `400`, `401`, `402`, `429`, `502`, `503`.

### 7.2 Mid‑stream errors (HTTP 200, SSE error event)
If a provider fails *after tokens already streamed*, OpenRouter cannot change status code and emits a **unified SSE error event**:
```
data: {"id":"cmpl-abc123","object":"chat.completion.chunk","created":1234567890,"model":"gpt-3.5-turbo","provider":"openai","error":{"code":"server_error","message":"Provider disconnected unexpectedly"},"choices":[{"index":0,"delta":{"content":""},"finish_reason":"error"}]}
```
Characteristics:
- Top‑level `error` object
- `choices[0].finish_reason = "error"`
- Stream ends right after this event

### 7.3 Handling in Python
```python
response = requests.post(..., stream=True)
if response.status_code != 200:
    print(response.json()["error"]["message"])
    return

for line in response.iter_lines():
    if not line:
        continue
    text = line.decode("utf-8")
    if not text.startswith("data: "):
        continue
    data = text[6:]
    if data == "[DONE]":
        break
    event = json.loads(data)
    if "error" in event:
        # mid-stream error
        print("Stream error:", event["error"]["message"])
        break
```

---

## 8) Stream Cancellation (Abort)

OpenRouter supports cancelling streaming requests by **closing/aborting** the connection. When provider supports it, this **immediately stops model processing and billing**.

Supported providers (per docs): OpenAI, Azure, Anthropic, Fireworks, Mancer, Recursal, AnyScale, Lepton, OctoAI, Novita, DeepInfra, Together, Cohere, Hyperbolic, Infermatic, Avian, XAI, Cloudflare, SFCompute, Nineteen, Liquid, Friendli, Chutes, DeepSeek.

**Not currently supported:** AWS Bedrock, Groq, Modal, Google, Google AI Studio, Minimax, HuggingFace, Replicate, Perplexity, Mistral, AI21, Featherless, Lynn, Lambda, Reflection, SambaNova, Inflection, ZeroOneAI, AionLabs, Alibaba, Nebius, Kluster, Targon, InferenceNet.

Python example (close response when canceling):
```python
from threading import Event, Thread
import requests

def stream_with_cancellation(prompt: str, cancel_event: Event):
    with requests.Session() as session:
        response = session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True},
            stream=True,
        )
        try:
            for line in response.iter_lines():
                if cancel_event.is_set():
                    response.close()  # aborts upstream
                    return
                if line:
                    print(line.decode(), end="", flush=True)
        finally:
            response.close()
```

**Warning from docs:** cancellation only works for streaming requests and supported providers. Otherwise, the model continues processing and you are billed for the full response.

---

## 9) Rate Limits + Credits

OpenRouter’s rate limits are **global per account**, not per API key. Creating more keys doesn’t increase limits. Rate limits are **model‑specific**.

To check limits/credits for a key:
```
GET https://openrouter.ai/api/v1/key
Authorization: Bearer <API_KEY>
```

Response includes:
- `limit`, `limit_remaining`, `limit_reset`
- `usage`, `usage_daily/weekly/monthly`
- `is_free_tier`

Free model limits (from docs):
- Free model variants (`:free`) are limited to a requests‑per‑minute cap and daily request caps that depend on credit purchases.
- Cloudflare DDoS protection can block extreme spikes.

---

## 10) Python/FastAPI Proxy Gotchas

**SSE parsing**
- Handle `:` comment lines (keep‑alive) before JSON parsing.
- Buffer and split by `\n` to handle partial SSE lines.

**Streaming tool calls**
- `delta.tool_calls` may be **split across chunks**. Accumulate by `index`/`id`, then parse full JSON arguments.

**Cancellation**
- If proxy client disconnects, close upstream `requests`/`httpx` stream to propagate cancellation.
- Only some providers honor cancellation to stop billing.

**Error handling**
- Check HTTP status before streaming (pre‑stream error).
- If JSON chunk includes top‑level `error`, treat as mid‑stream failure and stop.

---

## 11) Minimal FastAPI Streaming Proxy (concept)

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import requests
import json

app = FastAPI()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

@app.post("/stream")
async def stream_proxy(req: Request):
    body = await req.json()
    body["stream"] = True

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    upstream = requests.post(OPENROUTER_URL, headers=headers, json=body, stream=True)

    def event_generator():
        try:
            if upstream.status_code != 200:
                yield f"data: {json.dumps(upstream.json())}\n\n"
                return

            for line in upstream.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                # Pass through as-is (or filter comments)
                yield text + "\n\n" if text.startswith("data:") or text.startswith(":") else ""
        finally:
            upstream.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

This passes SSE events to clients intact (including `[DONE]`). If you want to **parse and re‑emit** deltas, use the parsing logic above.

---

### Quick Checklist for Implementation
- ✅ `stream: true` in request body
- ✅ Accept & parse SSE (`data:` lines; ignore `:` comments)
- ✅ Stop on `data: [DONE]`
- ✅ Accumulate `delta.tool_calls[].function.arguments` across chunks
- ✅ Handle mid‑stream `error` events + `finish_reason: error`
- ✅ Close upstream on client disconnect to cancel where supported
- ✅ Provide optional `HTTP-Referer` / `X-Title` headers
