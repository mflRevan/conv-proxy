<script lang="ts">
  import type { ChatMessage } from '../types/chat';

  export let message: ChatMessage;

  let showThinking = false;
  let showTools = false;

  function formatTime(ts: number): string {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="msg {message.role}">
  <div class="msg-header">
    <span class="msg-role">{message.role === 'user' ? 'You' : 'Jarvis'}</span>
    <span class="msg-time">{formatTime(message.timestamp)}</span>
  </div>

  <div class="msg-body">{message.text}</div>

  {#if message.thinking}
    <button class="meta-toggle" on:click={() => showThinking = !showThinking}>
      💭 {showThinking ? 'Hide' : 'Show'} reasoning
    </button>
    {#if showThinking}
      <pre class="thinking-block">{message.thinking}</pre>
    {/if}
  {/if}

  {#if message.toolCalls?.length}
    <button class="meta-toggle" on:click={() => showTools = !showTools}>
      🔧 {message.toolCalls.length} tool call{message.toolCalls.length > 1 ? 's' : ''} {showTools ? '▴' : '▾'}
    </button>
    {#if showTools}
      <div class="tool-calls">
        {#each message.toolCalls as tc}
          <div class="tool-call">
            <span class="tool-name">{tc.name}</span>
            <code class="tool-args">{JSON.stringify(tc.args)}</code>
            {#if tc.result}
              <pre class="tool-result">{tc.result}</pre>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}

  {#if message.totalMs !== undefined}
    <div class="msg-latency">
      {#if message.ttft !== undefined}
        TTFT {message.ttft.toFixed(0)}ms ·
      {/if}
      Total {message.totalMs.toFixed(0)}ms
    </div>
  {/if}
</div>

<style>
  .msg {
    max-width: 75%;
    padding: 12px 16px;
    border-radius: 16px;
    font-size: 0.92rem;
    line-height: 1.5;
    position: relative;
  }
  .msg.user {
    align-self: flex-end;
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: #fff;
    border-bottom-right-radius: 4px;
  }
  .msg.assistant {
    align-self: flex-start;
    background: #151b27;
    border: 1px solid rgba(255,255,255,0.06);
    border-bottom-left-radius: 4px;
  }
  .msg-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
    font-size: 0.7rem;
    opacity: 0.5;
  }
  .msg-role { font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .msg-body { white-space: pre-wrap; word-break: break-word; }
  .meta-toggle {
    display: inline-block;
    margin-top: 8px;
    background: none;
    border: 1px solid rgba(255,255,255,0.08);
    color: #94a3b8;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.72rem;
    cursor: pointer;
    transition: all 0.15s;
  }
  .meta-toggle:hover { color: #e2e8f0; border-color: rgba(255,255,255,0.15); }
  .thinking-block, .tool-result {
    margin: 6px 0 0;
    padding: 8px 10px;
    background: #0a0e15;
    border-radius: 6px;
    font-size: 0.72rem;
    color: #64748b;
    max-height: 180px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    line-height: 1.4;
  }
  .tool-calls { margin-top: 6px; }
  .tool-call {
    padding: 6px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .tool-name { color: #7dd3fc; font-weight: 600; font-size: 0.75rem; }
  .tool-args { font-size: 0.7rem; color: #94a3b8; margin-left: 6px; }
  .msg-latency {
    margin-top: 6px;
    font-size: 0.65rem;
    color: #475569;
  }
</style>
