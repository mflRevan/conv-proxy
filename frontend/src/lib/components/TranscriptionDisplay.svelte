<script lang="ts">
  import { audio } from '../stores/audio';
  $: text = $audio.currentTranscription || '';
  $: listening = $audio.micState === 'listening';
</script>

<div class="transcription" class:listening={listening}>
  {#if text}
    <p class="text">{text}</p>
  {:else if listening}
    <p class="placeholder">Listening…</p>
  {:else}
    <p class="placeholder idle">Awaiting voice input…</p>
  {/if}
</div>

<style>
  .transcription {
    padding: 12px 16px;
    background: rgba(30, 41, 59, 0.45);
    border: 1px solid rgba(59, 130, 246, 0.25);
    border-radius: 12px;
    min-height: 60px;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color .2s ease;
  }
  .transcription.listening { border-color: rgba(14,165,233,.6); }
  .text { margin:0; color:#e2e8f0; font-size:.98rem; line-height:1.4; text-align:center; }
  .placeholder { margin:0; color:#64748b; font-size:.9rem; }
  .placeholder.idle { color:#475569; }
</style>
