<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { connect, disconnect } from './lib/services/websocket';

  import StatusBar from './lib/components/StatusBar.svelte';
  import ResponseDisplay from './lib/components/ResponseDisplay.svelte';
  import AudioVisualizer from './lib/components/AudioVisualizer.svelte';
  import VoiceButton from './lib/components/VoiceButton.svelte';
  import TranscriptionDisplay from './lib/components/TranscriptionDisplay.svelte';
  import TaskDraft from './lib/components/TaskDraft.svelte';
  import AgentMonitor from './lib/components/AgentMonitor.svelte';
  import SettingsPanel from './lib/components/SettingsPanel.svelte';

  onMount(() => connect());
  onDestroy(() => disconnect());
</script>

<main class="app">
  <StatusBar />

  <section class="stage">
    <div class="response-wrap">
      <ResponseDisplay />
    </div>

    <div class="voice-controls">
      <AudioVisualizer />
      <VoiceButton />
      <div class="caption-slot">
        <TranscriptionDisplay />
      </div>
    </div>

    <aside class="floating left"><TaskDraft /></aside>
    <aside class="floating right"><AgentMonitor /></aside>
  </section>

  <SettingsPanel />
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background: radial-gradient(1100px 600px at 50% 100%, rgba(56, 189, 248, 0.08), transparent 60%),
      linear-gradient(135deg, #0f172a 0%, #111827 100%);
    color: #e2e8f0;
    overflow: hidden;
  }
  :global(*) { box-sizing: border-box; }

  .app { display: flex; flex-direction: column; height: 100vh; width: 100vw; }

  .stage {
    position: relative;
    flex: 1;
    min-height: 0;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .response-wrap {
    flex: 1;
    min-height: 0;
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(59, 130, 246, 0.18);
    border-radius: 16px;
    overflow: hidden;
  }

  .voice-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(59, 130, 246, 0.18);
    background: linear-gradient(to top, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.55));
    min-height: 240px;
  }

  .caption-slot {
    width: min(680px, 100%);
    min-height: 66px;
    display: flex;
    align-items: center;
  }

  .floating {
    position: absolute;
    top: 88px;
    width: min(320px, 28vw);
    height: min(64vh, 620px);
    border-radius: 16px;
    border: 1px solid rgba(125, 211, 252, 0.28);
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.7), rgba(15, 23, 42, 0.52));
    backdrop-filter: blur(11px);
    box-shadow: 0 14px 50px rgba(2, 8, 23, 0.45);
    padding: 12px;
    overflow: hidden;
    animation: floatIn .35s ease;
  }

  .floating.left { left: 20px; }
  .floating.right { right: 20px; }

  @keyframes floatIn {
    from { opacity: 0; transform: translateY(8px) scale(0.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  @media (max-width: 1200px) {
    .floating { width: min(280px, 34vw); }
  }

  @media (max-width: 900px) {
    .floating { display: none; }
  }
</style>
