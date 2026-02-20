<script lang="ts">
  import { agentState } from '../stores/agent';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';

  function renderMarkdown(src: string) {
    const raw = marked.parse(src || '', { breaks: true }) as string;
    return DOMPurify.sanitize(raw);
  }

  $: statusClass = $agentState.status === 'busy' ? 'busy' : $agentState.status === 'error' ? 'error' : 'idle';
</script>

<section class="agent-monitor">
  <header>
    <h3>Agent Status</h3>
    <span class="badge {statusClass}">{$agentState.status}</span>
  </header>

  {#if $agentState.status === 'busy'}
    <div class="busy-block">
      {#if $agentState.currentTool}
        <div class="tool">Tool: <span>{$agentState.currentTool}</span></div>
        {#if $agentState.currentArgs}
          <pre class="tool-args">{$agentState.currentArgs}</pre>
        {/if}
      {/if}
      {#if $agentState.assistantStream}
        <div class="stream">{@html renderMarkdown($agentState.assistantStream)}<span class="cursor">▊</span></div>
      {/if}
      {#if $agentState.thinking}
        <div class="thinking">Thinking…</div>
      {/if}
    </div>
  {:else}
    <div class="idle-block">
      {#if $agentState.lastSummary}
        <div class="summary">{@html renderMarkdown($agentState.lastSummary)}</div>
      {:else}
        <div class="summary empty">Idle. Awaiting next run.</div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .agent-monitor { height:100%; display:flex; flex-direction:column; gap:12px; }
  header { display:flex; justify-content:space-between; align-items:center; }
  h3 { margin:0; font-size:1rem; color:#e2e8f0; }
  .badge { font-size:.7rem; padding:4px 10px; border-radius:999px; text-transform:uppercase; letter-spacing:.08em; }
  .badge.idle { background: rgba(20,184,166,.2); color:#5eead4; }
  .badge.busy { background: rgba(37,99,235,.25); color:#93c5fd; animation: pulse 1.6s ease-in-out infinite; }
  .badge.error { background: rgba(239,68,68,.2); color:#fecaca; }

  .busy-block, .idle-block { flex:1; display:flex; flex-direction:column; gap:10px; overflow:auto; }
  .tool { font-size:.85rem; color:#93c5fd; }
  .tool span { color:#e2e8f0; font-weight:600; }
  .tool-args { margin:0; padding:8px 10px; border-radius:10px; background: rgba(15,23,42,.6); color:#cbd5e1; font-size:.75rem; white-space:pre-wrap; }
  .stream { padding:12px; border-radius:12px; background: rgba(15,23,42,.5); color:#e2e8f0; }
  .thinking { color:#7dd3fc; font-size:.8rem; }
  .summary { padding:12px; border-radius:12px; background: rgba(15,23,42,.5); color:#e2e8f0; }
  .summary.empty { color:#94a3b8; }
  .cursor { margin-left:2px; opacity:0.6; animation: blink 1s steps(2,end) infinite; }
  @keyframes pulse { 0%,100% { box-shadow:0 0 0 rgba(59,130,246,.0);} 50% { box-shadow:0 0 12px rgba(59,130,246,.5);} }
  @keyframes blink { 50% { opacity: 0.2; } }
</style>
