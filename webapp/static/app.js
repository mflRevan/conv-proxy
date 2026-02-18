const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');
const ttsToggle = document.getElementById('ttsToggle');
const micBtn = document.getElementById('mic');
const recordingIndicator = document.getElementById('recordingIndicator');
const sttSelect = document.getElementById('sttSelect');

let ws;
let wsReady = false;
let currentAssistant = null;
let currentThinking = null;
let currentTiming = null;
let audioQueue = [];
let audioCtx;
let mediaRecorder;
let mediaStream;
let recognition;
let recording = false;

function setStatus(online) {
  statusEl.textContent = online ? 'online' : 'offline';
  statusEl.classList.toggle('online', online);
}

function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const textEl = document.createElement('span');
  textEl.className = 'msg-text';
  textEl.textContent = text;
  div.appendChild(textEl);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function addThinkingDropdown(messageEl, thinkingText) {
  if (!thinkingText) return;
  let details = messageEl.querySelector('details.thinking');
  if (!details) {
    details = document.createElement('details');
    details.className = 'thinking';
    const summary = document.createElement('summary');
    summary.textContent = '💭 Thinking…';
    details.appendChild(summary);
    const content = document.createElement('pre');
    content.className = 'thinking-content';
    details.appendChild(content);
    messageEl.appendChild(details);
  }
  details.querySelector('.thinking-content').textContent = thinkingText;
}

function addLatencyLabel(messageEl, ttft, total) {
  let span = messageEl.querySelector('.latency');
  if (!span) {
    span = document.createElement('span');
    span.className = 'latency';
    messageEl.appendChild(span);
  }
  const ttftStr = ttft ? `${ttft.toFixed(0)}ms` : 'n/a';
  span.textContent = `TTFT ${ttftStr} • total ${total.toFixed(0)}ms`;
}

/* ---------- WebSocket ---------- */
function connect() {
  try {
    ws = new WebSocket(`ws://${window.location.host}/ws/chat`);
  } catch (e) {
    setStatus(false);
    return;
  }

  ws.onopen = () => {
    wsReady = true;
    setStatus(true);
  };
  ws.onclose = () => {
    wsReady = false;
    setStatus(false);
    // Reconnect after 3s
    setTimeout(connect, 3000);
  };
  ws.onerror = () => {
    wsReady = false;
    setStatus(false);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'text') {
      if (!currentAssistant) {
        currentAssistant = addMessage('', 'assistant');
        currentTiming = { start: performance.now(), ttft: null };
      }
      if (currentTiming && currentTiming.ttft === null) {
        currentTiming.ttft = performance.now() - currentTiming.start;
      }
      currentAssistant.querySelector('.msg-text').textContent += data.content;
      chat.scrollTop = chat.scrollHeight;

    } else if (data.type === 'thinking') {
      if (!currentAssistant) {
        currentAssistant = addMessage('', 'assistant');
        currentTiming = { start: performance.now(), ttft: null };
      }
      addThinkingDropdown(currentAssistant, data.content);

    } else if (data.type === 'audio') {
      enqueueAudio(data.content, data.sample_rate);

    } else if (data.type === 'done') {
      if (currentAssistant && currentTiming) {
        const total = performance.now() - currentTiming.start;
        addLatencyLabel(currentAssistant, currentTiming.ttft, total);
      }
      currentAssistant = null;
      currentTiming = null;

    } else if (data.type === 'stt') {
      if (data.text) {
        input.value = data.text;
        sendMessage();
      }
    }
  };
}

/* ---------- Audio ---------- */
function enqueueAudio(b64, sampleRate) {
  if (!b64) return;
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  audioQueue.push({ bytes, sampleRate });
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioQueue.length === 1) playNext();
}

function playNext() {
  if (!audioQueue.length) return;
  const { bytes, sampleRate } = audioQueue[0];
  const buffer = audioCtx.createBuffer(1, bytes.length / 2, sampleRate);
  const ch = buffer.getChannelData(0);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < ch.length; i++) ch[i] = view.getInt16(i * 2, true) / 32768;
  const src = audioCtx.createBufferSource();
  src.buffer = buffer;
  src.connect(audioCtx.destination);
  src.onended = () => { audioQueue.shift(); playNext(); };
  src.start(0);
}

/* ---------- HTTP fallback ---------- */
async function sendHttpChat(text) {
  const t0 = performance.now();
  const el = addMessage('⏳', 'assistant');
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, tts: ttsToggle.checked })
    });
    const data = await res.json();
    const total = performance.now() - t0;
    el.querySelector('.msg-text').textContent = data.text || data.error || '';
    if (data.thinking) addThinkingDropdown(el, data.thinking);
    addLatencyLabel(el, null, total);
    if (data.audio) data.audio.forEach(c => enqueueAudio(c, data.sample_rate));
  } catch (e) {
    el.querySelector('.msg-text').textContent = `Error: ${e.message}`;
  }
}

/* ---------- Send ---------- */
function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, 'user');
  input.value = '';
  if (wsReady) {
    ws.send(JSON.stringify({ message: text, tts: ttsToggle.checked }));
  } else {
    sendHttpChat(text);
  }
}

/* ---------- STT ---------- */
async function loadSttBackends() {
  try {
    const res = await fetch('/api/stt/backends');
    const p = await res.json();
    sttSelect.innerHTML = '';
    (p.backends || []).forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sttSelect.appendChild(opt);
    });
    if (p.default) sttSelect.value = p.default;
  } catch (e) {
    console.warn('STT backends load failed', e);
  }
}

function setRecording(active) {
  recording = active;
  micBtn.classList.toggle('active', active);
  recordingIndicator.classList.toggle('active', active);
}

async function toggleRecording() {
  if (recording) { stopRecording(); return; }
  const backend = sttSelect.value;
  if (backend === 'browser') {
    startBrowserRecognition();
  } else {
    await startMediaRecorder();
  }
}

function startBrowserRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert('Browser SpeechRecognition not available. Try Chrome or use a server-side backend.'); return; }
  recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.onstart = () => setRecording(true);
  recognition.onend = () => setRecording(false);
  recognition.onerror = () => setRecording(false);
  recognition.onresult = (e) => { input.value = e.results[0][0].transcript; sendMessage(); };
  recognition.start();
}

async function startMediaRecorder() {
  // navigator.mediaDevices requires secure context (HTTPS or localhost)
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Microphone not available.\n\nOn LAN, use "browser" STT backend (works in Chrome),\nor access via localhost, or use HTTPS.');
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(mediaStream);
    const chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      const wavBuf = await convertToWav(blob);
      // Send via HTTP (more reliable than WS for binary)
      await sendSttHttp(wavBuf);
      cleanupMedia();
      setRecording(false);
    };
    mediaRecorder.start();
    setRecording(true);
  } catch (err) {
    alert(`Mic error: ${err.message}\n\nTry "browser" STT backend instead.`);
    setRecording(false);
  }
}

async function sendSttHttp(wavBuffer) {
  const blob = new Blob([wavBuffer], { type: 'audio/wav' });
  const form = new FormData();
  form.append('file', blob, 'audio.wav');
  try {
    const res = await fetch(`/api/stt/transcribe?stt_backend=${encodeURIComponent(sttSelect.value)}`, {
      method: 'POST', body: form
    });
    const data = await res.json();
    if (data.text) { input.value = data.text; sendMessage(); }
  } catch (e) {
    console.error('STT error', e);
  }
}

function stopRecording() {
  if (recognition) { recognition.stop(); recognition = null; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
}

function cleanupMedia() {
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  mediaRecorder = null;
}

async function convertToWav(blob) {
  const ab = await blob.arrayBuffer();
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await audioCtx.decodeAudioData(ab);
  const offline = new OfflineAudioContext(1, decoded.duration * 16000, 16000);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start(0);
  const rendered = await offline.startRendering();
  return encodeWav(rendered.getChannelData(0), 16000);
}

function encodeWav(samples, sr) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const ws = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  ws(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); ws(8, 'WAVE');
  ws(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  ws(36, 'data'); v.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); o += 2;
  }
  return buf;
}

/* ---------- Init ---------- */
sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });
micBtn.addEventListener('click', toggleRecording);
loadSttBackends();
connect();
