<script lang="ts">
  import { conversation } from '../stores/conversation';

  let isExpanded = false;

  $: hasDraft = $conversation.taskDraft.length > 0;

  function toggle() {
    isExpanded = !isExpanded;
  }
</script>

{#if hasDraft}
  <div class="task-draft" class:expanded={isExpanded}>
    <button class="draft-header" on:click={toggle}>
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>
        <rect x="9" y="3" width="6" height="4" rx="1"/>
        <path d="m9 12 2 2 4-4"/>
      </svg>
      <span class="label">Task Draft</span>
      <svg class="chevron" class:rotated={isExpanded} viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
    
    {#if isExpanded}
      <div class="draft-content">
        <p>{$conversation.taskDraft}</p>
      </div>
    {/if}
  </div>
{/if}

<style>
  .task-draft {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(15, 23, 42, 0.95);
    border-top: 1px solid rgba(59, 130, 246, 0.3);
    backdrop-filter: blur(10px);
    z-index: 10;
    transition: all 0.3s ease;
  }

  .draft-header {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 24px;
    background: none;
    border: none;
    color: #e2e8f0;
    cursor: pointer;
    transition: background 0.2s ease;
  }

  .draft-header:hover {
    background: rgba(59, 130, 246, 0.05);
  }

  .icon {
    width: 20px;
    height: 20px;
    stroke-width: 2;
    color: #60a5fa;
  }

  .label {
    flex: 1;
    text-align: left;
    font-weight: 500;
    font-size: 0.875rem;
  }

  .chevron {
    width: 16px;
    height: 16px;
    stroke-width: 2.5;
    color: #94a3b8;
    transition: transform 0.3s ease;
  }

  .chevron.rotated {
    transform: rotate(180deg);
  }

  .draft-content {
    padding: 0 24px 20px;
    animation: slideDown 0.3s ease;
  }

  .draft-content p {
    margin: 0;
    padding: 16px;
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 8px;
    color: #cbd5e1;
    line-height: 1.6;
    font-size: 0.9rem;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      max-height: 0;
    }
    to {
      opacity: 1;
      max-height: 200px;
    }
  }

  @media (max-width: 640px) {
    .draft-header {
      padding: 12px 16px;
    }

    .draft-content {
      padding: 0 16px 16px;
    }
  }
</style>
