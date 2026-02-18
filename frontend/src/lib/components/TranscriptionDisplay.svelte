<script lang="ts">
  import { audio } from '../stores/audio';
  import { conversation } from '../stores/conversation';

  $: text = $audio.currentTranscription || ($conversation.isStreaming ? '' : '');
  $: visible = text.length > 0 || $audio.micState === 'listening';
</script>

{#if visible}
  <div class="transcription" class:empty={!text}>
    {#if text}
      <p class="text">{text}</p>
    {:else}
      <p class="placeholder">Listening...</p>
    {/if}
  </div>
{/if}

<style>
  .transcription {
    padding: 16px 24px;
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 12px;
    backdrop-filter: blur(10px);
    min-height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    max-width: 600px;
    width: 100%;
  }

  .text {
    margin: 0;
    color: #e2e8f0;
    font-size: 1.1rem;
    line-height: 1.6;
    text-align: center;
  }

  .placeholder {
    margin: 0;
    color: #64748b;
    font-size: 1rem;
    font-style: italic;
    animation: pulse-text 2s ease-in-out infinite;
  }

  @keyframes pulse-text {
    0%, 100% {
      opacity: 0.5;
    }
    50% {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    .transcription {
      padding: 12px 16px;
      min-height: 48px;
    }
    
    .text {
      font-size: 1rem;
    }
    
    .placeholder {
      font-size: 0.9rem;
    }
  }
</style>
