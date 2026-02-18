<script lang="ts">
  import { conversation } from '../stores/conversation';
  import { agentPanel } from '../stores/agent';
</script>

<section class="task-draft">
  <header>
    <h3>Scratchpad</h3>
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
  header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  h3 { margin:0; font-size:.95rem; color:#cbd5e1; }
  .badges { display:flex; gap:6px; }
  .state, .queued { font-size:.64rem; padding:4px 8px; border-radius:999px; }
  .state { background:rgba(51,65,85,.8); color:#94a3b8; }
  .queued { background:rgba(8,47,73,.8); color:#bae6fd; border:1px solid rgba(125,211,252,.3); }
  .draft-body { flex:1; overflow:auto; padding:10px; border-radius:10px; background:rgba(30,41,59,.5); border:1px solid rgba(59,130,246,.22); color:#e2e8f0; font-size:.78rem; line-height:1.45; white-space:pre-wrap; }
  .draft-empty { flex:1; display:flex; align-items:center; justify-content:center; text-align:center; padding:12px; border-radius:10px; border:1px dashed rgba(59,130,246,.25); color:#64748b; font-size:.75rem; }
  .dispatch { font-size:.72rem; color:#fde68a; }
</style>
