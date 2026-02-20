# 🦀 ClawProxy

**OpenClaw Observer & Planner Client** — a sidecar voice interface and session monitor for [OpenClaw](https://openclaw.ai).

ClawProxy connects to your local OpenClaw gateway via WebSocket, provides a real-time view of agent sessions (tool calls, chain-of-thought, live status), and includes a voice-enabled planner for hands-free task drafting.

## Features

- **Live session observer** — watch tool calls, assistant output, and CoT in real time
- **Multi-session selector** — browse and switch between active OpenClaw sessions
- **Planner agent** — brainstorm and refine tasks via text or voice before committing
- **Task dispatch** — send drafted tasks to any session as a user message
- **Voice pipeline** — wakeword detection, VAD, STT (Whisper), TTS (Kokoro)
- **Gateway auto-discovery** — finds your local OpenClaw gateway automatically

## Quick Start

```bash
# Clone
git clone https://github.com/yourname/clawproxy.git
cd clawproxy

# Install (creates clawproxy command)
pip install -e .

# Setup config (auto-discovers gateway)
clawproxy setup

# Launch
clawproxy launch
```

Then open `http://localhost:37374` in your browser.

## Requirements

- Python 3.10+
- A running [OpenClaw](https://openclaw.ai) gateway on the same machine
- Node.js 18+ (for frontend development only)

## Voice (optional)

Install voice dependencies for wakeword, STT, and TTS:

```bash
pip install -e ".[voice]"
```

Requires a Whisper model in `models/whisper/` and Kokoro TTS.

## CLI Reference

```
clawproxy launch     Start the server
  --port PORT        Server port (default: 37374)
  --host HOST        Bind host (default: 0.0.0.0)
  --gateway-url URL  Override gateway WebSocket URL
  --gateway-token T  Override gateway auth token
  --reload           Enable hot-reload (dev mode)
  -v, --verbose      Verbose logging

clawproxy status     Check proxy and gateway health
clawproxy setup      Initialize ~/.clawproxy config
  --force            Overwrite existing config
clawproxy uninstall  Remove ~/.clawproxy data
  -y, --yes          Skip confirmation
  --purge            Also remove venv
clawproxy version    Show version
```

## Architecture

```
┌─────────────────┐     WS (proto v3)     ┌──────────────┐
│  ClawProxy       │◄───────────────────── │  OpenClaw     │
│  (FastAPI + WS)  │  agent/chat/tool events│  Gateway     │
│                  │──────────────────────►│              │
│  ┌────────────┐  │   chat.send           │              │
│  │ Planner    │  │                       └──────────────┘
│  │ Agent      │  │
│  └────────────┘  │
│  ┌────────────┐  │     WS + REST         ┌──────────────┐
│  │ Voice      │  │◄───────────────────── │  Svelte       │
│  │ Pipeline   │  │                       │  Frontend     │
│  └────────────┘  │                       └──────────────┘
└─────────────────┘
```

## Development

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
clawproxy launch --reload -v
```

## License

MIT
