<script lang="ts">
  let { message = 'No data available' }: { message?: string } = $props();
</script>

<div class="empty">
  <p>{message}</p>
</div>

<style>
  .empty {
    text-align: center;
    padding: var(--space-8);
    color: var(--color-text-secondary);
    font-size: var(--text-sm);
  }
</style>
