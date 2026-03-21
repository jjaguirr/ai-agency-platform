<script lang="ts">
  import { onMount } from "svelte";
  import { listConversations, getConversationMessages, ApiError } from "../lib/api";
  import type { ConversationSummary, HistoryMessage } from "../lib/types";

  let conversations: ConversationSummary[] = [];
  let selected: string | null = null;
  let messages: HistoryMessage[] = [];
  let loading = true;
  let loadingThread = false;
  let error = "";

  // Filter state.
  let from = "";
  let to = "";

  onMount(load);

  async function load() {
    loading = true;
    error = "";
    try {
      const res = await listConversations(100, 0);
      conversations = res.conversations;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Failed to load";
    } finally {
      loading = false;
    }
  }

  async function open(id: string) {
    selected = id;
    loadingThread = true;
    messages = [];
    try {
      const res = await getConversationMessages(id);
      messages = res.messages;
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Failed to load thread";
    } finally {
      loadingThread = false;
    }
  }

  // Client-side date filter. The /v1/conversations endpoint doesn't
  // support date-range query params yet; we fetch the window and
  // filter here. Fine for MVP volume.
  $: filtered = conversations.filter((c) => {
    if (from && c.updated_at < from) return false;
    if (to && c.updated_at > to + "T23:59:59") return false;
    return true;
  });

  function fmt(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<h1>Conversations</h1>

{#if selected}
  <button class="secondary outline" on:click={() => (selected = null)}>← Back</button>
  <h2>{selected.slice(0, 12)}</h2>
  {#if loadingThread}
    <p aria-busy="true">Loading…</p>
  {:else if messages.length === 0}
    <p class="muted">No messages.</p>
  {:else}
    {#each messages as m}
      <div class="msg {m.role}">
        <small class="muted">{m.role} · {fmt(m.timestamp)}</small>
        <div>{m.content}</div>
      </div>
    {/each}
  {/if}
{:else}
  <div class="row">
    <label>
      From
      <input type="date" bind:value={from} />
    </label>
    <label>
      To
      <input type="date" bind:value={to} />
    </label>
  </div>

  {#if loading}
    <p aria-busy="true">Loading…</p>
  {:else if error}
    <p>{error}</p>
  {:else if filtered.length === 0}
    <p class="muted">No conversations in this range.</p>
  {:else}
    <div class="card">
      {#each filtered as c}
        <div
          class="conv-item"
          role="button"
          tabindex="0"
          on:click={() => open(c.id)}
          on:keydown={(e) => e.key === "Enter" && open(c.id)}
        >
          <strong>{c.id.slice(0, 12)}</strong>
          <span class="muted"> · {c.channel}</span>
          <div class="muted">Updated {fmt(c.updated_at)}</div>
        </div>
      {/each}
    </div>
  {/if}
{/if}
