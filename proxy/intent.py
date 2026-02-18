"""
Conv-proxy engine: Hybrid approach for the 1.2B model.

Architecture:
- STOP detection: keyword-based (reliable, instant)
- Task synthesis: LLM generates/refines a task draft from conversation
- Response generation: LLM generates spoken reply with context
- The "set_queued_task" is managed by the proxy layer, not by model tool calls

The model is used for what it's good at: generating text.
The proxy layer handles all logic/routing.
"""
import re
import time
from dataclasses import dataclass, field
from typing import Optional

STOP_PATTERNS = [
    r"\bstop\b", r"\bcancel\b", r"\babort\b", r"\binterrupt\b",
    r"\bhalt\b", r"\bkill\b", r"\bnever\s*mind\b", r"\bforget\s*it\b",
    r"\bdon'?t\s+do\s+that\b",
]
_STOP_RE = re.compile("|".join(STOP_PATTERNS), re.IGNORECASE)

# For determining if message potentially contains actionable content
# (vs pure chat like greetings/thanks/frustration)
ACTION_VERBS = {
    "add", "build", "create", "deploy", "fix", "implement", "install",
    "make", "move", "refactor", "remove", "run", "set", "setup", "switch",
    "test", "update", "upgrade", "write", "benchmark", "configure",
    "change", "delete", "check", "enable", "disable", "optimize",
    "integrate", "migrate", "push", "pull", "merge", "commit",
}


def detect_stop(text: str) -> bool:
    """Keyword-based stop detection. Fast and reliable."""
    return bool(_STOP_RE.search(text))


# Refinement words (suggest modifying existing draft)
REFINE_WORDS = {"also", "additionally", "plus", "and", "include", "make sure", "but", "instead", "actually"}


def has_refine_intent(text: str) -> bool:
    """Check if message refines an existing task draft."""
    lower = text.lower()
    return any(w in lower for w in REFINE_WORDS)


def has_action_intent(text: str) -> bool:
    """Heuristic: does the message contain action verbs suggesting a task?"""
    words = set(re.findall(r'\b\w+\b', text.lower()))
    return bool(words & ACTION_VERBS)


@dataclass
class ProxyState:
    """Manages the proxy's conversational state."""
    queued_task: str = ""
    agent_status: str = "idle"  # idle | busy
    agent_current_task: str = ""
    idle_timer: float = 0.0  # seconds since last user input
    dispatch_delay: float = 10.0  # seconds to wait before dispatching

    def should_dispatch(self) -> bool:
        """Check if queued task should be sent to agent."""
        return (
            self.queued_task
            and self.agent_status == "idle"
            and self.idle_timer >= self.dispatch_delay
        )


SYNTH_TASK_PROMPT = """You are a task writer. Given a conversation about what the user wants done, write a clear standalone task instruction.

Current task draft (may be empty):
{current_draft}

Write an UPDATED task incorporating the user's latest message. Output ONLY the task text.
If the conversation is just chat (greeting, question, complaint), output: NO_TASK"""

RESPOND_PROMPT = """You are Jarvis Proxy, a voice assistant. Keep responses to 1-2 sentences.

Context:
- Agent status: {agent_status}
{agent_task_line}
{queued_task_line}

Respond naturally to the user. Be concise and direct."""


def build_synth_messages(conversation_history: list[dict], current_draft: str) -> list[dict]:
    """Build messages for task synthesis."""
    prompt = SYNTH_TASK_PROMPT.replace("{current_draft}", current_draft or "(empty)")
    msgs = [{"role": "system", "content": prompt}]
    # Include last few turns for context
    for m in conversation_history[-6:]:
        msgs.append(m)
    return msgs


def build_respond_messages(state: ProxyState, conversation_history: list[dict]) -> list[dict]:
    """Build messages for response generation."""
    agent_task = f"- Current task: {state.agent_current_task}" if state.agent_current_task else ""
    queued = f"- Queued task: {state.queued_task}" if state.queued_task else ""
    prompt = RESPOND_PROMPT.format(
        agent_status=state.agent_status,
        agent_task_line=agent_task,
        queued_task_line=queued,
    )
    msgs = [{"role": "system", "content": prompt}]
    for m in conversation_history[-10:]:
        msgs.append(m)
    return msgs
