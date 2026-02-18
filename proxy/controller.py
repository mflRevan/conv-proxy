"""
Conv-proxy controller v2: OpenRouter-backed with native tool calling.

The model handles intent classification and tool calling natively.
The controller manages state, dispatch timing, and context injection.
"""
from __future__ import annotations

import asyncio
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Generator

from llm.openrouter_engine import OpenRouterEngine


# ─── Tool definitions ───
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "interrupt_agent",
            "description": "Stop/cancel/abort the main AI agent. ONLY call when user EXPLICITLY requests stopping, cancelling, or aborting.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_queued_task",
            "description": "Set or update the queued task draft. Call whenever user describes work they want done (features, fixes, tests, benchmarks, changes, deployments). Overwrites previous draft entirely. Write a complete standalone task instruction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Complete, standalone task instruction for the main agent.",
                    }
                },
                "required": ["task"],
            },
        },
    },
]


def _build_system_prompt(state: "ProxyState") -> str:
    """Build the system prompt with injected context."""
    parts = [
        "You are Jarvis Proxy, a lightweight conversational voice interface.",
        "You bridge the user (Aiman) and the main AI agent (Jarvis).",
        "",
        "## Rules",
        "- Keep replies to 1-2 concise sentences (you are spoken aloud via TTS)",
        "- Call set_queued_task when user describes ANY work to be done",
        "- Call interrupt_agent when user wants to stop/cancel/abort/interrupt, including soft phrases like 'never mind', 'forget it', 'don't do that'",
        "- For greetings, questions, complaints, status queries: reply conversationally",
        "- After a stop, treat the next message independently — don't assume user wants to stop again",
        "- Be direct, efficient, slightly warm. MCU-Jarvis vibe.",
        "",
    ]

    # Compressed past context (mock for now, will be injected)
    if state.compressed_context:
        parts.append("## Background Context")
        parts.append(state.compressed_context)
        parts.append("")

    # Live agent status
    parts.append("## Agent Status")
    parts.append(f"- Status: {state.agent_status.upper()}")
    if state.agent_current_task:
        parts.append(f"- Current task: {state.agent_current_task}")
    parts.append("")

    # Live agent turns (last N turns with main agent)
    if state.agent_turns:
        parts.append("## Live Agent Activity (recent turns)")
        for turn in state.agent_turns[-4:]:
            role = turn.get("role", "?")
            content = turn.get("content", "")[:300]
            parts.append(f"[{role}]: {content}")
        parts.append("")

    # Queued task draft
    if state.queued_task:
        parts.append("## Current Queued Task Draft")
        parts.append(f'"{state.queued_task}"')
        parts.append("(User may refine this. Overwrite with set_queued_task.)")
        parts.append("")

    return "\n".join(parts)


@dataclass
class ProxyState:
    """Proxy state: agent context + task queue + dispatch."""
    queued_task: str = ""
    agent_status: str = "idle"  # idle | busy
    agent_current_task: str = ""
    agent_turns: list[dict] = field(default_factory=list)
    compressed_context: str = ""
    dispatch_delay: float = 10.0  # seconds
    _last_input_time: float = 0.0


@dataclass
class ProxyController:
    """Manages proxy pipeline: context → LLM → tools → response."""
    engine: OpenRouterEngine
    state: ProxyState = field(default_factory=ProxyState)
    conversation: list[dict] = field(default_factory=list)
    max_history_pairs: int = 15

    # Callbacks
    on_stop: Optional[Callable] = None
    on_dispatch: Optional[Callable[[str], None]] = None
    on_task_updated: Optional[Callable[[str], None]] = None

    def _trim_history(self):
        max_msgs = self.max_history_pairs * 2
        if len(self.conversation) > max_msgs:
            self.conversation = self.conversation[-max_msgs:]

    def _build_messages(self, user_msg: str) -> list[dict]:
        """Build full message list for the LLM."""
        system = _build_system_prompt(self.state)
        msgs = [{"role": "system", "content": system}]
        msgs.extend(self.conversation)
        msgs.append({"role": "user", "content": user_msg})
        return msgs

    def process_message(self, user_msg: str) -> dict:
        """
        Process user message (non-streaming).
        Returns: {action, reply, task_draft, tool_calls, timings}
        """
        self.state._last_input_time = time.monotonic()
        self.conversation.append({"role": "user", "content": user_msg})
        self._trim_history()

        t0 = time.monotonic()
        system = _build_system_prompt(self.state)
        msgs_for_api = [{"role": "system", "content": system}] + self.conversation

        result = self.engine.chat(msgs_for_api, tools=TOOLS)
        latency = (time.monotonic() - t0) * 1000

        reply = result["content"] or ""
        tool_calls = result.get("tool_calls") or []
        action = "chat"

        # Process tool calls
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"].get("arguments", "")
            try:
                fn_args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                fn_args = {"task": raw_args}  # fallback: treat as raw task text

            if fn_name == "interrupt_agent":
                action = "stop"
                self.state.queued_task = ""
                if self.on_stop:
                    self.on_stop()

            elif fn_name == "set_queued_task":
                action = "task"
                task_text = fn_args.get("task", "")
                if not task_text and isinstance(fn_args, str):
                    task_text = fn_args
                if task_text:
                    self.state.queued_task = task_text
                    if self.on_task_updated:
                        self.on_task_updated(task_text)

        self.conversation.append({"role": "assistant", "content": reply})
        self._trim_history()

        return {
            "action": action,
            "reply": reply,
            "task_draft": self.state.queued_task,
            "tool_calls": [{"name": tc["function"]["name"], "args": tc["function"].get("arguments", "")} for tc in tool_calls],
            "timings": {"total": latency, "api": result["latency_ms"]},
        }

    def process_message_stream(
        self,
        user_msg: str,
        cancel_event: threading.Event | None = None,
    ) -> Generator[dict, None, None]:
        """
        Streaming version. Yields deltas as they arrive.
        Yields same types as OpenRouterEngine.chat_stream plus tool processing.
        """
        self.state._last_input_time = time.monotonic()
        self.conversation.append({"role": "user", "content": user_msg})
        self._trim_history()

        msgs = [{"role": "system", "content": _build_system_prompt(self.state)}] + self.conversation

        reply_parts = []
        tool_calls = []

        for delta in self.engine.chat_stream(msgs, tools=TOOLS, cancel_event=cancel_event):
            dt = delta["type"]

            if dt == "content":
                reply_parts.append(delta["text"])
                yield delta

            elif dt == "tool_call":
                tc = delta
                fn_name = tc["name"]
                try:
                    fn_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    fn_args = {}

                if fn_name == "interrupt_agent":
                    self.state.queued_task = ""
                    if self.on_stop:
                        self.on_stop()
                    yield {"type": "action", "action": "stop"}

                elif fn_name == "set_queued_task":
                    task_text = fn_args.get("task", "")
                    if task_text:
                        self.state.queued_task = task_text
                        if self.on_task_updated:
                            self.on_task_updated(task_text)
                    yield {"type": "action", "action": "task", "task": task_text}

                tool_calls.append({"name": fn_name, "args": fn_args})

            elif dt == "reasoning":
                yield delta

            elif dt == "done":
                full_reply = "".join(reply_parts)
                if full_reply:
                    self.conversation.append({"role": "assistant", "content": full_reply})
                    self._trim_history()
                yield delta

            elif dt == "cancelled":
                yield delta
                return

            elif dt == "error":
                yield delta
                return

    def update_agent_context(
        self,
        status: str = "idle",
        current_task: str = "",
        turns: list[dict] | None = None,
        compressed_context: str = "",
    ):
        """Update live agent context."""
        self.state.agent_status = status
        self.state.agent_current_task = current_task
        if turns is not None:
            self.state.agent_turns = turns
        if compressed_context:
            self.state.compressed_context = compressed_context

    def check_dispatch(self) -> Optional[str]:
        """Check if queued task should be dispatched. Returns task text or None."""
        if not self.state.queued_task:
            return None
        if self.state.agent_status != "idle":
            return None
        elapsed = time.monotonic() - self.state._last_input_time
        if elapsed < self.state.dispatch_delay:
            return None
        task = self.state.queued_task
        self.state.queued_task = ""
        if self.on_dispatch:
            self.on_dispatch(task)
        return task

    def reset(self):
        """Full reset."""
        self.conversation.clear()
        self.state.queued_task = ""
        self.state.agent_status = "idle"
        self.state.agent_current_task = ""
        self.state.agent_turns.clear()
