<script lang="ts">
  import { connection } from '../stores/connection';
  import { settings } from '../stores/settings';
  import { conversation } from '../stores/conversation';

  $: statusColor =
    $connection.gatewayState === 'connected' ? '#14b8a6' :
    $connection.gatewayState === 'connecting' ? '#eab308' :
    $connection.gatewayState === 'error' ? '#ef4444' :
    '#64748b';

  $: statusText =
    $connection.gatewayState === 'connected' ? 'Gateway Connected' :
    $connection.gatewayState === 'connecting' ? 'Gateway Connecting…' :
    $connection.gatewayState === 'error' ? 'Gateway Error' :
    'Gateway Disconnected';

  function toggleSettings() {
    settings.update(s => ({ ...s, showSettings: !s.showSettings }));
  }
</script>

<div class="status-bar">
  <div class="status-group">
    <div class="status-indicator" style="background-color: {statusColor}"></div>
    <span class="status-text">{statusText}</span>
  </div>

  <div class="info-group">
    {#if $connection.proxyModel}
      <span class="model-badge">{$connection.proxyModel}</span>
    {/if}
    {#if $conversation.contextChars}
      <span class="model-badge">CTX {Math.round($conversation.contextChars / 1000)}k</span>
    {/if}
  </div>

  <div class="actions">
    <button class="settings-button" on:click={toggleSettings} aria-label="Settings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <line x1="4" y1="6" x2="20" y2="6"/>
        <line x1="4" y1="12" x2="20" y2="12"/>
        <line x1="4" y1="18" x2="20" y2="18"/>
        <circle cx="9" cy="6" r="2" fill="currentColor" stroke="none"/>
        <circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"/>
        <circle cx="11" cy="18" r="2" fill="currentColor" stroke="none"/>
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

  .actions { display:flex; align-items:center; gap:8px; }

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
    .status-bar { padding: 12px 16px; flex-wrap: wrap; }
    .info-group { order: 3; width: 100%; justify-content: flex-start; margin-top: 8px; }
  }
</style>
