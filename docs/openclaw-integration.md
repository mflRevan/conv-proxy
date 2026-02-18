# OpenClaw Integration Plan for conv-proxy

## Where conv-proxy sits

`User (voice)` → `conv-proxy (OpenRouter + VAD/STT/TTS + queue/scratchpad)` → `OpenClaw main session (Jarvis)`.

conv-proxy is a conversational control layer. It does **not** replace the main session and should not execute long agentic tasks itself.

## Main-session interaction model

- Main session remains the authoritative executor.
- conv-proxy receives live context from main session via:
  - `POST /api/agent-context`
  - fields: `status`, `current_task`, `turns`, `compressed_context`, optional `just_finished`, `completion_brief`
- conv-proxy injects this context into its system prompt + live response behavior.

## Scratchpad vs Queue semantics

State held by proxy controller:
- `scratchpad_task`: editable task draft buffer
- `queued_task`: task explicitly queued for dispatch

Rules:
1. User work requests/refinements update `scratchpad_task` (not queued by default).
2. User must deliberately request queue/send/commit for `queued_task`.
3. Any new user interaction while queued de-queues it back to scratchpad.
4. Dispatch only if:
   - `queued_task` exists
   - main agent status is `idle`
   - dispatch delay elapsed (default 10s)
   - latest completion brief has been sent (gate)

## Completion brief gate

When main transitions busy→idle (or integration sends `just_finished=true`):
- Integration supplies `completion_brief`.
- Proxy broadcasts `agent_brief` to clients.
- Dispatch is blocked until this brief is emitted.

This enforces the requirement: user is briefed before any queued task is sent.

## Recommended bridge process (OpenClaw side)

A lightweight bridge should:
1. Poll/subscribe main-session updates.
2. Push context to conv-proxy `/api/agent-context`.
3. Listen for `dispatch_ready` events from proxy websocket (or future HTTP queue endpoint).
4. On dispatch_ready, call OpenClaw `sessions_send` to main session with queued task text.

Pseudo flow:
- proxy says `dispatch_ready(task)`
- bridge sends to main session:
  - `sessions_send(sessionKey=<main>, message=task)`
- bridge marks main as busy via `/api/agent-context`

## Safety notes

- Only explicit stop words trigger interrupt tool.
- Queueing is explicit and reversible by any further user interaction.
- Proxy remains a conversational layer with bounded responsibilities.
