<script lang="ts">
  import { conversation } from '../stores/conversation';
</script>

<section class="task-draft">
  <header>
    <h3>Scratchpad</h3>
    <span class="state">{$conversation.taskDraft ? 'ACTIVE' : 'EMPTY'}</span>
  </header>

  {#if $conversation.taskDraft}
    <div class="draft-body">{$conversation.taskDraft}</div>
  {:else}
    <div class="draft-empty">No buffered task yet. Ask Jarvis Proxy to draft one.</div>
  {/if}
</section>

<style>
  .task-draft { height:100%; display:flex; flex-direction:column; gap:10px; }
  header { display:flex; align-items:center; justify-content:space-between; }
  h3 { margin:0; font-size:.95rem; color:#cbd5e1; }
  .state { font-size:.65rem; padding:4px 8px; border-radius:999px; background:rgba(51,65,85,.8); color:#94a3b8; }
  .draft-body { flex:1; overflow:auto; padding:10px; border-radius:10px; background:rgba(30,41,59,.55); border:1px solid rgba(59,130,246,.2); color:#e2e8f0; font-size:.78rem; line-height:1.4; white-space:pre-wrap; }
  .draft-empty { flex:1; display:flex; align-items:center; justify-content:center; text-align:center; padding:12px; border-radius:10px; border:1px dashed rgba(59,130,246,.25); color:#64748b; font-size:.75rem; }
</style>
