<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { connect, disconnect } from './lib/services/websocket';
  
  import StatusBar from './lib/components/StatusBar.svelte';
  import ResponseDisplay from './lib/components/ResponseDisplay.svelte';
  import AudioVisualizer from './lib/components/AudioVisualizer.svelte';
  import VoiceButton from './lib/components/VoiceButton.svelte';
  import TranscriptionDisplay from './lib/components/TranscriptionDisplay.svelte';
  import TaskDraft from './lib/components/TaskDraft.svelte';
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
  
  <div class="content">
    <ResponseDisplay />
    
    <div class="voice-controls">
      <AudioVisualizer />
      <VoiceButton />
      <TranscriptionDisplay />
    </div>
  </div>

  <TaskDraft />
  <SettingsPanel />
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #e2e8f0;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    overflow: hidden;
  }

  :global(*) {
    box-sizing: border-box;
  }

  :global(::selection) {
    background: rgba(59, 130, 246, 0.3);
  }

  :global(::-webkit-scrollbar) {
    width: 8px;
    height: 8px;
  }

  :global(::-webkit-scrollbar-track) {
    background: rgba(15, 23, 42, 0.5);
  }

  :global(::-webkit-scrollbar-thumb) {
    background: rgba(59, 130, 246, 0.3);
    border-radius: 4px;
  }

  :global(::-webkit-scrollbar-thumb:hover) {
    background: rgba(59, 130, 246, 0.5);
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
  }

  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .voice-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 24px;
    padding: 32px 20px;
    background: linear-gradient(to top, rgba(15, 23, 42, 0.8), transparent);
  }

  @media (max-width: 640px) {
    .voice-controls {
      padding: 24px 16px;
      gap: 20px;
    }
  }

  @media (max-height: 600px) {
    .voice-controls {
      padding: 16px;
      gap: 16px;
    }
  }
</style>
