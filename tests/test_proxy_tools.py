"""
Conv-proxy test harness: tests the LFM Instruct model's ability to handle
the 2-tool proxy architecture with mock context injection.

Tests:
1. Basic conversation (no tool use)
2. Queued task refinement via set_queued_task
3. Interrupt detection (only on explicit request)
4. Context awareness (live agent activity, past turns)
5. Latency under different context sizes
"""
import json
import re
import time
import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, ".")
from llm.lfm_instruct_engine import LFMInstructEngine

TOOL_CALL_RE = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.DOTALL)

# ─── Mock Context ───

MOCK_PROJECT_SUMMARY = """## Active Projects
- **conv-proxy**: Local conversational AI proxy layer for Jarvis agent. Currently building Svelte frontend + LFM Instruct engine with GPU acceleration. Status: functional prototype, testing tool calling.
- **ml-pipeline**: ML training pipeline for neural style transfer. Status: on hold, blocked on dataset preprocessing.

## Recent Decisions
- Switched from LFM Thinking to LFM Instruct for proxy (no thinking overhead, 90 tok/s GPU)
- Using Kokoro 82M TTS, Moonshine-tiny STT
- WSL2 + RTX 3070 Ti as primary dev environment
"""

MOCK_LIVE_AGENT_CONTEXT = """## Live Agent Activity (Jarvis Main)
Status: BUSY — executing task
Current task: "Push conv-proxy changes to GitHub, test F16 model throughput"
Recent actions:
- [16:48] Rebuilt llama-cpp-python with CUDA support
- [16:50] Benchmarked Instruct Q4_0: 90 tok/s GPU vs 31 tok/s CPU
- [16:52] Downloaded Q8_0 model (80 tok/s GPU)
- [16:55] Built Svelte frontend, pushed to GitHub
- [16:58] Starting F16 download and proxy architecture design
"""

MOCK_LIVE_AGENT_IDLE = """## Live Agent Activity (Jarvis Main)
Status: IDLE — no active task
Last completed: "Pushed conv-proxy to GitHub" (2 min ago)
"""

TOOLS_JSON = [
    {
        "name": "interrupt_agent",
        "description": "EMERGENCY ONLY: Interrupt the main Jarvis agent's current task loop. Use ONLY when the user EXPLICITLY asks to stop/cancel/interrupt the agent. Never call this preemptively or based on inference.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "set_queued_task",
        "description": "Set or update the queued task draft. This overwrites the previous draft. The task is a standalone prompt/instruction that will be sent to the main agent when: (1) agent is idle AND (2) no user speech/input for 10 seconds. Call this whenever the user discusses, refines, or clarifies what they want done next.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The complete, standalone task prompt to queue for the main agent"
                }
            },
            "required": ["task"]
        }
    }
]

SYSTEM_PROMPT = f"""You are Jarvis Proxy, a lightweight local conversational interface. You relay between the user (Aiman) and the main Jarvis cloud agent.

RULES:
- Keep responses SHORT (1-3 sentences). You will be spoken aloud via TTS.
- Be direct, concise, efficient. No filler.
- You have access to live context about what the main agent is doing.
- You can see the user's past conversation history.

TOOLS:
List of tools: {json.dumps(TOOLS_JSON)}

TOOL RULES:
- set_queued_task: Call this whenever the user describes, refines, or discusses a task they want done. Synthesize their intent into a clear standalone prompt. Overwrite freely — it's a scratchpad.
- interrupt_agent: ONLY call when user EXPLICITLY says "stop", "cancel", "interrupt", "abort" the agent. NEVER call based on inference or context changes.

OUTPUT FORMAT:
- Tool calls go between <|tool_call_start|> and <|tool_call_end|> tokens.
- Your spoken response comes AFTER tool calls (or alone if no tools needed).
- Never narrate tool usage. Just call and respond naturally.
"""


def build_messages(
    live_context: str,
    conversation: list[tuple[str, str]],
    queued_task: Optional[str] = None,
    user_msg: str = "",
) -> list[dict]:
    """Build the full message list for the proxy."""
    msgs = []

    # System prompt
    msgs.append({"role": "system", "content": SYSTEM_PROMPT})

    # Injected context (as system message)
    ctx = MOCK_PROJECT_SUMMARY + "\n" + live_context
    if queued_task:
        ctx += f"\n## Current Queued Task Draft\n{queued_task}\n"
    msgs.append({"role": "system", "content": ctx})

    # Conversation history
    for role, text in conversation:
        msgs.append({"role": role, "content": text})

    # Current user message
    if user_msg:
        msgs.append({"role": "user", "content": user_msg})

    return msgs


def parse_response(raw: str) -> dict:
    """Parse tool calls and visible text from model output."""
    tool_calls = []
    for m in TOOL_CALL_RE.finditer(raw):
        tool_calls.append(m.group(1).strip())
    visible = TOOL_CALL_RE.sub("", raw).strip()
    return {"tool_calls": tool_calls, "visible": visible, "raw": raw}


@dataclass
class TestResult:
    name: str
    passed: bool
    details: str
    ttft_ms: float = 0
    total_ms: float = 0
    tokens: int = 0
    tok_s: float = 0
    raw_output: str = ""


def run_test(engine, name: str, messages: list[dict], check_fn, max_tokens: int = 256) -> TestResult:
    """Run a single test case."""
    t0 = time.monotonic()
    raw = engine.chat(messages, max_tokens=max_tokens, temperature=0.3)
    elapsed = (time.monotonic() - t0) * 1000
    parsed = parse_response(raw)

    # Rough token estimate
    tok_est = len(raw.split())
    tok_s = tok_est / (elapsed / 1000) if elapsed > 0 else 0

    passed, details = check_fn(parsed)

    return TestResult(
        name=name, passed=passed, details=details,
        total_ms=elapsed, tokens=tok_est, tok_s=tok_s,
        raw_output=raw
    )


def main():
    print("Loading LFM Instruct engine (GPU)...")
    engine = LFMInstructEngine(
        model_path="models/lfm-instruct/LFM2.5-1.2B-Instruct-Q4_0.gguf",
        n_gpu_layers=99, n_ctx=4096
    )
    print("Engine loaded.\n")

    results: list[TestResult] = []

    # ─── Test 1: Basic conversation (no tools) ───
    msgs = build_messages(MOCK_LIVE_AGENT_CONTEXT, [], user_msg="Hey Jarvis, what's the agent working on right now?")
    r = run_test(engine, "basic_status_query", msgs,
        lambda p: (
            not p["tool_calls"] and len(p["visible"]) > 10,
            f"No tools called, response: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 2: Simple greeting (no tools) ───
    msgs = build_messages(MOCK_LIVE_AGENT_IDLE, [], user_msg="Hey, how's it going?")
    r = run_test(engine, "basic_greeting", msgs,
        lambda p: (
            not p["tool_calls"],
            f"No tools called: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 3: Queue a task ───
    msgs = build_messages(MOCK_LIVE_AGENT_CONTEXT, [], user_msg="When the agent is done, have it run the STT benchmark on all backends and compare accuracy.")
    r = run_test(engine, "queue_task_simple", msgs,
        lambda p: (
            any("set_queued_task" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls']}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 4: Refine a queued task ───
    conv = [
        ("user", "After the agent finishes, have it benchmark all STT backends."),
        ("assistant", '<|tool_call_start|>[set_queued_task(task="Run STT benchmark on all backends (whisper-tiny, whisper-small, moonshine-tiny, moonshine-base) and compare accuracy and latency.")]<|tool_call_end|>Got it, I\'ll queue that up.'),
    ]
    msgs = build_messages(
        MOCK_LIVE_AGENT_CONTEXT, conv,
        queued_task="Run STT benchmark on all backends (whisper-tiny, whisper-small, moonshine-tiny, moonshine-base) and compare accuracy and latency.",
        user_msg="Actually, also include word error rate in the comparison. And test with at least 5 audio samples each."
    )
    r = run_test(engine, "refine_queued_task", msgs,
        lambda p: (
            any("set_queued_task" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls'][:1]}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 5: Should NOT interrupt (implicit context change) ───
    msgs = build_messages(MOCK_LIVE_AGENT_CONTEXT, [], user_msg="Hmm, I changed my mind about the frontend approach. Let's use React instead of Svelte.")
    r = run_test(engine, "no_interrupt_on_context_change", msgs,
        lambda p: (
            not any("interrupt_agent" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls']}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 6: Should interrupt (explicit request) ───
    msgs = build_messages(MOCK_LIVE_AGENT_CONTEXT, [], user_msg="Stop the agent. Cancel what it's doing right now.")
    r = run_test(engine, "interrupt_explicit", msgs,
        lambda p: (
            any("interrupt_agent" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls']}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 7: Should NOT interrupt (vague frustration) ───
    msgs = build_messages(MOCK_LIVE_AGENT_CONTEXT, [], user_msg="Ugh, this is taking forever.")
    r = run_test(engine, "no_interrupt_on_frustration", msgs,
        lambda p: (
            not any("interrupt_agent" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls']}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 8: Multi-turn task building ───
    conv = [
        ("user", "I want to add a dark mode toggle to the webapp."),
        ("assistant", '<|tool_call_start|>[set_queued_task(task="Add a dark mode toggle to the conv-proxy webapp frontend.")]<|tool_call_end|>Noted, I\'ll queue a dark mode toggle task.'),
        ("user", "Make sure it persists in localStorage."),
        ("assistant", '<|tool_call_start|>[set_queued_task(task="Add a dark mode toggle to the conv-proxy webapp frontend. Persist the preference in localStorage.")]<|tool_call_end|>Updated — it\'ll save the preference.'),
    ]
    msgs = build_messages(
        MOCK_LIVE_AGENT_IDLE, conv,
        queued_task="Add a dark mode toggle to the conv-proxy webapp frontend. Persist the preference in localStorage.",
        user_msg="Oh and the default should match the system preference."
    )
    r = run_test(engine, "multi_turn_task_refinement", msgs,
        lambda p: (
            any("set_queued_task" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls'][:1]}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 9: Latency with large context (16K tokens) ───
    big_context = MOCK_PROJECT_SUMMARY + "\n" + ("Additional context line. " * 500) + "\n" + MOCK_LIVE_AGENT_CONTEXT
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": big_context},
        {"role": "user", "content": "What's the agent doing?"},
    ]
    r = run_test(engine, "latency_large_context", msgs,
        lambda p: (
            len(p["visible"]) > 5,
            f"Response: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Test 10: Conversational (no task, just chat) ───
    msgs = build_messages(MOCK_LIVE_AGENT_IDLE, [], user_msg="What time is it in Berlin?")
    r = run_test(engine, "conversational_no_task", msgs,
        lambda p: (
            not any("interrupt" in tc for tc in p["tool_calls"]),
            f"Tool calls: {p['tool_calls']}, visible: {p['visible'][:120]}"
        ))
    results.append(r)

    # ─── Print results ───
    print("\n" + "=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    passed = sum(1 for r in results if r.passed)
    for r in results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        print(f"\n{status} | {r.name} | {r.total_ms:.0f}ms | ~{r.tok_s:.0f} tok/s")
        print(f"  {r.details}")
        if not r.passed:
            print(f"  RAW: {r.raw_output[:200]}")

    print(f"\n{'=' * 80}")
    print(f"TOTAL: {passed}/{len(results)} passed")
    avg_ms = sum(r.total_ms for r in results) / len(results)
    print(f"AVG latency: {avg_ms:.0f}ms")
    print(f"AVG tok/s: {sum(r.tok_s for r in results) / len(results):.0f}")


if __name__ == "__main__":
    main()
