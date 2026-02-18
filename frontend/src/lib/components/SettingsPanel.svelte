<script lang="ts">
  import { settings } from '../stores/settings';

  const sttBackends = [
    'moonshine-tiny',
    'whisper-tiny',
    'whisper-base',
    'whisper-small',
    'whisper-medium',
  ];

  function close() {
    settings.update(s => ({ ...s, showSettings: false }));
  }

  function handleBackdropClick(e: MouseEvent) {
    if (e.target === e.currentTarget) {
      close();
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      close();
    }
  }
</script>

{#if $settings.showSettings}
  <div 
    class="settings-overlay" 
    on:click={handleBackdropClick}
    on:keydown={handleKeydown}
    role="dialog"
    aria-modal="true"
    aria-labelledby="settings-title"
    tabindex="-1"
  >
    <div class="settings-panel">
      <div class="panel-header">
        <h2 id="settings-title">Settings</h2>
        <button class="close-button" on:click={close} aria-label="Close settings">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="panel-content">
        <div class="setting-group">
          <label for="stt-backend">Speech Recognition Backend</label>
          <select 
            id="stt-backend" 
            bind:value={$settings.sttBackend}
          >
            {#each sttBackends as backend}
              <option value={backend}>{backend}</option>
            {/each}
          </select>
          <p class="hint">Choose the speech-to-text model. Smaller models are faster but less accurate.</p>
        </div>

        <div class="setting-group">
          <label class="toggle-label">
            <input 
              type="checkbox" 
              bind:checked={$settings.ttsEnabled}
            />
            <span>Enable Text-to-Speech</span>
          </label>
          <p class="hint">Play audio responses from the assistant.</p>
        </div>

        <div class="setting-group">
          <label for="vad-threshold">Voice Activity Detection Threshold</label>
          <div class="slider-group">
            <input 
              id="vad-threshold"
              type="range" 
              min="0" 
              max="1" 
              step="0.05"
              bind:value={$settings.vadThreshold}
            />
            <span class="slider-value">{Math.round($settings.vadThreshold * 100)}%</span>
          </div>
          <p class="hint">Adjust sensitivity for detecting speech. Lower values are more sensitive.</p>
        </div>

        <div class="setting-group">
          <label for="silence-duration">Silence End Duration (ms)</label>
          <div class="slider-group">
            <input
              id="silence-duration"
              type="range"
              min="400"
              max="2000"
              step="50"
              bind:value={$settings.silenceDurationMs}
            />
            <span class="slider-value">{$settings.silenceDurationMs}</span>
          </div>
          <p class="hint">How long silence must last before a turn ends (server VAD).</p>
        </div>

        <div class="setting-group">
          <label class="toggle-label">
            <input 
              type="checkbox" 
              bind:checked={$settings.autoSend}
            />
            <span>Auto-send on silence</span>
          </label>
          <p class="hint">Turn handling is voice-first; silence triggers processing.</p>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .settings-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .settings-panel {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.98));
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 16px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow: hidden;
    animation: slideUp 0.3s ease;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  @keyframes slideUp {
    from {
      transform: translateY(20px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 24px;
    border-bottom: 1px solid rgba(59, 130, 246, 0.2);
  }

  .panel-header h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
    color: #e2e8f0;
  }

  .close-button {
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

  .close-button:hover {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
  }

  .close-button svg {
    width: 20px;
    height: 20px;
    stroke-width: 2.5;
  }

  .panel-content {
    padding: 24px;
    overflow-y: auto;
    max-height: calc(80vh - 80px);
  }

  .setting-group {
    margin-bottom: 28px;
  }

  .setting-group:last-child {
    margin-bottom: 0;
  }

  .setting-group > label {
    display: block;
    font-size: 0.9rem;
    font-weight: 500;
    color: #cbd5e1;
    margin-bottom: 8px;
  }

  select {
    width: 100%;
    padding: 12px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 8px;
    color: #e2e8f0;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  select:hover {
    border-color: rgba(59, 130, 246, 0.5);
  }

  select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    padding: 12px;
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .toggle-label:hover {
    background: rgba(15, 23, 42, 0.6);
    border-color: rgba(59, 130, 246, 0.4);
  }

  .toggle-label input[type="checkbox"] {
    width: 44px;
    height: 24px;
    position: relative;
    appearance: none;
    background: rgba(71, 85, 105, 0.5);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.3s ease;
    flex-shrink: 0;
  }

  .toggle-label input[type="checkbox"]:checked {
    background: #3b82f6;
  }

  .toggle-label input[type="checkbox"]::before {
    content: '';
    position: absolute;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: white;
    top: 3px;
    left: 3px;
    transition: all 0.3s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  }

  .toggle-label input[type="checkbox"]:checked::before {
    left: 23px;
  }

  .toggle-label span {
    color: #e2e8f0;
    font-size: 0.9rem;
  }

  .slider-group {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  input[type="range"] {
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: rgba(71, 85, 105, 0.5);
    outline: none;
    appearance: none;
  }

  input[type="range"]::-webkit-slider-thumb {
    appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #3b82f6;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  input[type="range"]::-webkit-slider-thumb:hover {
    transform: scale(1.2);
    box-shadow: 0 0 0 6px rgba(59, 130, 246, 0.2);
  }

  input[type="range"]::-moz-range-thumb {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #3b82f6;
    border: none;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .slider-value {
    min-width: 45px;
    text-align: right;
    font-size: 0.9rem;
    font-weight: 600;
    color: #60a5fa;
  }

  .hint {
    margin: 8px 0 0;
    font-size: 0.75rem;
    color: #64748b;
    line-height: 1.4;
  }

  @media (max-width: 640px) {
    .settings-panel {
      width: 95%;
    }

    .panel-header {
      padding: 20px;
    }

    .panel-content {
      padding: 20px;
    }
  }
</style>
