<script lang="ts">
  import { conversation } from '../stores/conversation';
  import { afterUpdate } from 'svelte';

  let containerEl: HTMLDivElement;
  let shouldAutoScroll = true;

  afterUpdate(() => {
    if (shouldAutoScroll && containerEl) {
      containerEl.scrollTop = containerEl.scrollHeight;
    }
  });

  function handleScroll() {
    if (!containerEl) return;
    const isAtBottom = containerEl.scrollHeight - containerEl.scrollTop - containerEl.clientHeight < 50;
    shouldAutoScroll = isAtBottom;
  }

  $: hasContent = $conversation.messages.length > 0 || $conversation.currentResponse;
</script>

<div class="response-container" bind:this={containerEl} on:scroll={handleScroll}>
  {#if !hasContent}
    <div class="empty-state">
      <div class="jarvis-logo">
        <svg viewBox="0 0 100 100" fill="none">
          <circle cx="50" cy="50" r="45" stroke="url(#grad1)" stroke-width="2" opacity="0.3"/>
          <circle cx="50" cy="50" r="35" stroke="url(#grad1)" stroke-width="2" opacity="0.5"/>
          <circle cx="50" cy="50" r="25" stroke="url(#grad1)" stroke-width="2" opacity="0.7"/>
          <circle cx="50" cy="50" r="8" fill="url(#grad1)"/>
          <defs>
            <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#60a5fa;stop-opacity:1" />
            </linearGradient>
          </defs>
        </svg>
      </div>
      <h2>Jarvis Voice Assistant</h2>
      <p>Press the microphone button to start a conversation</p>
    </div>
  {:else}
    <div class="messages">
      {#each $conversation.messages as msg (msg.id)}
        <div class="message" class:user={msg.role === 'user'} class:assistant={msg.role === 'assistant'}>
          <div class="message-content">
            <p>{msg.content}</p>
            {#if msg.reasoning}
              <details class="reasoning">
                <summary>View reasoning</summary>
                <pre>{msg.reasoning}</pre>
              </details>
            {/if}
          </div>
        </div>
      {/each}

      {#if $conversation.currentResponse}
        <div class="message assistant streaming">
          <div class="message-content">
            <p>{$conversation.currentResponse}<span class="cursor">▊</span></p>
            {#if $conversation.currentReasoning}
              <details class="reasoning" open>
                <summary>Reasoning</summary>
                <pre>{$conversation.currentReasoning}</pre>
              </details>
            {/if}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .response-container {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    scroll-behavior: smooth;
  }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #475569;
    text-align: center;
    gap: 20px;
  }

  .jarvis-logo {
    width: 120px;
    height: 120px;
    animation: rotate 20s linear infinite;
  }

  .jarvis-logo svg {
    width: 100%;
    height: 100%;
  }

  @keyframes rotate {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  .empty-state h2 {
    margin: 0;
    font-size: 1.8rem;
    font-weight: 600;
    background: linear-gradient(135deg, #3b82f6, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .empty-state p {
    margin: 0;
    font-size: 1rem;
    color: #64748b;
  }

  .messages {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .message {
    display: flex;
    animation: slideIn 0.3s ease;
  }

  .message.user {
    justify-content: flex-end;
  }

  .message.assistant {
    justify-content: flex-start;
  }

  .message-content {
    max-width: 70%;
    padding: 16px 20px;
    border-radius: 16px;
    position: relative;
  }

  .message.user .message-content {
    background: linear-gradient(135deg, #1e3a8a, #3b82f6);
    color: white;
  }

  .message.assistant .message-content {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(59, 130, 246, 0.2);
    color: #e2e8f0;
  }

  .message-content p {
    margin: 0;
    line-height: 1.6;
    font-size: 1rem;
  }

  .cursor {
    animation: blink 1s step-end infinite;
    color: #3b82f6;
    margin-left: 2px;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .reasoning {
    margin-top: 12px;
    padding: 12px;
    background: rgba(0, 0, 0, 0.2);
    border-radius: 8px;
    font-size: 0.85rem;
  }

  .reasoning summary {
    cursor: pointer;
    color: #94a3b8;
    font-size: 0.8rem;
    margin-bottom: 8px;
    user-select: none;
  }

  .reasoning summary:hover {
    color: #cbd5e1;
  }

  .reasoning pre {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: #cbd5e1;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.75rem;
    line-height: 1.4;
  }

  @media (max-width: 640px) {
    .response-container {
      padding: 12px;
    }

    .message-content {
      max-width: 85%;
      padding: 12px 16px;
    }

    .jarvis-logo {
      width: 80px;
      height: 80px;
    }

    .empty-state h2 {
      font-size: 1.4rem;
    }
  }
</style>
