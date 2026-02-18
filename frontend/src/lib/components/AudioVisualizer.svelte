<script lang="ts">
  import { audio } from '../stores/audio';

  $: level = $audio.audioLevel;
  $: isActive = $audio.isVadActive;
</script>

<div class="visualizer" class:active={isActive}>
  <div class="bars">
    {#each Array(32) as _, i}
      <div 
        class="bar" 
        style="height: {Math.max(2, (level / 100) * 80 * (0.5 + Math.random() * 0.5))}%"
        style:animation-delay="{i * 0.05}s"
      ></div>
    {/each}
  </div>
</div>

<style>
  .visualizer {
    width: 100%;
    max-width: 500px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 20px;
    opacity: 0.3;
    transition: opacity 0.3s ease;
  }

  .visualizer.active {
    opacity: 1;
  }

  .bars {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    width: 100%;
    height: 100%;
  }

  .bar {
    flex: 1;
    min-height: 2%;
    background: linear-gradient(to top, #3b82f6, #60a5fa);
    border-radius: 2px;
    transition: height 0.1s ease;
    animation: wave 1.5s ease-in-out infinite;
  }

  .visualizer.active .bar {
    background: linear-gradient(to top, #ef4444, #f87171);
  }

  @keyframes wave {
    0%, 100% {
      opacity: 0.6;
    }
    50% {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    .visualizer {
      height: 60px;
      max-width: 100%;
    }
    
    .bars {
      gap: 2px;
    }
  }
</style>
