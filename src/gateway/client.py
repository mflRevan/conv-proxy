"""
OpenClaw Gateway WebSocket client.

Connects to the local OpenClaw Gateway using protocol v3,
subscribes to agent/chat events, and provides methods to
list sessions, agents, fetch history, send messages, and
create new sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger("gateway.client")

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class GatewayConfig:
    url: str = "ws://127.0.0.1:18789"
    token: str = ""
    origin: str = "http://127.0.0.1:18789"
    client_id: str = "openclaw-control-ui"
    client_version: str = "0.1.0"
    reconnect_delay_base: float = 1.0
    reconnect_delay_max: float = 30.0
    scopes: list[str] = field(default_factory=lambda: [
        "operator.read", "operator.write", "operator.admin"
    ])
    caps: list[str] = field(default_factory=lambda: ["tool-events"])


@dataclass
class AgentEvent:
    """Normalized agent event from the gateway stream."""
    event_type: str      # "agent", "chat", etc.
    stream: str          # "tool", "assistant", "lifecycle", "error"
    run_id: str = ""
    seq: int = 0
    session_key: str = ""
    data: dict = field(default_factory=dict)
    ts: float = 0.0


@dataclass
class SessionInfo:
    key: str
    kind: str
    display_name: str
    agent_id: str = ""
    session_id: str = ""
    model: str = ""
    model_provider: str = ""
    updated_at: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    origin: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class AgentInfo:
    id: str
    name: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

EventCallback = Callable[[AgentEvent], Coroutine[Any, Any, None]]
StateCallback = Callable[[ConnectionState], Coroutine[Any, Any, None]]


class GatewayClient:
    """
    Async WebSocket client for the OpenClaw Gateway protocol v3.

    Usage:
        client = GatewayClient(GatewayConfig(token="..."))
        client.on_event = my_event_handler
        await client.connect()  # blocks until disconnected
    """

    def __init__(self, config: GatewayConfig):
        self.config = config
        self._ws: Optional[ClientConnection] = None
        self._state = ConnectionState.DISCONNECTED
        self._pending: dict[str, asyncio.Future] = {}
        self._req_counter = 0
        self._reconnect_attempt = 0
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()

        # Callbacks
        self.on_event: Optional[EventCallback] = None
        self.on_state_change: Optional[StateCallback] = None

        # Cached data
        self.server_info: dict = {}
        self.granted_methods: list[str] = []
        self.granted_events: list[str] = []

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED and self._ws is not None

    async def _set_state(self, state: ConnectionState):
        self._state = state
        if self.on_state_change:
            try:
                await self.on_state_change(state)
            except Exception:
                logger.exception("Error in state callback")

    # ------------------------------------------------------------------
    # Request/response
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        self._req_counter += 1
        return f"r{self._req_counter}"

    async def _send_request(self, method: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        """Send a request and wait for the response."""
        if not self._ws:
            raise ConnectionError("Not connected to gateway")

        req_id = self._next_id()
        frame = {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        try:
            await self._ws.send(json.dumps(frame))
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"Gateway request {method} timed out after {timeout}s")
        except Exception:
            self._pending.pop(req_id, None)
            raise

    # ------------------------------------------------------------------
    # Connect / handshake
    # ------------------------------------------------------------------

    async def _do_connect(self) -> bool:
        """Perform a single connection + handshake attempt."""
        try:
            await self._set_state(ConnectionState.CONNECTING)
            headers = {"Origin": self.config.origin}
            self._ws = await websockets.connect(
                self.config.url,
                additional_headers=headers,
                ping_interval=30,
                ping_timeout=10,
                max_size=16 * 1024 * 1024,  # 16MB
            )

            # Wait for challenge
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
            challenge = json.loads(raw)
            if challenge.get("event") != "connect.challenge":
                logger.error(f"Expected connect.challenge, got: {challenge}")
                return False

            # Send connect
            connect_frame = {
                "type": "req",
                "id": self._next_id(),
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {
                        "id": self.config.client_id,
                        "version": self.config.client_version,
                        "platform": "linux",
                        "mode": "ui",
                    },
                    "role": "operator",
                    "scopes": self.config.scopes,
                    "caps": self.config.caps,
                    "commands": [],
                    "permissions": {},
                    "auth": {"token": self.config.token},
                    "locale": "en-US",
                    "userAgent": f"conv-proxy/{self.config.client_version}",
                },
            }
            await self._ws.send(json.dumps(connect_frame))

            raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
            hello = json.loads(raw)

            if not hello.get("ok"):
                error = hello.get("error", {})
                logger.error(f"Gateway handshake failed: {error.get('message', 'unknown')}")
                return False

            payload = hello.get("payload", {})
            self.server_info = payload.get("server", {})
            features = payload.get("features", {})
            self.granted_methods = features.get("methods", [])
            self.granted_events = features.get("events", [])

            logger.info(
                f"Connected to gateway v{self.server_info.get('version', '?')} "
                f"host={self.server_info.get('host', '?')} "
                f"methods={len(self.granted_methods)} events={len(self.granted_events)}"
            )

            await self._set_state(ConnectionState.CONNECTED)
            self._connected_event.set()
            self._reconnect_attempt = 0
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------

    async def _recv_loop(self):
        """Read messages from the gateway and dispatch."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                if msg_type == "res":
                    req_id = msg.get("id")
                    if req_id and req_id in self._pending:
                        fut = self._pending.pop(req_id)
                        if not fut.done():
                            fut.set_result(msg)
                    continue

                if msg_type == "event":
                    await self._handle_event(msg)
                    continue

                # ping/pong handled by websockets library

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Gateway connection closed: {e}")
        except Exception as e:
            logger.error(f"Recv loop error: {e}")

    async def _handle_event(self, msg: dict):
        """Parse a gateway event and dispatch to callback."""
        event_name = msg.get("event", "")
        payload = msg.get("payload", {})

        if event_name == "agent":
            evt = AgentEvent(
                event_type="agent",
                stream=payload.get("stream", ""),
                run_id=payload.get("runId", ""),
                seq=payload.get("seq", 0),
                session_key=payload.get("sessionKey", ""),
                data=payload.get("data", {}),
                ts=payload.get("ts", time.time()),
            )
            if self.on_event:
                try:
                    await self.on_event(evt)
                except Exception:
                    logger.exception("Error in event callback")

        elif event_name == "chat":
            evt = AgentEvent(
                event_type="chat",
                stream=payload.get("type", ""),
                session_key=payload.get("sessionKey", ""),
                data=payload,
                ts=payload.get("ts", time.time()),
            )
            if self.on_event:
                try:
                    await self.on_event(evt)
                except Exception:
                    logger.exception("Error in event callback")

        elif event_name == "health":
            # Silently handle health events
            pass

        elif event_name in ("presence", "tick", "heartbeat"):
            # Low-priority events
            pass

        else:
            logger.debug(f"Unhandled event: {event_name}")

    # ------------------------------------------------------------------
    # Public: lifecycle
    # ------------------------------------------------------------------

    async def connect(self):
        """Connect and run until stopped. Reconnects automatically."""
        self._stop_event.clear()

        while not self._stop_event.is_set():
            ok = await self._do_connect()

            if ok:
                await self._recv_loop()

            # Clean up
            self._connected_event.clear()
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
                self._ws = None

            # Cancel pending requests
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("Disconnected"))
            self._pending.clear()

            if self._stop_event.is_set():
                break

            await self._set_state(ConnectionState.RECONNECTING)
            self._reconnect_attempt += 1
            delay = min(
                self.config.reconnect_delay_base * (2 ** min(self._reconnect_attempt, 5)),
                self.config.reconnect_delay_max,
            )
            logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempt})")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

        await self._set_state(ConnectionState.DISCONNECTED)

    async def disconnect(self):
        """Gracefully disconnect."""
        self._stop_event.set()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def wait_connected(self, timeout: float = 30.0):
        """Wait until connected to the gateway."""
        await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)

    # ------------------------------------------------------------------
    # Public: API methods
    # ------------------------------------------------------------------

    async def list_sessions(self) -> list[SessionInfo]:
        """List all active sessions."""
        result = await self._send_request("sessions.list")
        if not result.get("ok"):
            raise RuntimeError(f"sessions.list failed: {result.get('error', {}).get('message', '?')}")

        payload = result["payload"]
        sessions_raw = payload.get("sessions", [])
        sessions = []
        for s in sessions_raw:
            sessions.append(SessionInfo(
                key=s.get("key", ""),
                kind=s.get("kind", ""),
                display_name=s.get("displayName", ""),
                agent_id=s.get("key", "").split(":")[1] if ":" in s.get("key", "") else "",
                session_id=s.get("sessionId", ""),
                model=s.get("model", ""),
                model_provider=s.get("modelProvider", ""),
                updated_at=s.get("updatedAt", 0),
                input_tokens=s.get("inputTokens", 0),
                output_tokens=s.get("outputTokens", 0),
                origin=s.get("origin", {}),
                raw=s,
            ))
        return sessions

    async def list_agents(self) -> list[AgentInfo]:
        """List available agents."""
        result = await self._send_request("agents.list")
        if not result.get("ok"):
            raise RuntimeError(f"agents.list failed: {result.get('error', {}).get('message', '?')}")

        payload = result["payload"]
        agents = []
        for a in payload.get("agents", []):
            agents.append(AgentInfo(
                id=a.get("id", ""),
                name=a.get("name", a.get("id", "")),
            ))
        return agents

    async def get_history(self, session_key: str, limit: int = 50) -> list[dict]:
        """Get chat history for a session."""
        result = await self._send_request("chat.history", {
            "sessionKey": session_key,
            "limit": limit,
        })
        if not result.get("ok"):
            raise RuntimeError(f"chat.history failed: {result.get('error', {}).get('message', '?')}")
        return result.get("payload", {}).get("messages", [])

    async def send_message(self, session_key: str, message: str) -> dict:
        """Send a user message to a session (triggers agent response)."""
        result = await self._send_request("chat.send", {
            "sessionKey": session_key,
            "message": message,
        }, timeout=120)
        if not result.get("ok"):
            raise RuntimeError(f"chat.send failed: {result.get('error', {}).get('message', '?')}")
        return result.get("payload", {})

    async def inject_message(self, session_key: str, message: str, role: str = "user") -> dict:
        """Inject a message into a session without triggering response."""
        result = await self._send_request("chat.inject", {
            "sessionKey": session_key,
            "message": message,
            "role": role,
        })
        if not result.get("ok"):
            raise RuntimeError(f"chat.inject failed: {result.get('error', {}).get('message', '?')}")
        return result.get("payload", {})


    async def abort_run(self, session_key: str) -> dict:
        """Abort the current agent run for a session."""
        result = await self._send_request("chat.abort", {
            "sessionKey": session_key,
        })
        if not result.get("ok"):
            raise RuntimeError(f"chat.abort failed: {result.get('error', {}).get('message', '?')}")
        return result.get("payload", {})

    async def get_status(self) -> dict:
        """Get gateway status."""
        result = await self._send_request("status")
        if not result.get("ok"):
            return {}
        return result.get("payload", {})
