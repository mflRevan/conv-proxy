# conv-proxy

A conversational proxy that combines LiquidAI's LFM models with Kokoro TTS and optional multi-backend STT.

## Architecture
- **LLM**: `llm/LFMThinkingEngine` (default) and `llm/LFMAudioEngine` for the GGUF audio server.
- **TTS**: `tts/KokoroStreamingTTS` provides streaming synthesis with sentence, word-chunk, and native chunking.
- **STT**: `stt/` supports whisper.cpp, Moonshine v2, and a browser-only Web Speech API backend.
- **Web UI**: `webapp/` offers a FastAPI + WebSocket chat interface with optional TTS playback and mic input.

## Setup
```bash
cd conv-proxy
source .venv-kokoro/bin/activate
pip install -r requirements.txt
```

Ensure `.env` contains your `HF_TOKEN` for HuggingFace downloads and `OPENROUTER_API_KEY` for proxy LLM calls.

Wakeword (default-on) uses OpenWakeWord (`hey jarvis`). If `openwakeword` is missing, proxy falls back gracefully to VAD-only mode.

### Download GGUF assets
```bash
mkdir -p models/lfm-audio runners
# Download from LiquidAI/LFM2.5-Audio-1.5B-GGUF
# Required files:
# - LFM2.5-Audio-1.5B-Q4_0.gguf
# - mmproj-LFM2.5-Audio-1.5B-Q4_0.gguf
# - vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf
# - tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf
# Runner:
# - runners/llama-liquid-audio-ubuntu-x64.zip (unzip to runners/llama-liquid-audio-server)
```

### Build whisper.cpp + models
```bash
# Build whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp /tmp/whisper-cpp
cd /tmp/whisper-cpp && cmake -B build && cmake --build build -j$(nproc)
cp build/bin/whisper-cli /path/to/conv-proxy/runners/whisper-cli

# Download models
mkdir -p models/whisper
# Download ggml-tiny.bin and ggml-small.bin from ggerganov/whisper.cpp
# ggml-medium.bin is supported but not downloaded by default (too large).
```

### Moonshine
```bash
pip install useful-moonshine-onnx
# Fallback:
# pip install moonshine
```

> **Note:** Browser Web Speech API only works over HTTPS or localhost.
> On LAN (phone access via IP), it may not work unless you serve via HTTPS.

## Usage (production CLI)
Use the new CLI wrapper (no `run.sh` required):

```bash
cd conv-proxy
python3 convproxy_cli.py onboard
python3 convproxy_cli.py start
python3 convproxy_cli.py status
python3 convproxy_cli.py bind-main     # safe bind to main session (dispatch OFF)
python3 convproxy_cli.py bridge-status
```

Other useful commands:
```bash
python3 convproxy_cli.py sessions       # list OpenClaw sessions
python3 convproxy_cli.py agents         # list available agents
python3 convproxy_cli.py bind <session_id> --dispatch   # live dispatch ON
python3 convproxy_cli.py dispatch on|off
python3 convproxy_cli.py monitor
python3 convproxy_cli.py stop
```

Frontend is served by FastAPI at `http://localhost:37374`.

Available STT backends (depending on installed binaries/models):
- whisper-tiny
- whisper-small
- whisper-medium (supported, not downloaded by default)
- moonshine-tiny
- moonshine-base
- browser

Benchmarks:
```bash
python -m benchmarks.llm_thinking_benchmark
python -m benchmarks.tts_benchmark
python -m benchmarks.stt_benchmark
```

Sample STT benchmark (CPU, 16kHz TTS input):
```
whisper-tiny   | time 0.74s | WER 0.00 | RTF 0.17
whisper-small  | time 2.14s | WER 0.00 | RTF 0.49
moonshine-tiny | time 0.17s | WER 0.00 | RTF 0.04
moonshine-base | time 0.30s | WER 0.00 | RTF 0.07
```

Python API:
```python
from proxy.conv_proxy import ConversationalProxy

proxy = ConversationalProxy()
for audio in proxy.process_input("Hello there!"):
    # stream audio chunks
    pass
```

## Tests
```bash
pytest -q
```

## Planned
- Parakeet TDT (1.1B) STT backend (requires NVIDIA NeMo)
