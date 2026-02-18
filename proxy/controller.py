"""
Conv-proxy controller: manages the full proxy pipeline.

Architecture:
- STOP: keyword-based (instant, reliable)
- TASK: action verb heuristic → LLM synthesizes/refines draft
- CHAT: LLM generates spoken reply with context
- Dispatch: queued task sent to agent when idle + no input for N seconds
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from proxy.intent import (
    detect_stop, has_action_intent, has_refine_intent,
    ProxyState, build_synth_messages, build_respond_messages,
    SYNTH_TASK_PROMPT, RESPOND_PROMPT,
)


@dataclass
class ProxyController:
    """Manages proxy state, intent routing, and task dispatch."""
    engine: object  # LFMInstructEngine
    state: ProxyState = field(default_factory=ProxyState)
    conversation: list[dict] = field(default_factory=list)
    max_history: int = 30  # 15 pairs

    # Callbacks (set by webapp)
    on_stop: Optional[Callable] = None  # called when user requests stop
    on_dispatch: Optional[Callable[[str], None]] = None  # called when task dispatched
    on_task_updated: Optional[Callable[[str], None]] = None  # called when draft changes

    _idle_task: Optional[asyncio.Task] = None
    _last_input_time: float = 0.0

    def _trim_history(self):
        if len(self.conversation) > self.max_history:
            self.conversation = self.conversation[-self.max_history:]

    def process_message(self, user_msg: str) -> dict:
        """
        Process a user message through the full pipeline.
        Returns: {action, reply, task_updated, task_draft, timings}
        """
        result = {
            "action": "chat",
            "reply": "",
            "task_updated": False,
            "task_draft": self.state.queued_task,
            "timings": {},
        }
        self._last_input_time = time.monotonic()
        t_total = time.monotonic()

        # ─── STOP ───
        if detect_stop(user_msg):
            result["action"] = "stop"
            self.conversation.append({"role": "user", "content": user_msg})

            t0 = time.monotonic()
            reply = self.engine.chat([
                {"role": "system", "content": "Confirm stopping the agent. 1 sentence max."},
                {"role": "user", "content": user_msg},
            ], max_tokens=30, temperature=0.3)
            result["timings"]["respond"] = (time.monotonic() - t0) * 1000
            result["reply"] = reply.strip()

            self.conversation.append({"role": "assistant", "content": result["reply"]})
            self.state.queued_task = ""
            result["task_draft"] = ""
            self._trim_history()

            if self.on_stop:
                self.on_stop()

            result["timings"]["total"] = (time.monotonic() - t_total) * 1000
            return result

        self.conversation.append({"role": "user", "content": user_msg})

        # ─── TASK synthesis ───
        should_synth = has_action_intent(user_msg) or (
            self.state.queued_task and has_refine_intent(user_msg)
        )

        if should_synth:
            t0 = time.monotonic()
            synth_msgs = build_synth_messages(self.conversation, self.state.queued_task)
            raw = self.engine.chat(synth_msgs, max_tokens=150, temperature=0.3)
            result["timings"]["synth"] = (time.monotonic() - t0) * 1000

            new_task = raw.strip()
            if new_task and "NO_TASK" not in new_task.upper():
                self.state.queued_task = new_task
                result["task_updated"] = True
                result["action"] = "task"
                result["task_draft"] = new_task

                if self.on_task_updated:
                    self.on_task_updated(new_task)

        # ─── Response generation ───
        t0 = time.monotonic()
        resp_msgs = build_respond_messages(self.state, self.conversation)
        reply = self.engine.chat(resp_msgs, max_tokens=60, temperature=0.5)
        result["timings"]["respond"] = (time.monotonic() - t0) * 1000
        result["reply"] = reply.strip()

        self.conversation.append({"role": "assistant", "content": result["reply"]})
        self._trim_history()

        result["timings"]["total"] = (time.monotonic() - t_total) * 1000
        return result

    def update_agent_context(self, status: str, current_task: str = "", live_turns: list[dict] = None):
        """Update injected agent context (called by the OpenClaw integration layer)."""
        self.state.agent_status = status
        self.state.agent_current_task = current_task

    def reset(self):
        """Reset conversation and task state."""
        self.conversation.clear()
        self.state.queued_task = ""
        self.state.agent_status = "idle"
        self.state.agent_current_task = ""

    async def check_dispatch(self) -> Optional[str]:
        """Check if queued task should be dispatched. Called periodically."""
        if not self.state.queued_task:
            return None
        if self.state.agent_status != "idle":
            return None

        elapsed = time.monotonic() - self._last_input_time
        if elapsed < self.state.dispatch_delay:
            return None

        # Dispatch!
        task = self.state.queued_task
        self.state.queued_task = ""
        if self.on_dispatch:
            self.on_dispatch(task)
        return task
