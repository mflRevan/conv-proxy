# conv-proxy

A conversational proxy that combines LiquidAI's LFM2.5-1.2B-Thinking with Kokoro TTS for low-latency voice interactions.

## Architecture
- **LLM**: `llm/LFMEngine` wraps the LFM2.5 model with ChatML-style formatting and tool-call parsing.
- **TTS**: `tts/KokoroStreamingTTS` provides streaming synthesis with sentence, word-chunk, and native chunking.
- **Proxy**: `proxy/ConversationalProxy` bridges LLM text output into streaming audio and maintains a lightweight conversation history.

## Setup
```bash
cd conv-proxy
source .venv-kokoro/bin/activate
pip install -r requirements.txt
```

Ensure `.env` contains your `HF_TOKEN` for HuggingFace downloads.

## Usage
```bash
python -m benchmarks.tts_benchmark
python -m benchmarks.llm_benchmark
```

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
