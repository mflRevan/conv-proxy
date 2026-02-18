<script lang="ts">
  import { audio } from '../stores/audio';
  import { audioRecorder } from '../services/audioRecorder';

  function handleClick() {
    if ($audio.micState === 'idle') {
      audioRecorder.start();
    } else if ($audio.micState === 'listening') {
      audioRecorder.stop();
    }
  }

  $: isListening = $audio.micState === 'listening';
  $: isProcessing = $audio.micState === 'processing';
  $: disabled = isProcessing;
</script>

<button 
  class="voice-button" 
  class:listening={isListening}
  class:processing={isProcessing}
  on:click={handleClick}
  {disabled}
  aria-label={isListening ? 'Stop recording' : 'Start recording'}
>
  <div class="icon-wrapper">
    {#if isProcessing}
      <div class="processing-spinner"></div>
    {:else}
      <svg class="mic-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/>
        <line x1="8" y1="23" x2="16" y2="23"/>
      </svg>
    {/if}
  </div>
  
  {#if isListening}
    <div class="pulse-ring"></div>
    <div class="pulse-ring delay"></div>
  {/if}
</button>

<style>
  .voice-button {
    position: relative;
    width: 140px;
    height: 140px;
    border-radius: 50%;
    border: none;
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 
      0 10px 30px rgba(59, 130, 246, 0.3),
      0 0 0 0 rgba(59, 130, 246, 0);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .voice-button:hover:not(:disabled) {
    transform: scale(1.05);
    box-shadow: 
      0 15px 40px rgba(59, 130, 246, 0.4),
      0 0 0 8px rgba(59, 130, 246, 0.1);
  }

  .voice-button:active:not(:disabled) {
    transform: scale(0.95);
  }

  .voice-button:disabled {
    cursor: not-allowed;
    opacity: 0.7;
  }

  .voice-button.listening {
    background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
    animation: pulse-glow 2s ease-in-out infinite;
  }

  .voice-button.processing {
    background: linear-gradient(135deg, #ca8a04 0%, #eab308 100%);
  }

  .icon-wrapper {
    position: relative;
    z-index: 2;
  }

  .mic-icon {
    width: 48px;
    height: 48px;
    stroke-width: 2.5;
    color: white;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
  }

  .processing-spinner {
    width: 48px;
    height: 48px;
    border: 4px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .pulse-ring {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 3px solid #ef4444;
    animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    pointer-events: none;
  }

  .pulse-ring.delay {
    animation-delay: 1s;
  }

  @keyframes pulse-glow {
    0%, 100% {
      box-shadow: 
        0 10px 30px rgba(239, 68, 68, 0.4),
        0 0 0 0 rgba(239, 68, 68, 0.4);
    }
    50% {
      box-shadow: 
        0 15px 40px rgba(239, 68, 68, 0.5),
        0 0 0 8px rgba(239, 68, 68, 0.2);
    }
  }

  @keyframes pulse-ring {
    0% {
      transform: translate(-50%, -50%) scale(1);
      opacity: 1;
    }
    100% {
      transform: translate(-50%, -50%) scale(1.8);
      opacity: 0;
    }
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 640px) {
    .voice-button {
      width: 120px;
      height: 120px;
    }
    
    .mic-icon {
      width: 40px;
      height: 40px;
    }
  }
</style>
