<script lang="ts">
  import { agentPanel } from '../stores/agent';

  function formatContent(content: string): { kind: 'code' | 'text'; value: string }[] {
    if (!content) return [];
    const blocks: { kind: 'code' | 'text'; value: string }[] = [];
    const regex = /```[\w-]*\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = regex.exec(content)) !== null) {
      const pre = content.slice(lastIndex, m.index).trim();
      if (pre) blocks.push({ kind: 'text', value: pre });
      blocks.push({ kind: 'code', value: m[1].trim() });
      lastIndex = regex.lastIndex;
    }
    const tail = content.slice(lastIndex).trim();
    if (tail) blocks.push({ kind: 'text', value: tail });
    return blocks.length ? blocks : [{ kind: 'text', value: content }];
  }
</script>

<section class="agent-monitor">
  <header>
    <h3>Main Agent Live</h3>
    <span class="badge" class:busy={$agentPanel.status === 'busy'}>{$agentPanel.status.toUpperCase()}</span>
  </header>

  {#if $agentPanel.currentTask}
    <div class="current-task">{$agentPanel.currentTask}</div>
  {/if}

  <div class="tool-strip">
    {#each $agentPanel.toolEvents as evt (evt.id)}
      <div class="tool-pill">
        <span class="dot"></span>
        <span>{evt.tool}</span>
      </div>
    {/each}
  </div>

  {#if $agentPanel.queuedTask}
    <div class="queue-card">
      <div class="queue-title">Queued task armed</div>
      <div class="queue-task">{$agentPanel.queuedTask}</div>
      {#if $agentPanel.dispatchCountdown !== null}
        <div class="countdown">Dispatch in {$agentPanel.dispatchCountdown}s</div>
      {/if}
    </div>
  {/if}

  <div class="feed">
    {#each $agentPanel.progressFeed as item (item.id)}
      <article class="item" class:done={item.state === 'done'}>
        <div class="row">
          <strong>{item.title}</strong>
          <span>{item.progress}%</span>
        </div>
        <div class="bar"><span style={`width:${item.progress}%`}></span></div>

        {#each formatContent(item.content) as block}
          {#if block.kind === 'code'}
            <pre>{block.value}</pre>
          {:else}
            <p>{block.value}</p>
          {/if}
        {/each}
      </article>
    {/each}
  </div>
</section>

<style>
  .agent-monitor { height: 100%; display:flex; flex-direction:column; gap:10px; }
  header { display:flex; justify-content:space-between; align-items:center; }
  h3 { margin:0; font-size:0.95rem; color:#cbd5e1; }
  .badge { font-size:.68rem; padding:4px 8px; border-radius:999px; background:#334155; color:#cbd5e1; }
  .badge.busy { background:#0f766e; color:#99f6e4; }
  .current-task { font-size:.82rem; color:#94a3b8; line-height:1.35; }
  .tool-strip { display:flex; flex-wrap:wrap; gap:6px; min-height:28px; }
  .tool-pill { display:flex; align-items:center; gap:6px; padding:4px 8px; border:1px solid rgba(59,130,246,.25); border-radius:999px; font-size:.72rem; color:#bfdbfe; background:rgba(30,41,59,.6); }
  .dot { width:6px; height:6px; border-radius:50%; background:#38bdf8; box-shadow:0 0 10px #38bdf8; }
  .queue-card { border:1px solid rgba(125,211,252,.35); background:rgba(8,47,73,.5); border-radius:10px; padding:10px; }
  .queue-title { font-size:.74rem; color:#bae6fd; }
  .queue-task { font-size:.77rem; color:#e2e8f0; margin-top:4px; }
  .countdown { margin-top:6px; font-size:.74rem; color:#fde68a; }
  .feed { overflow:auto; display:flex; flex-direction:column; gap:8px; padding-right:4px; }
  .item { border:1px solid rgba(59,130,246,.2); background:rgba(30,41,59,.45); border-radius:10px; padding:10px; }
  .item.done { border-color: rgba(16,185,129,.35); }
  .row { display:flex; justify-content:space-between; font-size:.78rem; color:#cbd5e1; margin-bottom:6px; }
  .bar { height:6px; border-radius:999px; background:rgba(15,23,42,.8); overflow:hidden; margin-bottom:8px; }
  .bar span { display:block; height:100%; background:linear-gradient(90deg,#38bdf8,#22d3ee); transition:width .4s ease; }
  p { margin:0 0 6px; font-size:.75rem; color:#cbd5e1; white-space:pre-wrap; }
  pre { margin:0; font-size:.71rem; color:#dbeafe; background:#0b1220; border:1px solid rgba(59,130,246,.25); border-radius:8px; padding:8px; overflow:auto; }
</style>
