const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');
const ttsToggle = document.getElementById('ttsToggle');

let ws;
let currentAssistant;
let audioQueue = [];
let audioCtx;

function setStatus(online) {
  statusEl.textContent = online ? 'online' : 'offline';
  statusEl.classList.toggle('online', online);
}

function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function connect() {
  ws = new WebSocket(`ws://${window.location.host}/ws/chat`);

  ws.onopen = () => setStatus(true);
  ws.onclose = () => setStatus(false);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'text') {
      if (!currentAssistant) {
        currentAssistant = addMessage('', 'assistant');
      }
      currentAssistant.textContent += data.content;
      chat.scrollTop = chat.scrollHeight;
    } else if (data.type === 'audio') {
      enqueueAudio(data.content, data.sample_rate);
    } else if (data.type === 'done') {
      currentAssistant = null;
    }
  };
}

function enqueueAudio(b64, sampleRate) {
  if (!b64) return;
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  audioQueue.push({ bytes, sampleRate });
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioQueue.length === 1) {
    playNext();
  }
}

function playNext() {
  if (audioQueue.length === 0) return;
  const { bytes, sampleRate } = audioQueue[0];
  const buffer = audioCtx.createBuffer(1, bytes.length / 2, sampleRate);
  const channel = buffer.getChannelData(0);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < channel.length; i++) {
    channel[i] = view.getInt16(i * 2, true) / 32768;
  }
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  source.onended = () => {
    audioQueue.shift();
    playNext();
  };
  source.start(0);
}

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, 'user');
  ws.send(JSON.stringify({ message: text, tts: ttsToggle.checked }));
  input.value = '';
}

sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});

connect();
