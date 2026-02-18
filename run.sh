#!/usr/bin/env bash
set -euo pipefail

ENGINE_TYPE="audio"
MODEL_DIR="models/lfm-audio"
RUNNER="runners/llama-liquid-audio-ubuntu-x64/llama-liquid-audio-server"
PORT=8090

while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine)
      ENGINE_TYPE="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$ENGINE_TYPE" == "audio" ]]; then
  if [[ ! -x "$RUNNER" ]]; then
    echo "Runner not found or not executable: $RUNNER" >&2
    exit 1
  fi

  if [[ ! -f "$MODEL_DIR/LFM2.5-Audio-1.5B-Q4_0.gguf" ]]; then
    echo "Model files missing. Download the GGUF files first." >&2
    exit 1
  fi

  LD_LIBRARY_PATH="$(dirname "$RUNNER"):${LD_LIBRARY_PATH:-}" \
  "$RUNNER" -m "$MODEL_DIR/LFM2.5-Audio-1.5B-Q4_0.gguf" \
    -mm "$MODEL_DIR/mmproj-LFM2.5-Audio-1.5B-Q4_0.gguf" \
    -mv "$MODEL_DIR/vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf" \
    --tts-speaker-file "$MODEL_DIR/tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf" \
    --port "$PORT" \
    > lfm_server.log 2>&1 &

  SERVER_PID=$!

  echo "Starting LFM server (pid $SERVER_PID)..."

  until curl -s "http://127.0.0.1:${PORT}/v1/models" >/dev/null; do
    sleep 1
    echo "Waiting for LFM server..."
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "Server exited unexpectedly. Check lfm_server.log" >&2
      exit 1
    fi
  done

  echo "LFM server ready. Starting webapp..."
fi

ENGINE_TYPE="$ENGINE_TYPE" uvicorn webapp.app:app --host 0.0.0.0 --port 8000
