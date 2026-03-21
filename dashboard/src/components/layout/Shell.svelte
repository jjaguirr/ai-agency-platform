<script lang="ts">
  import Sidebar from './Sidebar.svelte';
  import Header from './Header.svelte';
  import type { Component } from 'svelte';

  let { page, params = {} }: { page: Component; params?: Record<string, string> } = $props();
</script>

<div class="shell">
  <Sidebar />
  <div class="main">
    <Header />
    <div class="content">
      {#if page}
        <page {params}></page>
      {/if}
    </div>
  </div>
</div>

<style>
  .shell {
    display: flex;
    height: 100%;
  }
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .content {
    flex: 1;
    padding: var(--space-6);
    overflow-y: auto;
  }
</style>
