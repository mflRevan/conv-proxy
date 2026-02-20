<script lang="ts">
  import { afterUpdate } from 'svelte';
  import { conversation } from '../stores/conversation';
  import { sendProxyMessage } from '../services/ws';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';

  let containerEl: HTMLDivElement;
  let input = '';
  let shouldAutoScroll = true;

  function renderMarkdown(src: string) {
    const raw = marked.parse(src || '', { breaks: true }) as string;
    return DOMPurify.sanitize(raw);
  }

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    sendProxyMessage(text);
    input = '';
  }

  function handleScroll() {
    if (!containerEl) return;
    const atBottom = containerEl.scrollHeight - containerEl.scrollTop - containerEl.clientHeight < 60;
    shouldAutoScroll = atBottom;
  }

  afterUpdate(() => {
    if (shouldAutoScroll && containerEl) {
      containerEl.scrollTop = containerEl.scrollHeight;
    }
  });
</script>

<section class="proxy-chat">
  <div class="messages" bind:this={containerEl} on:scroll={handleScroll}>
    {#if !$conversation.messages.length && !$conversation.currentResponse}
      <div class="empty">Start a conversation with your proxy agent.</div>
    {:else}
      {#each $conversation.messages as msg (msg.id)}
        <div class="message" class:user={msg.role === 'user'} class:assistant={msg.role === 'assistant'}>
          <div class="bubble">
            <div class="markdown">{@html renderMarkdown(msg.content)}</div>
          </div>
        </div>
      {/each}

      {#if $conversation.currentResponse}
        <div class="message assistant streaming">
          <div class="bubble">
            <div class="markdown streaming">{@html renderMarkdown($conversation.currentResponse)}<span class="cursor">▊</span></div>
          </div>
        </div>
      {/if}
    {/if}
  </div>

  <div class="composer">
    <input
      type="text"
      placeholder="Message the proxy agent..."
      bind:value={input}
      on:keydown={(e) => e.key === 'Enter' && handleSend()}
    />
    <button on:click={handleSend}>Send</button>
  </div>
</section>

<style>
  .proxy-chat {
    display:flex;
    flex-direction:column;
    height:100%;
    min-height:0;
  }
  .messages {
    flex:1;
    min-height:0;
    overflow-y:auto;
    padding: 18px 18px 8px;
    display:flex;
    flex-direction:column;
    gap:14px;
    scroll-behavior:smooth;
  }
  .empty {
    flex:1;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#94a3b8;
    font-size:.95rem;
  }
  .message {
    display:flex;
  }
  .message.user { justify-content:flex-end; }
  .message.assistant { justify-content:flex-start; }
  .bubble {
    max-width:72%;
    padding:14px 18px;
    border-radius:16px;
    background: rgba(15,23,42,.7);
    border: 1px solid rgba(59,130,246,.18);
  }
  .message.user .bubble {
    background: linear-gradient(135deg, #1e3a8a, #2563eb);
    border:none;
    color:white;
  }
  .markdown :global(p) { margin:0; line-height:1.5; }
  .markdown :global(code) { background: rgba(148,163,184,.2); padding:2px 4px; border-radius:4px; }
  .markdown.streaming { opacity:0.9; }
  .cursor { margin-left:2px; opacity:0.6; animation: blink 1s steps(2,end) infinite; }
  @keyframes blink { 50% { opacity: 0.2; } }

  .composer {
    display:flex;
    gap:10px;
    padding: 12px 16px 16px;
    border-top: 1px solid rgba(148,163,184,.15);
    background: rgba(2,6,23,.35);
  }
  .composer input {
    flex:1;
    background: rgba(15,23,42,.9);
    border:1px solid rgba(59,130,246,.3);
    border-radius:10px;
    padding:10px 12px;
    color:#e2e8f0;
  }
  .composer button {
    background:#2563eb;
    color:white;
    border:none;
    border-radius:10px;
    padding:10px 16px;
    cursor:pointer;
  }
</style>
