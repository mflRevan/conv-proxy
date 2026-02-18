<script lang="ts">
  import { conversation } from '../stores/conversation';
  import { agentPanel } from '../stores/agent';
</script>

<section class="task-draft" class:armed={!!$agentPanel.queuedTask}>
  <header>
    <h3>Queued Task / Scratchpad</h3>
    <div class="badges">
      <span class="state">{$conversation.taskDraft ? 'BUFFERED' : 'EMPTY'}</span>
      {#if $agentPanel.queuedTask}
        <span class="queued">QUEUED</span>
      {/if}
    </div>
  </header>

  {#if $conversation.taskDraft}
    <div class="draft-body">{$conversation.taskDraft}</div>
  {:else}
    <div class="draft-empty">No buffered task yet. Tell proxy what to draft.</div>
  {/if}

  {#if $agentPanel.dispatchCountdown !== null}
    <div class="dispatch">Auto-send in {$agentPanel.dispatchCountdown}s (if agent remains idle)</div>
  {/if}
</section>

<style>
  .task-draft { height:100%; display:flex; flex-direction:column; gap:10px; }
  .task-draft.armed { animation: armedGlow 1.3s ease-in-out infinite alternate; }
  @keyframes armedGlow { from { filter: saturate(1); } to { filter: saturate(1.2); } }

  header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  h3 { margin:0; font-size:1rem; color:#e2e8f0; letter-spacing:.01em; }
  .badges { display:flex; gap:6px; }
  .state, .queued { font-size:.66rem; padding:4px 9px; border-radius:999px; }
  .state { background:rgba(51,65,85,.85); color:#94a3b8; }
  .queued { background:rgba(69,26,3,.78); color:#fdba74; border:1px solid rgba(251,146,60,.35); }
  .draft-body { flex:1; overflow:auto; padding:12px; border-radius:12px; background:rgba(30,41,59,.44); border:1px solid rgba(125,211,252,.28); color:#f1f5f9; font-size:.9rem; line-height:1.5; white-space:pre-wrap; }
  .draft-empty { flex:1; display:flex; align-items:center; justify-content:center; text-align:center; padding:12px; border-radius:12px; border:1px dashed rgba(125,211,252,.28); color:#64748b; font-size:.8rem; }
  .dispatch { font-size:.8rem; color:#fbbf24; font-weight:600; }
</style>
