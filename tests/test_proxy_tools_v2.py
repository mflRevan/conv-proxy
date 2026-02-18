"""
Conv-proxy test harness v2: Adjusted for actual model behavior.
The model outputs [function_name(args)] inline without special tokens.
"""
import json
import re
import time
import sys

sys.path.insert(0, ".")
from llm.lfm_instruct_engine import LFMInstructEngine

# Parse [function_name(key="value", ...)] patterns
TOOL_CALL_RE = re.compile(
    r'\[(\w+)\((.*?)\)\]',
    re.DOTALL
)

def parse_tool_calls(text: str) -> list[dict]:
    """Extract tool calls from model output."""
    calls = []
    for m in TOOL_CALL_RE.finditer(text):
        name = m.group(1)
        args_str = m.group(2).strip()
        calls.append({"name": name, "args_raw": args_str, "full": m.group(0)})
    return calls

def strip_tool_calls(text: str) -> str:
    return TOOL_CALL_RE.sub("", text).strip()

# ─── Mock Context ───

MOCK_PROJECT_SUMMARY = """## Active Projects
- **conv-proxy**: Local conversational AI proxy for Jarvis. Building Svelte frontend + LFM Instruct engine with GPU. Status: functional prototype.
- **ml-pipeline**: ML training pipeline for neural style transfer. Status: on hold.

## Recent Decisions
- Switched from LFM Thinking to LFM Instruct (90 tok/s GPU)
- Kokoro 82M TTS, Moonshine-tiny STT
- WSL2 + RTX 3070 Ti dev environment
"""

MOCK_AGENT_BUSY = """## Live Agent Status: BUSY
Current task: "Push conv-proxy changes to GitHub, test F16 model throughput"
Recent:
- [16:48] Rebuilt llama-cpp-python with CUDA
- [16:50] Benchmarked Instruct Q4_0: 90 tok/s GPU
- [16:55] Built Svelte frontend, pushed to GitHub
"""

MOCK_AGENT_IDLE = """## Live Agent Status: IDLE
Last completed: "Pushed conv-proxy to GitHub" (2 min ago)
"""

TOOLS_JSON = [
    {
        "name": "interrupt_agent",
        "description": "Interrupt the main agent's current task. ONLY use when user EXPLICITLY says stop/cancel/interrupt/abort.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "set_queued_task",
        "description": "Set/update the queued task draft (overwrites previous). Call whenever user describes or refines what they want done next. Write a clear, standalone task prompt.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Complete standalone task prompt for the main agent"}
            },
            "required": ["task"]
        }
    }
]

SYSTEM_PROMPT = f"""You are Jarvis Proxy, a lightweight voice interface between user Aiman and the main Jarvis agent.

RESPONSE RULES:
- 1-3 sentences max. You are spoken aloud.
- Be direct. No filler, no narration.

TOOLS:
List of tools: {json.dumps(TOOLS_JSON)}

When calling a tool, write it as: [function_name(param="value")]
Then write your spoken response after it on the same line or next line.

CRITICAL RULES:
- interrupt_agent: ONLY when user EXPLICITLY says "stop", "cancel", "interrupt", "abort". NEVER otherwise.
- set_queued_task: Call whenever user discusses a task. Synthesize into a complete standalone prompt.
- For normal conversation (greetings, questions, status), just respond without tools.
"""


def build_messages(live_ctx: str, conv: list[tuple[str, str]], queued: str = "", user_msg: str = "") -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    ctx = MOCK_PROJECT_SUMMARY + "\n" + live_ctx
    if queued:
        ctx += f"\n## Queued Task Draft\n{queued}\n"
    msgs.append({"role": "system", "content": ctx})
    for role, text in conv:
        msgs.append({"role": role, "content": text})
    if user_msg:
        msgs.append({"role": "user", "content": user_msg})
    return msgs


class TestRunner:
    def __init__(self, engine):
        self.engine = engine
        self.results = []

    def test(self, name: str, msgs: list[dict], check_fn, max_tokens=256):
        t0 = time.monotonic()
        raw = self.engine.chat(msgs, max_tokens=max_tokens, temperature=0.3)
        elapsed_ms = (time.monotonic() - t0) * 1000
        calls = parse_tool_calls(raw)
        visible = strip_tool_calls(raw)
        call_names = [c["name"] for c in calls]

        passed, detail = check_fn(call_names, calls, visible, raw)
        status = "✅" if passed else "❌"
        print(f"{status} {name} ({elapsed_ms:.0f}ms)")
        print(f"   tools: {call_names}  visible: {visible[:100]}")
        if not passed:
            print(f"   RAW: {raw[:200]}")
        self.results.append((name, passed, elapsed_ms))

    def summary(self):
        print(f"\n{'='*60}")
        p = sum(1 for _, ok, _ in self.results if ok)
        avg = sum(ms for _, _, ms in self.results) / len(self.results)
        print(f"PASSED: {p}/{len(self.results)} | AVG latency: {avg:.0f}ms")


def main():
    print("Loading engine (GPU)...\n")
    engine = LFMInstructEngine(
        model_path="models/lfm-instruct/LFM2.5-1.2B-Instruct-Q4_0.gguf",
        n_gpu_layers=99, n_ctx=4096
    )
    t = TestRunner(engine)

    # 1. Status query — no tools
    t.test("status_query",
        build_messages(MOCK_AGENT_BUSY, [], user_msg="What's the agent working on?"),
        lambda names, calls, vis, raw: (not names, "ok"))

    # 2. Greeting — no tools
    t.test("greeting",
        build_messages(MOCK_AGENT_IDLE, [], user_msg="Hey, how's it going?"),
        lambda names, calls, vis, raw: (not names, "ok"))

    # 3. Queue a task
    t.test("queue_task",
        build_messages(MOCK_AGENT_BUSY, [], user_msg="When it's done, run STT benchmarks on all backends."),
        lambda names, calls, vis, raw: ("set_queued_task" in names, f"calls: {names}"))

    # 4. Refine queued task
    conv = [
        ("user", "After the agent finishes, benchmark all STT backends."),
        ("assistant", '[set_queued_task(task="Run STT benchmark on all backends and compare accuracy and latency.")]Got it, queued.'),
    ]
    t.test("refine_task",
        build_messages(MOCK_AGENT_BUSY, conv,
            queued="Run STT benchmark on all backends and compare accuracy and latency.",
            user_msg="Also include word error rate. Test 5 samples each."),
        lambda names, calls, vis, raw: ("set_queued_task" in names, f"calls: {names}"))

    # 5. No interrupt on context change
    t.test("no_interrupt_context_change",
        build_messages(MOCK_AGENT_BUSY, [], user_msg="I changed my mind, let's use React instead of Svelte."),
        lambda names, calls, vis, raw: ("interrupt_agent" not in names, f"calls: {names}"))

    # 6. Explicit interrupt
    t.test("explicit_interrupt",
        build_messages(MOCK_AGENT_BUSY, [], user_msg="Stop the agent. Cancel what it's doing."),
        lambda names, calls, vis, raw: ("interrupt_agent" in names, f"calls: {names}"))

    # 7. No interrupt on frustration
    t.test("no_interrupt_frustration",
        build_messages(MOCK_AGENT_BUSY, [], user_msg="Ugh, this is taking forever."),
        lambda names, calls, vis, raw: ("interrupt_agent" not in names, f"calls: {names}"))

    # 8. Multi-turn refinement
    conv = [
        ("user", "Add dark mode toggle to the webapp."),
        ("assistant", '[set_queued_task(task="Add dark mode toggle to conv-proxy webapp.")]Noted.'),
        ("user", "Persist in localStorage."),
        ("assistant", '[set_queued_task(task="Add dark mode toggle to conv-proxy webapp. Persist preference in localStorage.")]Updated.'),
    ]
    t.test("multi_turn_refine",
        build_messages(MOCK_AGENT_IDLE, conv,
            queued="Add dark mode toggle to conv-proxy webapp. Persist preference in localStorage.",
            user_msg="Default should match system preference."),
        lambda names, calls, vis, raw: ("set_queued_task" in names and "interrupt_agent" not in names, f"calls: {names}"))

    # 9. Large context latency
    big = MOCK_PROJECT_SUMMARY + ("Additional context. " * 500) + MOCK_AGENT_BUSY
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": big},
            {"role": "user", "content": "What's the agent doing?"}]
    t.test("large_context",
        msgs,
        lambda names, calls, vis, raw: (len(vis) > 5, "ok"))

    # 10. Pure conversation
    t.test("pure_conversation",
        build_messages(MOCK_AGENT_IDLE, [], user_msg="What's the weather like?"),
        lambda names, calls, vis, raw: ("interrupt_agent" not in names, "ok"))

    t.summary()


if __name__ == "__main__":
    main()
