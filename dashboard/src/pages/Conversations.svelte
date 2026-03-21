<script lang="ts">
  import Card from '../components/ui/Card.svelte';
  import Spinner from '../components/ui/Spinner.svelte';
  import EmptyState from '../components/ui/EmptyState.svelte';
  import Badge from '../components/ui/Badge.svelte';
  import { api } from '../lib/auth/store';
  import type { ConversationSummary, HistoryMessage } from '../lib/api/types';

  let { params = {} }: { params?: Record<string, string> } = $props();

  let conversations = $state<ConversationSummary[]>([]);
  let loading = $state(true);
  let search = $state('');
  let selectedId = $state<string | null>(null);
  let messages = $state<HistoryMessage[]>([]);
  let loadingMessages = $state(false);
  let threadChannel = $state<string | undefined>(undefined);

  async function loadConversations() {
    loading = true;
    try {
      const resp = await api.listConversations(200, 0);
      conversations = resp.conversations;
    } catch {
      conversations = [];
    }
    loading = false;
  }

  async function openThread(id: string) {
    selectedId = id;
    loadingMessages = true;
    try {
      const resp = await api.getMessages(id);
      messages = resp.messages;
      threadChannel = resp.channel ?? undefined;
    } catch {
      messages = [];
    }
    loadingMessages = false;
  }

  // If route has :id param, open it
  $effect(() => {
    if (params?.id && params.id !== selectedId) {
      openThread(params.id);
    }
  });

  loadConversations();

  let filtered = $derived(
    search
      ? conversations.filter(c =>
          c.id.toLowerCase().includes(search.toLowerCase()) ||
          c.channel.toLowerCase().includes(search.toLowerCase())
        )
      : conversations
  );

  function formatTime(iso: string) {
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  }
</script>

<div class="conversations-page">
  <h1>Conversations</h1>

  <div class="layout">
    <!-- List panel -->
    <div class="list-panel">
      <input
        type="text"
        class="search-input"
        placeholder="Search conversations..."
        bind:value={search}
      />

      {#if loading}
        <Spinner />
      {:else if filtered.length === 0}
        <EmptyState message="No conversations found" />
      {:else}
        <ul class="conv-list">
          {#each filtered as c}
            <li>
              <button
                class="conv-item"
                class:active={selectedId === c.id}
                onclick={() => openThread(c.id)}
              >
                <div class="conv-row">
                  <span class="conv-id">{c.id.slice(0, 12)}...</span>
                  <Badge label={c.channel} />
                </div>
                <span class="conv-time">{formatTime(c.updated_at)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Thread panel -->
    <div class="thread-panel">
      {#if !selectedId}
        <EmptyState message="Select a conversation to view messages" />
      {:else if loadingMessages}
        <Spinner />
      {:else}
        <div class="thread-header">
          <span class="thread-id">{selectedId}</span>
          {#if threadChannel}
            <Badge label={threadChannel} />
          {/if}
        </div>
        <div class="thread-messages">
          {#each messages as msg}
            <div class="message" class:user={msg.role === 'user'} class:assistant={msg.role === 'assistant'}>
              <div class="msg-meta">
                <span class="msg-role">{msg.role}</span>
                <span class="msg-time">{formatTime(msg.timestamp)}</span>
              </div>
              <div class="msg-content">{msg.content}</div>
            </div>
          {/each}
          {#if messages.length === 0}
            <EmptyState message="No messages in this conversation" />
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .conversations-page { display: flex; flex-direction: column; gap: var(--space-4); height: 100%; }
  .layout {
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: var(--space-4);
    flex: 1;
    min-height: 0;
  }
  @media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }
    .thread-panel { display: none; }
  }

  .list-panel {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .search-input {
    padding: var(--space-3) var(--space-4);
    border: none;
    border-bottom: 1px solid var(--color-border);
    outline: none;
    font-size: var(--text-sm);
  }
  .search-input:focus {
    box-shadow: inset 0 -2px 0 var(--color-primary);
  }
  .conv-list {
    list-style: none;
    overflow-y: auto;
    flex: 1;
  }
  .conv-item {
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-bottom: 1px solid var(--color-border);
    padding: var(--space-3) var(--space-4);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .conv-item:hover { background: var(--color-bg); }
  .conv-item.active { background: #e7f1ff; }
  .conv-row { display: flex; align-items: center; gap: var(--space-2); }
  .conv-id { font-family: var(--font-mono); font-size: var(--text-sm); }
  .conv-time { font-size: var(--text-xs); color: var(--color-text-secondary); }

  .thread-panel {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .thread-header {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--color-border);
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .thread-id { font-family: var(--font-mono); font-size: var(--text-sm); }
  .thread-messages {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .message {
    max-width: 80%;
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-lg);
    font-size: var(--text-sm);
  }
  .message.user {
    background: #e7f1ff;
    align-self: flex-end;
  }
  .message.assistant {
    background: var(--color-bg);
    align-self: flex-start;
  }
  .msg-meta {
    display: flex;
    justify-content: space-between;
    margin-bottom: var(--space-1);
  }
  .msg-role { font-weight: 600; font-size: var(--text-xs); text-transform: capitalize; }
  .msg-time { font-size: var(--text-xs); color: var(--color-text-secondary); }
  .msg-content { white-space: pre-wrap; line-height: 1.5; }
</style>
