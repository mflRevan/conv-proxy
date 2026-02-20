<script lang="ts">
  import { settings } from '../stores/settings';
  import { conversation } from '../stores/conversation';

  const sttBackends = [
    'whisper-tiny',
    'whisper-small',
    'whisper-medium',
    'moonshine-tiny',
    'moonshine-base',
    'browser',
  ];

  function close() {
    settings.update(s => ({ ...s, showSettings: false }));
  }

  function handleBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) {
      close();
    }
  }

  $: ctx = $conversation;
  $: promptOther = Math.max(0, (ctx.promptChars || 0)
    - (ctx.proxyMdChars || 0)
    - (ctx.compressedChars || 0)
    - (ctx.historyTextChars || 0)
    - (ctx.historyFullChars || 0)
    - (ctx.liveTurnChars || 0)
    - (ctx.scratchpadChars || 0)
    - (ctx.queuedChars || 0));

  $: segments = [
    { label: 'Proxy MD', value: ctx.proxyMdChars, color: '#38bdf8' },
    { label: 'Compressed', value: ctx.compressedChars, color: '#a78bfa' },
    { label: 'Main history', value: ctx.historyTextChars, color: '#60a5fa' },
    { label: 'Full-res', value: ctx.historyFullChars, color: '#fbbf24' },
    { label: 'Live turn', value: ctx.liveTurnChars, color: '#34d399' },
    { label: 'Scratchpad', value: ctx.scratchpadChars, color: '#f472b6' },
    { label: 'Queued', value: ctx.queuedChars, color: '#fb7185' },
    { label: 'Proxy chat', value: ctx.conversationChars, color: '#94a3b8' },
    { label: 'Other prompt', value: promptOther, color: '#64748b' },
  ].filter(s => (s.value || 0) > 0);

  $: total = segments.reduce((sum, s) => sum + (s.value || 0), 0) || 1;
  $: pieStyle = `background: conic-gradient(${segments.map((s, i) => {
    const start = segments.slice(0, i).reduce((sum, v) => sum + v.value, 0) / total * 360;
    const end = (segments.slice(0, i + 1).reduce((sum, v) => sum + v.value, 0) / total * 360);
    return `${s.color} ${start}deg ${end}deg`;
  }).join(',')});`;

  $: legendItems = segments.map(s => ({
    ...s,
    k: Math.max(0.1, Math.round((s.value || 0) / 100) / 10),
  }));

  async function applySettings() {
    const s = $settings;
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proxyModel: s.proxyModel,
        proxyTemperature: s.proxyTemperature,
        proxyMaxTokens: s.proxyMaxTokens,
        historyLength: s.historyLength,
        compressedContext: s.compressedContextEnabled ? s.compressedContext : '',
        mainHistoryLength: s.mainHistoryLength,
        mainHistoryFullCount: s.mainHistoryFullCount,
        sttBackend: s.sttBackend,
        ttsEnabled: s.ttsEnabled,
        vadThreshold: s.vadThreshold,
        silenceDurationMs: s.silenceDurationMs,
        wakewordEnabled: s.wakewordEnabled,
        wakewordThreshold: s.wakewordThreshold,
        wakewordActiveWindowMs: s.wakewordActiveWindowMs,
        gatewayUrl: s.gatewayUrl,
        gatewayToken: s.gatewayToken,
      }),
    });
  }
</script>

{#if $settings.showSettings}
  <div class="settings-overlay" on:click={handleBackdropClick}>
    <div class="settings-panel">
      <div class="panel-header">
        <h2>Settings</h2>
        <button class="close-button" on:click={close} aria-label="Close settings">
          ✕
        </button>
      </div>

      <div class="panel-content">
        <section>
          <h3>Proxy Agent</h3>
          <label>
            Model (OpenRouter ID)
            <input type="text" bind:value={$settings.proxyModel} />
          </label>
          <label>
            Temperature
            <input type="number" step="0.1" min="0" max="1" bind:value={$settings.proxyTemperature} />
          </label>
          <label>
            Max Tokens
            <input type="number" min="64" max="4096" bind:value={$settings.proxyMaxTokens} />
          </label>
        </section>

        <section>
          <h3>Context</h3>
          <div class="context-row">
            <div class="context-controls">
              <label>
                Proxy history length (pairs)
                <input type="number" min="4" max="40" bind:value={$settings.historyLength} />
              </label>
              <label>
                Main agent history length (messages)
                <input type="number" min="5" max="80" bind:value={$settings.mainHistoryLength} />
              </label>
              <label>
                Main agent full-resolution window (messages)
                <input type="number" min="1" max="20" bind:value={$settings.mainHistoryFullCount} />
              </label>
              <label class="toggle">
                <input type="checkbox" bind:checked={$settings.compressedContextEnabled} />
                <span>Use compressed context</span>
              </label>
              <textarea
                rows="3"
                placeholder="Compressed context summary"
                bind:value={$settings.compressedContext}
              ></textarea>
            </div>

            <div class="context-preview">
              <div class="chart" style={pieStyle}></div>
              <div class="legend">
                {#each legendItems as item}
                  <div class="legend-row">
                    <span class="swatch" style={`background:${item.color}`}></span>
                    <span class="label">{item.label}</span>
                    <span class="value">{item.k}k</span>
                  </div>
                {/each}
              </div>
              <div class="context-total">Total: {Math.round($conversation.contextChars / 1000)}k chars</div>
            </div>
          </div>
        </section>

        <section>
          <h3>Voice</h3>
          <label>
            STT Backend
            <select bind:value={$settings.sttBackend}>
              {#each sttBackends as backend}
                <option value={backend}>{backend}</option>
              {/each}
            </select>
          </label>
          <label>
            VAD Threshold
            <input type="range" min="0.1" max="1" step="0.05" bind:value={$settings.vadThreshold} />
          </label>
          <label>
            Silence Duration (ms)
            <input type="number" min="300" max="2000" bind:value={$settings.silenceDurationMs} />
          </label>
          <label class="toggle">
            <input type="checkbox" bind:checked={$settings.autoSend} />
            <span>Auto-send on silence</span>
          </label>
          <label class="toggle">
            <input type="checkbox" bind:checked={$settings.wakewordEnabled} />
            <span>Wakeword enabled</span>
          </label>
          <label>
            Wakeword Threshold
            <input type="range" min="0.2" max="0.9" step="0.05" bind:value={$settings.wakewordThreshold} />
          </label>
          <label>
            Wakeword Timeout (ms)
            <input type="number" min="2000" max="20000" bind:value={$settings.wakewordActiveWindowMs} />
          </label>
        </section>

        <section>
          <h3>TTS</h3>
          <label class="toggle">
            <input type="checkbox" bind:checked={$settings.ttsEnabled} />
            <span>Enable text-to-speech</span>
          </label>
        </section>

        <section>
          <h3>Connection</h3>
          <label>
            Gateway URL
            <input type="text" bind:value={$settings.gatewayUrl} placeholder="ws://127.0.0.1:18789" />
          </label>
          <label>
            Gateway Token
            <input type="password" bind:value={$settings.gatewayToken} />
          </label>
          <button class="secondary" on:click={applySettings}>Reconnect</button>
        </section>
      </div>

      <div class="panel-footer">
        <button class="secondary" on:click={close}>Close</button>
        <button on:click={applySettings}>Apply</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .settings-overlay {
    position: fixed;
    inset: 0;
    background: rgba(2, 6, 23, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
  }
  .settings-panel {
    width: min(900px, 92vw);
    max-height: 90vh;
    overflow: auto;
    background: #0f172a;
    border: 1px solid rgba(59,130,246,.25);
    border-radius: 18px;
    padding: 20px 24px 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .panel-header {
    display:flex;
    align-items:center;
    justify-content:space-between;
  }
  .panel-content {
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 18px;
  }
  .context-row { display:grid; grid-template-columns: 1.3fr 1fr; gap:14px; }
  .context-controls { display:flex; flex-direction:column; gap:10px; }
  .context-preview { display:flex; flex-direction:column; gap:12px; align-items:center; justify-content:center; }
  .chart { width:140px; height:140px; border-radius:50%; border:1px solid rgba(148,163,184,.3); box-shadow: inset 0 0 18px rgba(15,23,42,.6); }
  .legend { width:100%; display:flex; flex-direction:column; gap:6px; }
  .legend-row { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:.72rem; color:#cbd5e1; }
  .swatch { width:10px; height:10px; border-radius:2px; display:inline-block; }
  .label { flex:1; }
  .value { color:#93c5fd; }
  .context-total { font-size:.75rem; color:#94a3b8; }
  @media (max-width: 860px) { .context-row { grid-template-columns: 1fr; } }
  section {
    display:flex;
    flex-direction:column;
    gap: 10px;
    padding: 12px;
    border-radius: 12px;
    border: 1px solid rgba(148,163,184,.18);
    background: rgba(15,23,42,.5);
  }
  h3 { margin:0 0 4px; font-size:0.95rem; color:#e2e8f0; }
  label { display:flex; flex-direction:column; gap:6px; font-size:0.8rem; color:#cbd5e1; }
  input, select, textarea {
    background: rgba(2,6,23,.8);
    border: 1px solid rgba(59,130,246,.3);
    border-radius: 8px;
    padding: 8px 10px;
    color: #e2e8f0;
  }
  .toggle { flex-direction: row; align-items:center; gap:8px; }
  .panel-footer {
    display:flex;
    justify-content:flex-end;
    gap:10px;
  }
  button {
    background:#2563eb;
    color:white;
    border:none;
    border-radius:10px;
    padding:8px 16px;
    cursor:pointer;
  }
  button.secondary {
    background: transparent;
    border: 1px solid rgba(148,163,184,.4);
    color:#cbd5e1;
  }
  .close-button {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 1.1rem;
    cursor: pointer;
  }
</style>
