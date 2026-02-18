<script lang="ts">
  import { connection } from '../stores/connection';
  import { audio } from '../stores/audio';
  import { settings } from '../stores/settings';

  $: statusColor = 
    $connection.status === 'connected' ? '#10b981' :
    $connection.status === 'connecting' ? '#eab308' :
    $connection.status === 'error' ? '#ef4444' :
    '#64748b';

  $: statusText = 
    $connection.status === 'connected' ? 'Connected' :
    $connection.status === 'connecting' ? 'Connecting...' :
    $connection.status === 'error' ? 'Connection Error' :
    'Disconnected';

  $: activityText = 
    $audio.speakerState === 'speaking' ? 'Speaking' :
    $audio.micState === 'listening' ? 'Listening' :
    $audio.micState === 'processing' ? 'Processing' :
    $connection.agentStatus || 'Idle';

  function toggleSettings() {
    settings.update(s => ({ ...s, showSettings: !s.showSettings }));
  }

  async function startMockFlow() {
    await fetch('/api/mock-agent/start', { method: 'POST' });
  }

  async function stopMockFlow() {
    await fetch('/api/mock-agent/stop', { method: 'POST' });
  }
</script>

<div class="status-bar">
  <div class="status-group">
    <div class="status-indicator" style="background-color: {statusColor}"></div>
    <span class="status-text">{statusText}</span>
  </div>

  <div class="info-group">
    {#if $connection.model}
      <span class="model-badge">{$connection.model}</span>
    {/if}
    <span class="activity">{activityText}</span>
  </div>

  <div class="actions">
    <button class="mock-btn" on:click={startMockFlow}>Mock Start</button>
    <button class="mock-btn stop" on:click={stopMockFlow}>Mock Stop</button>
    <button class="settings-button" on:click={toggleSettings} aria-label="Settings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 1v6m0 6v6M3.5 3.5l4.2 4.2m8.6 8.6l4.2 4.2M1 12h6m6 0h6M3.5 20.5l4.2-4.2m8.6-8.6l4.2-4.2"/>
      </svg>
    </button>
  </div>
</div>

<style>
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    background: rgba(15, 23, 42, 0.8);
    border-bottom: 1px solid rgba(59, 130, 246, 0.2);
    backdrop-filter: blur(10px);
    gap: 16px;
  }

  .status-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .status-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    box-shadow: 0 0 8px currentColor;
  }

  .status-text {
    font-size: 0.875rem;
    color: #cbd5e1;
    font-weight: 500;
  }

  .info-group {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    justify-content: center;
  }

  .model-badge {
    padding: 4px 12px;
    background: rgba(59, 130, 246, 0.2);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 12px;
    font-size: 0.75rem;
    color: #93c5fd;
    font-weight: 500;
  }

  .activity {
    font-size: 0.875rem;
    color: #94a3b8;
    font-style: italic;
  }

  .actions { display:flex; align-items:center; gap:8px; }

  .mock-btn {
    border: 1px solid rgba(59,130,246,.35);
    background: rgba(30,41,59,.6);
    color: #cbd5e1;
    font-size: .72rem;
    padding: 6px 10px;
    border-radius: 8px;
    cursor: pointer;
  }
  .mock-btn.stop { border-color: rgba(239,68,68,.35); color:#fecaca; }

  .settings-button {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    padding: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    border-radius: 8px;
  }

  .settings-button:hover {
    background: rgba(59, 130, 246, 0.1);
    color: #60a5fa;
  }

  .settings-button svg {
    width: 20px;
    height: 20px;
    stroke-width: 2;
  }

  @media (max-width: 768px) {
    .status-bar {
      padding: 12px 16px;
      flex-wrap: wrap;
    }

    .info-group {
      order: 3;
      width: 100%;
      justify-content: flex-start;
      margin-top: 8px;
    }
  }
</style>
