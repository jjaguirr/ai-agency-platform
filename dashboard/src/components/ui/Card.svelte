<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, children }: { title?: string; children: Snippet } = $props();
</script>

<div class="card">
  {#if title}
    <div class="card-header">
      <h3>{title}</h3>
    </div>
  {/if}
  <div class="card-body">
    {@render children()}
  </div>
</div>

<style>
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
  }
  .card-header {
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid var(--color-border);
  }
  .card-body {
    padding: var(--space-5);
  }
</style>
