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

  onMount(() => {
    connect();
  });

  onDestroy(() => {
    disconnect();
  });
</script>

<main class="app">
  <StatusBar />

  <section class="layout">
    <aside class="left-panel">
      <TaskDraft />
    </aside>

    <section class="center-panel">
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
    </section>

    <aside class="right-panel">
      <AgentMonitor />
    </aside>
  </section>

  <SettingsPanel />
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #e2e8f0;
    overflow: hidden;
  }
  :global(*) { box-sizing: border-box; }

  .app { display:flex; flex-direction:column; height:100vh; width:100vw; }

  .layout {
    flex:1;
    display:grid;
    grid-template-columns: 280px minmax(0,1fr) 340px;
    gap: 12px;
    padding: 12px;
    min-height: 0;
  }

  .left-panel, .right-panel {
    background: rgba(15,23,42,.65);
    border: 1px solid rgba(59,130,246,.22);
    border-radius: 14px;
    backdrop-filter: blur(10px);
    padding: 12px;
    min-height:0;
    overflow: hidden;
  }

  .center-panel { min-height:0; display:flex; flex-direction:column; gap:10px; }

  .response-wrap {
    flex:1;
    min-height: 0;
    background: rgba(15,23,42,.55);
    border: 1px solid rgba(59,130,246,.18);
    border-radius: 14px;
    overflow: hidden;
  }

  .voice-controls {
    display:flex;
    flex-direction:column;
    align-items:center;
    gap:12px;
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(59,130,246,.18);
    background: linear-gradient(to top, rgba(15,23,42,.9), rgba(15,23,42,.55));
    min-height: 240px;
  }

  .caption-slot { width: min(680px, 100%); min-height: 66px; display:flex; align-items:center; }

  @media (max-width: 1200px) {
    .layout { grid-template-columns: 240px minmax(0,1fr); }
    .right-panel { display:none; }
  }

  @media (max-width: 860px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: minmax(0,1fr) auto;
    }
    .left-panel { display:none; }
    .center-panel { order: 1; }
  }
</style>
