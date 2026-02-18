# conv-proxy

A conversational proxy that combines LiquidAI's LFM2.5-Audio GGUF server with Kokoro TTS for low-latency voice interactions.

## Architecture
- **LLM**: `llm/LFMAudioEngine` wraps the LFM2.5-Audio GGUF server via OpenAI-compatible API.
- **TTS**: `tts/KokoroStreamingTTS` provides streaming synthesis with sentence, word-chunk, and native chunking.
- **Proxy**: `proxy/ConversationalProxy` bridges LLM text output into streaming audio and maintains a lightweight conversation history.
- **Web UI**: `webapp/` offers a FastAPI + WebSocket chat interface with optional TTS playback.

## Setup
```bash
cd conv-proxy
source .venv-kokoro/bin/activate
pip install -r requirements.txt
```

Ensure `.env` contains your `HF_TOKEN` for HuggingFace downloads.

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

## Usage
Run the web UI:
```bash
./run.sh
# Open http://localhost:8000
```

Benchmarks:
```bash
python -m benchmarks.llm_benchmark
python -m benchmarks.tts_benchmark
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
