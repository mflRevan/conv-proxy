<script lang="ts">
  import { onMount, afterUpdate } from 'svelte';
  import { messages, ttsEnabled } from './lib/stores/chat';
  import { connect, fetchSttBackends, sendMessage } from './lib/services/api';
  import Header from './lib/components/Header.svelte';
  import MessageBubble from './lib/components/MessageBubble.svelte';
  import ChatInput from './lib/components/ChatInput.svelte';

  let chatEl: HTMLElement;

  onMount(() => {
    connect();
    fetchSttBackends();
  });

  afterUpdate(() => {
    if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
  });

  function handleSend(e: CustomEvent<string>) {
    sendMessage(e.detail, $ttsEnabled);
  }
</script>

<div class="app">
  <Header />

  <main class="chat" bind:this={chatEl}>
    {#if $messages.length === 0}
      <div class="empty">
        <span class="empty-icon">◆</span>
        <p>Start a conversation with Jarvis</p>
      </div>
    {:else}
      {#each $messages as msg (msg.id)}
        <MessageBubble message={msg} />
      {/each}
    {/if}
  </main>

  <ChatInput on:send={handleSend} />
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #080c12;
    color: #e2e8f0;
    -webkit-font-smoothing: antialiased;
  }
  :global(*) { box-sizing: border-box; }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    max-width: 900px;
    margin: 0 auto;
  }

  .chat {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    scroll-behavior: smooth;
  }

  .empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #334155;
    gap: 12px;
  }
  .empty-icon {
    font-size: 3rem;
    color: #1e293b;
  }
  .empty p {
    font-size: 0.85rem;
    letter-spacing: 0.03em;
  }

  @media (max-width: 640px) {
    .app { max-width: 100%; }
  }
</style>
