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

  <section class="hud">
    <section class="left-stage">
      <div class="chat-shell">
        <ResponseDisplay />
      </div>

      <div class="dock">
        <VoiceButton />
        <div class="viz-wrap">
          <AudioVisualizer />
        </div>
      </div>

      <div class="caption-slot">
        <TranscriptionDisplay />
      </div>
    </section>

    <section class="right-stage">
      <div class="hero scratchpad-hero">
        <TaskDraft />
      </div>
      <div class="hero agent-hero">
        <AgentMonitor />
      </div>
    </section>
  </section>

  <SettingsPanel />
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    background:
      radial-gradient(900px 500px at 20% 75%, rgba(59,130,246,.11), transparent 70%),
      radial-gradient(800px 450px at 80% 18%, rgba(34,211,238,.09), transparent 68%),
      linear-gradient(135deg, #0b1020 0%, #111827 100%);
    color: #e2e8f0;
    overflow: hidden;
  }
  :global(*) { box-sizing: border-box; }

  .app { display:flex; flex-direction:column; height:100vh; width:100vw; }

  .hud {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(380px, 42vw);
    gap: 14px;
    padding: 12px;
  }

  .left-stage {
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0,1fr) auto auto;
    gap: 10px;
  }

  .chat-shell {
    min-height: 0;
    display:flex;
    flex-direction:column;
    border-radius: 18px;
    border: 1px solid rgba(96,165,250,.22);
    background: linear-gradient(180deg, rgba(15,23,42,.56), rgba(2,6,23,.5));
    box-shadow: inset 0 1px 0 rgba(148,163,184,.08), 0 22px 46px rgba(2,6,23,.42);
    overflow: hidden;
  }

  .dock {
    display:flex;
    align-items:center;
    justify-content:center;
    gap: 18px;
    padding: 10px 14px;
    border-radius: 14px;
    border: 1px solid rgba(59,130,246,.2);
    background: linear-gradient(180deg, rgba(15,23,42,.68), rgba(15,23,42,.45));
  }

  .viz-wrap {
    width: min(540px, 72%);
    border-radius: 999px;
    border: 1px solid rgba(125,211,252,.28);
    background: rgba(15,23,42,.56);
    padding: 7px 14px;
  }

  .caption-slot {
    min-height: 70px;
    display:flex;
    align-items:center;
  }

  .right-stage {
    min-height: 0;
    display:grid;
    grid-template-rows: minmax(190px, 44%) minmax(220px, 56%);
    gap: 12px;
  }

  .hero {
    border: 1px solid rgba(125,211,252,.36);
    background: linear-gradient(180deg, rgba(8,47,73,.34), rgba(15,23,42,.64));
    border-radius: 30px 22px 28px 20px;
    box-shadow: 0 16px 45px rgba(2,8,23,.55), inset 0 0 0 1px rgba(186,230,253,.08);
    padding: 14px;
    min-height:0;
    overflow: hidden;
    position: relative;
  }

  .hero::after {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(145deg, rgba(186,230,253,.08), transparent 34%, transparent 70%, rgba(56,189,248,.06));
  }

  .scratchpad-hero {
    transform: translateY(2px);
  }

  .agent-hero {
    border-color: rgba(45,212,191,.4);
    background: linear-gradient(180deg, rgba(2,44,34,.38), rgba(15,23,42,.67));
    box-shadow: 0 18px 52px rgba(2,8,23,.58), 0 0 22px rgba(45,212,191,.12);
  }

  @media (max-width: 1100px) {
    .hud { grid-template-columns: 1fr; }
    .right-stage { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr; }
  }

  @media (max-width: 860px) {
    .right-stage { grid-template-columns: 1fr; }
  }
</style>
