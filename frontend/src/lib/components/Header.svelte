<script lang="ts">
  import { status, sttBackends, selectedStt, ttsEnabled } from '../stores/chat';
  import { clearMessages } from '../services/api';
</script>

<header class="top-bar">
  <div class="brand">
    <span class="logo">◆</span>
    <span class="name">JARVIS</span>
    <span class="tag">CONV-PROXY</span>
  </div>

  <div class="controls">
    <div class="control">
      <label for="stt">STT</label>
      <select id="stt" bind:value={$selectedStt}>
        {#each $sttBackends as b}
          <option value={b}>{b}</option>
        {/each}
      </select>
    </div>

    <label class="toggle">
      <input type="checkbox" bind:checked={$ttsEnabled} />
      <span class="toggle-label">TTS</span>
    </label>

    <button class="clear-btn" on:click={clearMessages} title="Clear chat">✕</button>

    <div class="status-pill" class:online={$status.connected}>
      <span class="dot"></span>
      {$status.connected ? 'online' : 'offline'}
    </div>
  </div>
</header>

<style>
  .top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: #0d1117;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    flex-shrink: 0;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .logo {
    color: #7dd3fc;
    font-size: 1.1rem;
  }
  .name {
    font-weight: 700;
    letter-spacing: 0.1em;
    font-size: 0.85rem;
    color: #e2e8f0;
  }
  .tag {
    font-size: 0.65rem;
    color: #475569;
    letter-spacing: 0.08em;
    border: 1px solid rgba(255,255,255,0.06);
    padding: 1px 6px;
    border-radius: 4px;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .control {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.72rem;
    color: #94a3b8;
  }
  .control select {
    background: #0a0e14;
    color: #e2e8f0;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 0.72rem;
    outline: none;
  }
  .toggle {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
  }
  .toggle input { width: 14px; height: 14px; accent-color: #7dd3fc; }
  .toggle-label { font-size: 0.72rem; color: #94a3b8; }
  .clear-btn {
    background: none;
    border: 1px solid rgba(255,255,255,0.06);
    color: #475569;
    width: 28px; height: 28px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.75rem;
    display: grid; place-items: center;
    transition: all 0.15s;
  }
  .clear-btn:hover { color: #ef4444; border-color: rgba(239,68,68,0.3); }
  .status-pill {
    font-size: 0.72rem;
    padding: 3px 10px;
    border-radius: 999px;
    background: rgba(239,68,68,0.1);
    color: #ef4444;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .status-pill.online {
    background: rgba(34,197,94,0.1);
    color: #22c55e;
  }
  .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
  }
</style>
