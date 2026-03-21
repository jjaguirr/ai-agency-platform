<script lang="ts">
  import Card from '../components/ui/Card.svelte';
  import Badge from '../components/ui/Badge.svelte';
  import Spinner from '../components/ui/Spinner.svelte';
  import EmptyState from '../components/ui/EmptyState.svelte';
  import { api } from '../lib/auth/store';
  import type { ConversationSummary, NotificationResponse, ActivitySummary, SpecialistStatus } from '../lib/api/types';

  let conversations = $state<ConversationSummary[]>([]);
  let notifications = $state<NotificationResponse[]>([]);
  let loadingConversations = $state(true);
  let loadingNotifications = $state(true);

  // TODO: Replace with real API when activity endpoint exists (GET /v1/activity/today)
  const activity: ActivitySummary = { message_count: 12, specialist_delegations: 3, proactive_triggers: 5 };

  // TODO: Replace with real API when specialist status endpoint exists (GET /v1/specialists/status)
  const specialists: SpecialistStatus[] = [
    { name: 'Calendar', operational: true },
    { name: 'Email', operational: true },
    { name: 'Research', operational: false },
    { name: 'Finance', operational: true },
  ];

  async function loadData() {
    try {
      const resp = await api.listConversations(5, 0);
      conversations = resp.conversations;
    } catch { conversations = []; }
    loadingConversations = false;

    try {
      notifications = await api.peekNotifications();
    } catch { notifications = []; }
    loadingNotifications = false;
  }

  loadData();

  // Poll notifications every 30s
  const interval = setInterval(async () => {
    try { notifications = await api.peekNotifications(); } catch { /* ignore */ }
  }, 30000);

  import { onDestroy } from 'svelte';
  onDestroy(() => clearInterval(interval));

  function priorityVariant(p: string) {
    const map: Record<string, 'danger' | 'warning' | 'info' | 'default'> = {
      URGENT: 'danger', HIGH: 'warning', MEDIUM: 'info', LOW: 'default'
    };
    return map[p] ?? 'default';
  }

  function formatTime(iso: string) {
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  }
</script>

<div class="overview">
  <h1>Overview</h1>

  <!-- Activity summary -->
  <div class="stats-grid">
    <div class="stat-card">
      <span class="stat-value">{activity.message_count}</span>
      <span class="stat-label">Messages today</span>
    </div>
    <div class="stat-card">
      <span class="stat-value">{activity.specialist_delegations}</span>
      <span class="stat-label">Delegations</span>
    </div>
    <div class="stat-card">
      <span class="stat-value">{activity.proactive_triggers}</span>
      <span class="stat-label">Proactive triggers</span>
    </div>
  </div>

  <!-- Specialists -->
  <Card title="Active Specialists">
    <div class="specialist-grid">
      {#each specialists as s}
        <div class="specialist-item">
          <Badge variant={s.operational ? 'success' : 'danger'} label={s.operational ? 'Online' : 'Offline'} />
          <span>{s.name}</span>
        </div>
      {/each}
    </div>
  </Card>

  <div class="two-col">
    <!-- Recent conversations -->
    <Card title="Recent Conversations">
      {#if loadingConversations}
        <Spinner />
      {:else if conversations.length === 0}
        <EmptyState message="No conversations yet" />
      {:else}
        <ul class="list">
          {#each conversations as c}
            <li class="list-item">
              <a href="#/conversations/{c.id}" class="list-link">
                <span class="list-id">{c.id.slice(0, 8)}...</span>
                <Badge label={c.channel} />
                <span class="list-time">{formatTime(c.updated_at)}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </Card>

    <!-- Pending notifications -->
    <Card title="Pending Notifications">
      {#if loadingNotifications}
        <Spinner />
      {:else if notifications.length === 0}
        <EmptyState message="No pending notifications" />
      {:else}
        <ul class="list">
          {#each notifications as n}
            <li class="list-item notification">
              <div class="notif-header">
                <Badge variant={priorityVariant(n.priority)} label={n.priority} />
                <span class="list-time">{formatTime(n.created_at)}</span>
              </div>
              <strong>{n.title}</strong>
              <p class="notif-msg">{n.message}</p>
            </li>
          {/each}
        </ul>
      {/if}
    </Card>
  </div>
</div>

<style>
  .overview { display: flex; flex-direction: column; gap: var(--space-6); }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: var(--space-4);
  }
  .stat-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .stat-value { font-size: var(--text-2xl); font-weight: 700; }
  .stat-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
  .specialist-grid {
    display: flex;
    gap: var(--space-4);
    flex-wrap: wrap;
  }
  .specialist-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
  }
  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-6);
  }
  @media (max-width: 900px) {
    .two-col { grid-template-columns: 1fr; }
  }
  .list { list-style: none; }
  .list-item {
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--color-border);
  }
  .list-item:last-child { border-bottom: none; }
  .list-link {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    text-decoration: none;
    color: var(--color-text);
  }
  .list-link:hover { color: var(--color-primary); }
  .list-id { font-family: var(--font-mono); font-size: var(--text-sm); }
  .list-time { font-size: var(--text-xs); color: var(--color-text-secondary); margin-left: auto; }
  .notification { display: flex; flex-direction: column; gap: var(--space-1); }
  .notif-header { display: flex; align-items: center; gap: var(--space-2); }
  .notif-msg { font-size: var(--text-sm); color: var(--color-text-secondary); }
</style>
