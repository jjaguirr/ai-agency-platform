<script lang="ts">
  import { customerId, logout } from '../../lib/auth/store';
</script>

<header class="header">
  <div class="header-left"></div>
  <div class="header-right">
    {#if $customerId}
      <span class="customer-id">{$customerId}</span>
    {/if}
    <button class="btn-logout" onclick={logout}>Logout</button>
  </div>
</header>

<style>
  .header {
    height: var(--header-height);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--space-6);
    flex-shrink: 0;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }
  .customer-id {
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
  }
  .btn-logout {
    background: none;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
    cursor: pointer;
  }
  .btn-logout:hover {
    background: var(--color-bg);
    color: var(--color-text);
  }
</style>
