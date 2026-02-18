<script lang="ts">
  import { agentPanel } from '../stores/agent';

  const stateLabel: Record<string, string> = {
    busy: 'Working',
    idle: 'Idle',
  };

  $: latest = $agentPanel.progressFeed[$agentPanel.progressFeed.length - 1];
  $: stateText = latest?.state || $agentPanel.status || 'idle';
  $: titleText = latest?.title || $agentPanel.currentTask || 'Awaiting next run';

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

<section class="agent-monitor" style={`--pulse-token:${$agentPanel.pulseToken}`}>
  <header>
    <h3>Main Agent</h3>
    <div class="head-right">
      <span class="bridge" class:on={$agentPanel.bridgeConfigured}>{$agentPanel.bridgeConfigured ? 'linked' : 'mock/offline'}</span>
      <span class="badge" class:busy={$agentPanel.status === 'busy'}>{stateLabel[$agentPanel.status] || $agentPanel.status}</span>
    </div>
  </header>

  <div class="now-card" class:active={$agentPanel.status === 'busy'}>
    <div class="pulse"></div>
    <div>
      <div class="now-label">Now</div>
      <div class="now-title">{titleText}</div>
      <div class="now-sub">State: {stateText}</div>
    </div>
  </div>

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
      <div class="queue-title">Queued task</div>
      <div class="queue-task">{$agentPanel.queuedTask}</div>
      {#if $agentPanel.dispatchCountdown !== null}
        <div class="countdown">Sending in {$agentPanel.dispatchCountdown}s</div>
      {/if}
    </div>
  {/if}

  {#if latest?.content}
    <div class="rich">
      {#each formatContent(latest.content) as block}
        {#if block.kind === 'code'}
          <pre>{block.value}</pre>
        {:else}
          <p>{block.value}</p>
        {/if}
      {/each}
    </div>
  {/if}
</section>

<style>
  .agent-monitor { height: 100%; display:flex; flex-direction:column; gap:12px; }
  header { display:flex; justify-content:space-between; align-items:center; }
  .head-right { display:flex; gap:8px; align-items:center; }
  .bridge { font-size:.66rem; padding:3px 8px; border-radius:999px; border:1px solid rgba(148,163,184,.3); color:#94a3b8; }
  .bridge.on { color:#86efac; border-color: rgba(74,222,128,.4); background: rgba(20,83,45,.25); }
  h3 { margin:0; font-size:1.02rem; color:#e2e8f0; }
  .badge { font-size:.72rem; padding:5px 10px; border-radius:999px; background:#334155; color:#cbd5e1; }
  .badge.busy { background:#0f766e; color:#99f6e4; }

  .now-card {
    position: relative;
    display:flex; gap:12px; align-items:flex-start;
    border:1px solid rgba(56,189,248,.32);
    background: linear-gradient(180deg, rgba(8,47,73,.42), rgba(30,41,59,.52));
    border-radius: 15px;
    padding: 12px;
  }
  .now-card.active { border-color: rgba(45,212,191,.48); box-shadow: 0 0 20px rgba(45,212,191,.14); }
  .pulse {
    margin-top:4px;
    width:10px; height:10px; border-radius:50%;
    background:#22d3ee;
    box-shadow: 0 0 0 0 rgba(34,211,238,.7);
    animation: pulse 1.5s infinite;
    flex: 0 0 auto;
  }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(34,211,238,.6); }
    70% { box-shadow: 0 0 0 10px rgba(34,211,238,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,211,238,0); }
  }
  .now-label { font-size:.7rem; color:#93c5fd; text-transform:uppercase; letter-spacing:.08em; }
  .now-title { margin-top:3px; font-size:1.03rem; font-weight:650; color:#f0f9ff; line-height:1.28; }
  .now-sub { margin-top:4px; font-size:.82rem; color:#93c5fd; }

  .tool-strip { display:flex; flex-wrap:wrap; gap:6px; min-height:28px; }
  .tool-pill { display:flex; align-items:center; gap:6px; padding:4px 8px; border:1px solid rgba(59,130,246,.25); border-radius:999px; font-size:.72rem; color:#bfdbfe; background:rgba(30,41,59,.6); animation: toolIn .25s ease; transition: transform .2s ease, box-shadow .2s ease; }
  .tool-pill:hover { transform: translateY(-1px); box-shadow: 0 6px 14px rgba(56,189,248,.16); }
  .dot { width:6px; height:6px; border-radius:50%; background:#38bdf8; box-shadow:0 0 10px #38bdf8; }
  @keyframes toolIn { from {opacity:0; transform: translateY(4px);} to {opacity:1; transform: translateY(0);} }

  .queue-card { border:1px solid rgba(251,191,36,.4); background:linear-gradient(180deg, rgba(69,26,3,.36), rgba(8,47,73,.5)); border-radius:12px; padding:10px; animation: queuePulse 1.2s ease-in-out infinite alternate; }
  @keyframes queuePulse { from { box-shadow: inset 0 0 0 rgba(251,191,36,0);} to { box-shadow: inset 0 0 24px rgba(251,191,36,.08);} }
  .queue-title { font-size:.74rem; color:#bae6fd; }
  .queue-task { font-size:.77rem; color:#e2e8f0; margin-top:4px; white-space:pre-wrap; }
  .countdown { margin-top:6px; font-size:.74rem; color:#fde68a; }

  .rich { overflow:auto; margin-top:auto; display:flex; flex-direction:column; gap:8px; }
  p { margin:0; font-size:.76rem; color:#cbd5e1; white-space:pre-wrap; }
  pre { margin:0; font-size:.71rem; color:#dbeafe; background:#0b1220; border:1px solid rgba(59,130,246,.25); border-radius:8px; padding:8px; overflow:auto; }
</style>
