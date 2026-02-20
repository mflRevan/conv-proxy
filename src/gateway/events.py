"""
Gateway event manager — processes raw gateway events into
normalized state for the frontend and proxy agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .client import AgentEvent

logger = logging.getLogger("gateway.events")


@dataclass
class ToolCall:
    tool_id: str
    name: str
    arguments: str = ""
    started_at: float = 0.0
    result: str = ""
    finished_at: float = 0.0
    status: str = "running"  # running | completed | error


@dataclass
class RunState:
    """Tracks a single agent run."""
    run_id: str
    session_key: str
    started_at: float = 0.0
    status: str = "running"  # running | completed | error
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_chunks: list[str] = field(default_factory=list)
    cot_chunks: list[str] = field(default_factory=list)
    final_text: str = ""
    error: str = ""


@dataclass
class SessionState:
    """Live state for a watched session."""
    session_key: str
    agent_status: str = "idle"  # idle | busy | error
    current_run: Optional[RunState] = None
    last_run: Optional[RunState] = None
    last_event_at: float = 0.0


class EventManager:
    """
    Maintains per-session live state from gateway events.
    Emits normalized events for the frontend WebSocket.
    """

    def __init__(self):
        self.sessions: dict[str, SessionState] = {}
        self._broadcast: Optional[Any] = None  # set by server

    def set_broadcast(self, fn):
        """Set the broadcast function for frontend WS."""
        self._broadcast = fn

    def get_session_state(self, session_key: str) -> SessionState:
        if session_key not in self.sessions:
            self.sessions[session_key] = SessionState(session_key=session_key)
        return self.sessions[session_key]

    async def handle_event(self, event: AgentEvent):
        """Process a gateway event and update state."""
        sk = event.session_key
        if not sk:
            return

        state = self.get_session_state(sk)
        state.last_event_at = time.time()

        if event.event_type == "agent":
            await self._handle_agent_event(state, event)
        elif event.event_type == "chat":
            await self._handle_chat_event(state, event)

    async def _handle_agent_event(self, state: SessionState, event: AgentEvent):
        stream = event.stream
        data = event.data

        if stream == "lifecycle":
            phase = data.get("phase", "")
            if phase == "run_start":
                state.agent_status = "busy"
                state.current_run = RunState(
                    run_id=event.run_id,
                    session_key=state.session_key,
                    started_at=time.time(),
                )
                await self._emit(state.session_key, {
                    "type": "agent_status",
                    "status": "busy",
                    "runId": event.run_id,
                })

            elif phase in ("run_end", "run_complete"):
                state.agent_status = "idle"
                if state.current_run:
                    state.current_run.status = "completed"
                    # Assemble final text
                    if state.current_run.assistant_chunks:
                        state.current_run.final_text = "".join(state.current_run.assistant_chunks)
                    state.last_run = state.current_run
                    state.current_run = None
                await self._emit(state.session_key, {
                    "type": "agent_status",
                    "status": "idle",
                    "runId": event.run_id,
                })

            elif phase == "run_error":
                state.agent_status = "error"
                if state.current_run:
                    state.current_run.status = "error"
                    state.current_run.error = data.get("error", "unknown error")
                    state.last_run = state.current_run
                    state.current_run = None
                await self._emit(state.session_key, {
                    "type": "agent_status",
                    "status": "error",
                    "error": data.get("error", ""),
                    "runId": event.run_id,
                })

        elif stream == "tool":
            if not state.current_run:
                return

            event_kind = data.get("event", data.get("kind", ""))
            if event_kind in ("tool_call", "call"):
                tc = ToolCall(
                    tool_id=data.get("toolCallId", data.get("id", str(event.seq))),
                    name=data.get("name", data.get("toolName", "?")),
                    arguments=data.get("arguments", data.get("input", "")),
                    started_at=time.time(),
                )
                state.current_run.tool_calls.append(tc)
                await self._emit(state.session_key, {
                    "type": "tool_call",
                    "toolId": tc.tool_id,
                    "name": tc.name,
                    "arguments": tc.arguments[:2000],
                    "runId": event.run_id,
                })

            elif event_kind in ("tool_result", "result"):
                # Find matching tool call
                tool_id = data.get("toolCallId", data.get("id", ""))
                content = data.get("content", data.get("output", ""))
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict):
                            parts.append(c.get("text", c.get("content", "")))
                        elif isinstance(c, str):
                            parts.append(c)
                    content = "\n".join(parts)

                for tc in reversed(state.current_run.tool_calls):
                    if tc.tool_id == tool_id or tc.status == "running":
                        tc.result = str(content)[:8000]
                        tc.finished_at = time.time()
                        tc.status = "completed"
                        break

                await self._emit(state.session_key, {
                    "type": "tool_result",
                    "toolId": tool_id,
                    "name": data.get("name", data.get("toolName", "")),
                    "content": str(content)[:4000],
                    "runId": event.run_id,
                })

        elif stream == "assistant":
            if not state.current_run:
                return

            delta = data.get("delta", data.get("text", data.get("content", "")))
            thinking = data.get("thinking", False)

            if thinking:
                state.current_run.cot_chunks.append(str(delta))
                await self._emit(state.session_key, {
                    "type": "cot_delta",
                    "delta": str(delta),
                    "runId": event.run_id,
                })
            elif delta:
                state.current_run.assistant_chunks.append(str(delta))
                await self._emit(state.session_key, {
                    "type": "assistant_delta",
                    "delta": str(delta),
                    "runId": event.run_id,
                })

        elif stream == "error":
            error_msg = data.get("message", data.get("error", str(data)))
            await self._emit(state.session_key, {
                "type": "agent_error",
                "error": error_msg,
                "runId": event.run_id,
            })

    async def _handle_chat_event(self, state: SessionState, event: AgentEvent):
        data = event.data
        msg_type = data.get("type", "")

        if msg_type in ("message", "assistant"):
            await self._emit(state.session_key, {
                "type": "chat_message",
                "role": data.get("role", "assistant"),
                "content": data.get("content", data.get("text", "")),
            })

    async def _emit(self, session_key: str, payload: dict):
        """Broadcast a normalized event to connected frontends."""
        payload["sessionKey"] = session_key
        payload["ts"] = time.time()
        if self._broadcast:
            try:
                await self._broadcast(payload)
            except Exception:
                logger.exception("Error broadcasting event")

    def get_cot_text(self, session_key: str) -> str:
        """Get CoT for current or last run."""
        state = self.sessions.get(session_key)
        if not state:
            return ""
        run = state.current_run or state.last_run
        if not run:
            return ""
        return "".join(run.cot_chunks)

    def get_tool_calls(self, session_key: str) -> list[dict]:
        """Get tool calls for current or last run."""
        state = self.sessions.get(session_key)
        if not state:
            return []
        run = state.current_run or state.last_run
        if not run:
            return []
        return [
            {
                "toolId": tc.tool_id,
                "name": tc.name,
                "arguments": tc.arguments[:2000],
                "result": tc.result[:4000],
                "status": tc.status,
                "startedAt": tc.started_at,
                "finishedAt": tc.finished_at,
            }
            for tc in run.tool_calls
        ]
