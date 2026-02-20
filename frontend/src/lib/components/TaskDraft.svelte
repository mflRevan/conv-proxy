<script lang="ts">
  import { conversation } from '../stores/conversation';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';

  function renderMarkdown(src: string) {
    const raw = marked.parse(src || '', { breaks: true }) as string;
    return DOMPurify.sanitize(raw);
  }

  $: state = $conversation.queuedTask ? 'queued' : $conversation.taskDraft ? 'buffered' : 'empty';
  $: dispatched = $conversation.lastDispatchAt !== null;
  $: displayText = $conversation.queuedTask || $conversation.taskDraft;
</script>

<section class="task-draft {state} {dispatched ? 'dispatched' : ''}">
  <header>
    <h3>Queued Task</h3>
    <div class="badges">
      <span class="state">{state.toUpperCase()}</span>
      {#if state === 'queued' && $conversation.dispatchCountdown}
        <span class="countdown">{$conversation.dispatchCountdown}s</span>
      {/if}
    </div>
  </header>

  {#if displayText}
    <div class="draft-body">{@html renderMarkdown(displayText)}</div>
  {:else}
    <div class="draft-empty">Scratchpad is empty. Ask the proxy to draft a task.</div>
  {/if}
</section>

<style>
  .task-draft { height:100%; display:flex; flex-direction:column; gap:12px; transition: all .3s ease; }
  header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  h3 { margin:0; font-size:1rem; color:#e2e8f0; }
  .badges { display:flex; gap:8px; align-items:center; }
  .state { font-size:.66rem; padding:4px 9px; border-radius:999px; background:rgba(51,65,85,.85); color:#94a3b8; }
  .countdown { font-size:.7rem; padding:4px 9px; border-radius:999px; background:rgba(245,158,11,.2); color:#fbbf24; }
  .draft-body {
    flex:1;
    overflow:auto;
    padding:16px;
    border-radius:16px;
    background:rgba(30,41,59,.44);
    border:1px solid rgba(125,211,252,.28);
    color:#f1f5f9;
    font-size:1.05rem;
    line-height:1.6;
  }
  .draft-empty {
    flex:1;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:16px;
    border-radius:16px;
    border:1px dashed rgba(125,211,252,.28);
    color:#64748b;
    font-size:.9rem;
  }
  .task-draft.buffered { box-shadow: 0 0 18px rgba(59,130,246,.35); }
  .task-draft.queued { box-shadow: 0 0 26px rgba(245,158,11,.45); animation: pulse 1.6s ease-in-out infinite; }
  .task-draft.empty { opacity: 0.75; }
  .task-draft.dispatched { box-shadow: 0 0 30px rgba(34,197,94,.6); }
  @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.01); } }
</style>
