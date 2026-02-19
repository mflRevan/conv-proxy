"""
Conv-proxy controller: OpenRouter-backed with explicit scratchpad/queue semantics.

Key behavior:
- Proxy maintains a mutable scratchpad task buffer.
- Proxy only queues a task when user deliberately asks to queue/send it.
- Any new user interaction while a task is queued de-queues it back to scratchpad.
- Dispatch happens only when: queued task exists, agent is idle, dispatch delay passed,
  and required completion briefing has been sent.
"""
from __future__ import annotations

import json
import time
import threading
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Generator

from llm.openrouter_engine import OpenRouterEngine


# ─── Tool definitions ───────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "interrupt_agent",
            "description": "Stop/cancel/abort the main AI agent. ONLY call when user explicitly asks to stop/cancel/abort/interrupt current agent run.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_task_buffer",
            "description": "Set or refine the scratchpad task buffer from user requests. This does NOT queue/dispatch the task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Complete standalone task instruction in scratchpad form.",
                    }
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_task_buffer",
            "description": "Clear the scratchpad task buffer when user asks to discard/remove/reset it.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },

    {
        "type": "function",
        "function": {
            "name": "append_task_buffer",
            "description": "Append markdown text to the scratchpad task buffer (preferred for incremental planning).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Markdown text to append."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_task_buffer",
            "description": "Patch the scratchpad task buffer by replacing a substring (controlled edit).",
            "parameters": {
                "type": "object",
                "properties": {
                    "find": {"type": "string", "description": "Exact text to find."},
                    "replace": {"type": "string", "description": "Replacement text."},
                    "count": {"type": "integer", "description": "Max replacements (default 1, 0=all)."}
                },
                "required": ["find", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue_buffered_task",
            "description": "Queue the current scratchpad task for later dispatch to main agent. ONLY call when user deliberately asks to queue/send/commit it.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _load_fixed_proxy_prompt() -> str:
    cfg = Path(__file__).resolve().parents[1] / "config" / "PROXY.md"
    if cfg.exists():
        return cfg.read_text(encoding="utf-8").strip()
    return "You are Jarvis Proxy. Keep spoken responses concise."


FIXED_PROXY_PROMPT = _load_fixed_proxy_prompt()

_CALL_MARKERS_RE = re.compile(r"<\|[^>]+\|>")


def _clean_tool_args(raw: str) -> str:
    if not raw:
        return ""
    s = _CALL_MARKERS_RE.sub("", raw).strip()
    # if model appended extra junk after valid JSON, keep through last brace
    if "}" in s and s.count("{") >= 1:
        last = s.rfind("}")
        s = s[: last + 1]
    return s.strip()


def _parse_tool_args(raw: str) -> dict:
    cleaned = _clean_tool_args(raw)
    if not cleaned:
        return {}
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {"task": cleaned}


def _normalize_task_text(task: str) -> str:
    t = (task or "").strip()
    if not t:
        return ""
    # If task is sent as JSON string, unwrap to raw text task
    try:
        parsed = json.loads(t)
        if isinstance(parsed, dict) and isinstance(parsed.get("task"), str):
            return parsed["task"].strip()
    except Exception:
        pass
    return t


def _build_system_prompt(state: "ProxyState") -> str:
    parts = [FIXED_PROXY_PROMPT, "", "## Runtime Rules"]
    parts.extend([
        "- Spoken replies: short, clear, 1-2 sentences unless explicitly asked for detail.",
        "- Maintain a scratchpad task buffer via set_task_buffer/clear_task_buffer.",
        "- Do NOT queue by default. Queue ONLY on deliberate user request (e.g. 'queue this', 'send this to Jarvis').",
        "- interrupt_agent only on explicit stop/cancel instructions.",
        "- If queued task gets de-queued due to new user interaction, treat it as scratchpad again.",
        "- Be direct, efficient, lightly warm. MCU-Jarvis-like tone.",
        "",
    ])

    if state.compressed_context:
        parts += ["## Background Context", state.compressed_context, ""]

    parts += ["## Agent Status", f"- Status: {state.agent_status.upper()}"]
    if state.agent_current_task:
        parts.append(f"- Current task: {state.agent_current_task}")
    parts.append("")

    if state.agent_turns:
        parts.append("## Live Agent Activity (recent)")
        for turn in state.agent_turns[-4:]:
            role = turn.get("role", "?")
            content = (turn.get("content", "") or "")[:300]
            parts.append(f"[{role}] {content}")
        parts.append("")

    parts += ["## Task Buffer State"]
    parts.append(f"- Scratchpad: {state.scratchpad_task or '(empty)'}")
    parts.append(f"- Queued: {state.queued_task or '(none)'}")
    parts.append(
        "- Dispatch gate: queued task dispatches only when agent is idle, quiet delay elapsed, and latest completion brief was sent."
    )
    parts.append("")

    return "\n".join(parts)


@dataclass
class ProxyState:
    scratchpad_task: str = ""
    queued_task: str = ""

    agent_status: str = "idle"  # idle | busy
    agent_current_task: str = ""
    agent_turns: list[dict] = field(default_factory=list)
    compressed_context: str = ""

    dispatch_delay: float = 10.0
    _last_input_time: float = 0.0

    # completion briefing gate
    pending_completion_brief: str = ""
    must_brief_before_dispatch: bool = False


@dataclass
class ProxyController:
    engine: OpenRouterEngine
    state: ProxyState = field(default_factory=ProxyState)
    conversation: list[dict] = field(default_factory=list)
    max_history_pairs: int = 15

    # Callbacks
    on_stop: Optional[Callable] = None
    on_dispatch: Optional[Callable[[str], None]] = None
    on_task_updated: Optional[Callable[[str], None]] = None
    on_task_queued: Optional[Callable[[str], None]] = None

    def _trim_history(self):
        max_msgs = self.max_history_pairs * 2
        if len(self.conversation) > max_msgs:
            self.conversation = self.conversation[-max_msgs:]

    def _dequeue_on_user_interaction(self):
        """
        Any user interaction de-queues current queued task back into scratchpad.
        """
        if self.state.queued_task:
            self.state.scratchpad_task = self.state.queued_task
            self.state.queued_task = ""

    def process_message(self, user_msg: str) -> dict:
        self.state._last_input_time = time.monotonic()
        self._dequeue_on_user_interaction()
        self.conversation.append({"role": "user", "content": user_msg})
        self._trim_history()

        t0 = time.monotonic()
        msgs_for_api = [{"role": "system", "content": _build_system_prompt(self.state)}] + self.conversation
        result = self.engine.chat(msgs_for_api, tools=TOOLS)
        latency = (time.monotonic() - t0) * 1000

        reply = result.get("content") or ""
        tool_calls = result.get("tool_calls") or []
        action = "chat"

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"].get("arguments", "")
            fn_args = _parse_tool_args(raw_args)

            if fn_name == "interrupt_agent":
                action = "stop"
                self.state.queued_task = ""
                if self.on_stop:
                    self.on_stop()

            elif fn_name == "set_task_buffer":
                action = "buffer"
                task_text = _normalize_task_text(fn_args.get("task", ""))
                if task_text:
                    self.state.scratchpad_task = task_text
                    if self.on_task_updated:
                        self.on_task_updated(task_text)

            elif fn_name == "clear_task_buffer":
                action = "buffer_cleared"
                self.state.scratchpad_task = ""

            elif fn_name == "append_task_buffer":
                action = "buffer"
                add_text = _normalize_task_text(fn_args.get("text", ""))
                if add_text:
                    if self.state.scratchpad_task:
                        self.state.scratchpad_task += "\n" + add_text
                    else:
                        self.state.scratchpad_task = add_text
                    if self.on_task_updated:
                        self.on_task_updated(self.state.scratchpad_task)

            elif fn_name == "patch_task_buffer":
                action = "buffer"
                find = fn_args.get("find", "") or ""
                replace = fn_args.get("replace", "") or ""
                count = fn_args.get("count", 1)
                try:
                    count = int(count)
                except Exception:
                    count = 1
                if find and self.state.scratchpad_task:
                    if count == 0:
                        self.state.scratchpad_task = self.state.scratchpad_task.replace(find, replace)
                    else:
                        self.state.scratchpad_task = self.state.scratchpad_task.replace(find, replace, count)
                    if self.on_task_updated:
                        self.on_task_updated(self.state.scratchpad_task)

            elif fn_name == "queue_buffered_task":
                if self.state.scratchpad_task:
                    action = "queued"
                    self.state.queued_task = self.state.scratchpad_task
                    if self.on_task_queued:
                        self.on_task_queued(self.state.queued_task)

        assistant_msg = {"role": "assistant", "content": reply}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        self.conversation.append(assistant_msg)

        for tc in tool_calls:
            tc_id = tc.get("id", "")
            fn_name = tc["function"]["name"]
            tool_result = {"status": "ok", "scratchpad": self.state.scratchpad_task[:100], "queued": bool(self.state.queued_task)}
            if fn_name == "queue_buffered_task" and not self.state.scratchpad_task:
                tool_result = {"status": "error", "message": "scratchpad empty"}
            self.conversation.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": json.dumps(tool_result),
            })

        self._trim_history()
        return {
            "action": action,
            "reply": reply,
            "task_draft": self.state.scratchpad_task,
            "queued_task": self.state.queued_task,
            "tool_calls": [{"name": tc["function"]["name"], "args": tc["function"].get("arguments", "")} for tc in tool_calls],
            "timings": {"total": latency, "api": result.get("latency_ms", 0.0)},
        }

    def process_message_stream(self, user_msg: str, cancel_event: threading.Event | None = None) -> Generator[dict, None, None]:
        self.state._last_input_time = time.monotonic()
        self._dequeue_on_user_interaction()
        self.conversation.append({"role": "user", "content": user_msg})
        self._trim_history()

        msgs = [{"role": "system", "content": _build_system_prompt(self.state)}] + self.conversation
        reply_parts: list[str] = []

        for delta in self.engine.chat_stream(msgs, tools=TOOLS, cancel_event=cancel_event):
            dt = delta["type"]

            if dt == "content":
                reply_parts.append(delta["text"])
                yield delta

            elif dt == "tool_call":
                fn_name = delta["name"]
                raw_args = delta.get("arguments", "")
                fn_args = _parse_tool_args(raw_args)

                if fn_name == "interrupt_agent":
                    self.state.queued_task = ""
                    if self.on_stop:
                        self.on_stop()
                    yield {"type": "action", "action": "stop"}

                elif fn_name == "set_task_buffer":
                    task_text = _normalize_task_text(fn_args.get("task", ""))
                    if task_text:
                        self.state.scratchpad_task = task_text
                        if self.on_task_updated:
                            self.on_task_updated(task_text)
                    yield {"type": "action", "action": "buffer", "task": task_text}

                elif fn_name == "clear_task_buffer":
                    self.state.scratchpad_task = ""
                    yield {"type": "action", "action": "buffer_cleared"}

                elif fn_name == "append_task_buffer":
                    add_text = _normalize_task_text(fn_args.get("text", ""))
                    if add_text:
                        if self.state.scratchpad_task:
                            self.state.scratchpad_task += "\n" + add_text
                        else:
                            self.state.scratchpad_task = add_text
                        if self.on_task_updated:
                            self.on_task_updated(self.state.scratchpad_task)
                    yield {"type": "action", "action": "buffer", "task": add_text}

                elif fn_name == "patch_task_buffer":
                    find = fn_args.get("find", "") or ""
                    replace = fn_args.get("replace", "") or ""
                    count = fn_args.get("count", 1)
                    try:
                        count = int(count)
                    except Exception:
                        count = 1
                    if find and self.state.scratchpad_task:
                        if count == 0:
                            self.state.scratchpad_task = self.state.scratchpad_task.replace(find, replace)
                        else:
                            self.state.scratchpad_task = self.state.scratchpad_task.replace(find, replace, count)
                        if self.on_task_updated:
                            self.on_task_updated(self.state.scratchpad_task)
                    yield {"type": "action", "action": "buffer", "task": self.state.scratchpad_task}

                elif fn_name == "queue_buffered_task":
                    if self.state.scratchpad_task:
                        self.state.queued_task = self.state.scratchpad_task
                        if self.on_task_queued:
                            self.on_task_queued(self.state.queued_task)
                        yield {"type": "action", "action": "queued", "task": self.state.queued_task}
                    else:
                        yield {"type": "action", "action": "queue_failed", "task": ""}

            elif dt == "reasoning":
                yield delta

            elif dt == "done":
                full_reply = "".join(reply_parts)
                if full_reply:
                    self.conversation.append({"role": "assistant", "content": full_reply})
                    self._trim_history()
                yield delta

            elif dt in ("cancelled", "error"):
                yield delta
                return

    def update_agent_context(
        self,
        status: str = "idle",
        current_task: str = "",
        turns: list[dict] | None = None,
        compressed_context: str = "",
        just_finished: bool = False,
        completion_brief: str = "",
    ):
        prev_status = self.state.agent_status
        self.state.agent_status = status
        self.state.agent_current_task = current_task
        if turns is not None:
            self.state.agent_turns = turns
        if compressed_context:
            self.state.compressed_context = compressed_context

        finished_transition = (prev_status == "busy" and status == "idle")
        if just_finished or finished_transition:
            if completion_brief.strip():
                self.state.pending_completion_brief = completion_brief.strip()
            self.state.must_brief_before_dispatch = True

    def pop_pending_completion_brief(self) -> str:
        brief = self.state.pending_completion_brief
        self.state.pending_completion_brief = ""
        if brief:
            self.state.must_brief_before_dispatch = False
        return brief

    def check_dispatch(self) -> Optional[str]:
        if not self.state.queued_task:
            return None
        if self.state.agent_status != "idle":
            return None
        if self.state.must_brief_before_dispatch:
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
        self.conversation.clear()
        self.state.scratchpad_task = ""
        self.state.queued_task = ""
        self.state.agent_status = "idle"
        self.state.agent_current_task = ""
        self.state.agent_turns.clear()
        self.state.pending_completion_brief = ""
        self.state.must_brief_before_dispatch = False
