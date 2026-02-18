# Browser VAD research for real‑time conversational AI (Svelte)

> Goal: low‑latency (<100ms ideal), configurable thresholds, barge‑in while TTS plays.

## 1) **@ricky0123/vad-web** (Silero VAD via ONNX Runtime Web)
**What it is:** Browser VAD running Silero VAD through ONNX Runtime Web. Provides a high‑level `MicVAD` API for real‑time mic input and a `NonRealTimeVAD` for buffers.

**How it works (from docs):**
- Resamples input to **16 kHz**.
- Batches samples into frames of **`frameSamples` (default 1536)**.
  - 1536 @ 16kHz ≈ **96 ms per frame** → *baseline inference latency*.
- Runs Silero model per frame, returns a probability 0..1.
- State machine with `positiveSpeechThreshold`, `negativeSpeechThreshold`, `redemptionFrames`, `minSpeechFrames`, `preSpeechPadFrames` to control speech start/end.

**Integration (Svelte/TS):**
- Install: `npm i @ricky0123/vad onnxruntime-web`
- For Vite/SvelteKit, you must **serve** the VAD assets:
  - `*.worklet.js`, `*.onnx`, and `onnxruntime-web` wasm files. Typical approach:
    - Copy to `static/` (SvelteKit) using a build step or `vite-plugin-static-copy`.
    - Ensure URLs resolve at runtime (e.g., `/vad-worklet.js`, `/silero_vad.onnx`, `/ort-wasm.wasm`).
- Example usage:
  ```ts
  import * as vad from "@ricky0123/vad";

  const myvad = await vad.MicVAD.new({
    onSpeechStart: () => {},
    onSpeechEnd: (audio) => { /* Float32Array @ 16kHz */ },
    onVADMisfire: () => {},
    onFrameProcessed: (probs) => {},
    // thresholds:
    positiveSpeechThreshold: 0.8,
    negativeSpeechThreshold: 0.5,
    redemptionFrames: 8,
    preSpeechPadFrames: 2,
    minSpeechFrames: 4,
  });
  myvad.start();
  ```

**Latency:**
- At least **one frame (~96ms)**, plus model inference (~few ms to tens of ms depending on device). Good but close to 100ms. Increase responsiveness by lowering `frameSamples` only if supported (docs imply default should not change).

**CPU usage:**
- Moderate: ONNX Runtime + model inference each frame. On mobile, might be significant; on desktop, fine.

**Configuration:**
- `positiveSpeechThreshold`, `negativeSpeechThreshold`, `redemptionFrames`, `minSpeechFrames`, `preSpeechPadFrames`, `frameSamples`.

**Pros:**
- Accurate ML VAD, simple API, configurable.
- Works fully in browser, good for noisy environments.

**Cons:**
- Heavier bundle (onnx + wasm + model assets). Higher CPU than energy‑based.
- Asset hosting/config overhead in bundlers.

**Sources:**
- README via jsDelivr: https://cdn.jsdelivr.net/npm/@ricky0123/vad/README.md
- Quick start: https://cdn.jsdelivr.net/npm/@ricky0123/vad-web/README.md

---

## 2) **Simple energy‑based VAD** (RMS threshold + silence duration)
**What it is:** Compute RMS/energy of audio frames and compare to threshold; detect speech start when energy > threshold for N frames; detect end when energy < threshold for M frames.

**Integration (Svelte/TS):**
- Use `AudioContext`, `MediaStreamAudioSourceNode`, `AudioWorklet` (preferred) or `AnalyserNode`.
- For lowest latency, use `AudioWorkletProcessor` to compute RMS per small frame (e.g., 10–20ms):
  ```ts
  // In AudioWorkletProcessor: compute rms for frame, postMessage({ rms })
  ```
- Maintain state machine in main thread or worker.

**Latency:**
- **Very low**, typically frame size (10–20ms) + decision smoothing (e.g., 50–100ms silence).

**CPU usage:**
- Very low; minimal math.

**Configuration:**
- `rmsThreshold` (or dB threshold), `minSpeechMs`, `minSilenceMs`, `hangoverMs`, `preRollMs`.
- Optional adaptive noise floor: measure ambient noise in first 500–1000ms.

**Pros:**
- Fast, tiny, no model assets, easy to customize for barge‑in.

**Cons:**
- Less accurate in noisy environments; may false trigger on background or TTS leakage.

**Notes:**
- You can improve robustness by band‑pass filtering (e.g., 80–300Hz or 85–255Hz) and tracking spectral energy.

---

## 3) **WebRTC VAD** (native library, *not* exposed in browsers)
**What it is:** Google’s WebRTC VAD (C) used widely in telephony. Aggressiveness levels 0–3, frame sizes 10/20/30ms. Requires 16‑bit PCM @ 8/16/32/48kHz.

**Browser availability:**
- **Not available as a native Web API**. Libraries like `webrtcvad` are **Node native addons**, not browser‑ready.
- To use in browser you’d need a **WASM build** of WebRTC VAD or a JS port (some community projects exist but are less maintained).

**Integration (Svelte/TS):**
- If using a WASM port, wrap as worker or AudioWorklet (feed 10–30ms PCM frames).
- Expect additional build complexity; verify license and performance.

**Latency:**
- Excellent (10–30ms frames + small smoothing).

**CPU usage:**
- Low to moderate (C/WASM is efficient).

**Configuration:**
- Aggressiveness (0–3). Frame length must be 10/20/30ms.

**Pros:**
- High quality classical VAD, low latency.

**Cons:**
- No first‑class browser API; requires WASM build or third‑party port.

**Sources:**
- Node addon docs (not browser): https://cdn.jsdelivr.net/npm/webrtcvad/README.md
- WebRTC VAD reference (py wrapper): https://raw.githubusercontent.com/wiseman/py-webrtcvad/master/README.md

---

## 4) **Other lightweight browser VAD libraries**
### **voice-activity-detection** (Jam3)
- Uses WebAudio FFT + noise floor calibration and frequency band thresholds.
- Configurable: `fftSize`, `bufferLen`, `minCaptureFreq`, `maxCaptureFreq`, `noiseCaptureDuration`, `avgNoiseMultiplier`, callbacks `onVoiceStart/onVoiceStop`.
- Lightweight and easy to integrate, but less robust than ML.

**Integration:**
```ts
import vad from "voice-activity-detection";

const ac = new AudioContext();
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
vad(ac, stream, { onVoiceStart, onVoiceStop, avgNoiseMultiplier: 1.2 });
```

**Source:** https://cdn.jsdelivr.net/npm/voice-activity-detection/README.md

---

# Echo cancellation & barge‑in
**Browser‑level AEC:**
- Use `getUserMedia` with `echoCancellation: true` (and optionally `noiseSuppression`, `autoGainControl`).
- You can request specific modes (`"all"`, `"remote-only"`) where supported.

Example:
```ts
navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  }
});
```

**Barge‑in strategy:**
1. **Keep VAD running while TTS plays**; on speech start, immediately stop/duck TTS playback.
2. **AEC helps** but won’t fully remove speaker leakage. Combine with:
   - A **higher speech threshold** while TTS is playing (dynamic threshold).
   - **Spectral gating**: compare mic energy in voice band vs full-band energy.
   - Optional **echo reference subtraction**: feed known TTS output into a custom echo canceller (complex; browser doesn’t expose system AEC tuning).

**Key constraint:** Browsers do not provide direct access to system AEC internals; you only get constraints.

**Source:**
- MDN echoCancellation: https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation

---

# Streaming audio to server via WebSocket (best practices)
**Capture pipeline:**
- Use **AudioWorklet** (preferred) instead of deprecated ScriptProcessor for low‑latency capture.
- Resample to 16 kHz (if needed) in the worklet to reduce bandwidth and align with ASR/VAD models.
- Chunk audio in **10–20ms frames** (e.g., 160–320 samples @16k) and send as binary frames.

**Transport:**
- WebSocket binary frames (ArrayBuffer) with a minimal header (sequence number + timestamp).
- Avoid huge frames (100ms+) to reduce latency jitter.
- Backpressure: use a ring buffer and drop oldest if network stalls.

**Server compatibility:**
- If server expects PCM16, convert `Float32` → `Int16` in the worklet/worker.
- Include **stream start/stop** markers and **VAD events** to help the server align.

---

# Audio format considerations (PCM16 vs Opus)
**PCM16 (raw linear PCM)**
- ✅ Lowest latency, simple to generate in browser.
- ✅ Easy for server to consume and for real‑time ASR.
- ❌ High bandwidth (16kHz mono 16‑bit ≈ 256 kbps).

**Opus (compressed)**
- ✅ Low bandwidth, great quality.
- ❌ Browser encoding options typically via MediaRecorder (larger chunk sizes ~100ms+). Adds latency.
- ❌ WebCodecs AudioEncoder (Opus) is improving but still not universally supported.

**Recommendation:**
- For ultra‑low latency conversational AI, **PCM16** over WebSocket is simplest and fastest.
- Consider Opus only if bandwidth is a limiting factor and you can tolerate additional latency (or use WebRTC).

---

# Practical recommendations for this Svelte app
1. **Default VAD:** use **@ricky0123/vad** (Silero) for accuracy + configurable thresholds. Expect ~100ms baseline latency.
2. **Fallback/fast path:** add **energy‑based VAD** for ultra‑fast barge‑in (trigger on RMS spike, then confirm with Silero).
3. **AEC:** enable `echoCancellation: true` + `noiseSuppression`, and dynamically adjust thresholds during TTS playback.
4. **Streaming:** AudioWorklet → PCM16 → WebSocket in 10–20ms frames.

---

## Sources (retrieved)
- https://cdn.jsdelivr.net/npm/@ricky0123/vad/README.md
- https://cdn.jsdelivr.net/npm/@ricky0123/vad-web/README.md
- https://cdn.jsdelivr.net/npm/webrtcvad/README.md
- https://cdn.jsdelivr.net/npm/voice-activity-detection/README.md
- https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation
