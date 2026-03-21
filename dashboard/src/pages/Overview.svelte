<script lang="ts">
  import { onMount } from "svelte";
  import {
    getActivitySummary,
    getNotifications,
    getSpecialistStatus,
    listConversations,
  } from "../lib/api";
  import type {
    ActivitySummary,
    ConversationSummary,
    Notification,
    SpecialistStatus,
  } from "../lib/types";

  let activity: ActivitySummary | null = null;
  let specialists: SpecialistStatus[] = [];
  let recent: ConversationSummary[] = [];
  let notifications: Notification[] = [];
  let error = "";

  onMount(async () => {
    // Fire everything in parallel; each failure is independent.
    const [act, spec, convs, notifs] = await Promise.allSettled([
      getActivitySummary(),
      getSpecialistStatus(),
      listConversations(5, 0),
      getNotifications(),
    ]);

    if (act.status === "fulfilled") activity = act.value;
    if (spec.status === "fulfilled") specialists = spec.value;
    if (convs.status === "fulfilled") recent = convs.value.conversations;
    if (notifs.status === "fulfilled") notifications = notifs.value;

    const failed = [act, spec, convs, notifs].filter((r) => r.status === "rejected");
    if (failed.length) {
      error = `Some panels failed to load (${failed.length}/${4}).`;
    }
  });

  function fmt(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<h1>Overview</h1>
{#if error}<p class="muted">{error}</p>{/if}

<section>
  <h2>Today's activity</h2>
  <div class="grid-cards">
    <div class="card">
      <h3>Messages</h3>
      <div class="big">{activity?.messages ?? "—"}</div>
    </div>
    <div class="card">
      <h3>Delegations</h3>
      <div class="big">{activity?.delegations ?? "—"}</div>
    </div>
    <div class="card">
      <h3>Proactive triggers</h3>
      <div class="big">{activity?.proactive_triggers ?? "—"}</div>
    </div>
  </div>
</section>

<section>
  <h2>Specialists</h2>
  <div class="card">
    {#if specialists.length === 0}
      <p class="muted">No specialists registered.</p>
    {:else}
      {#each specialists as s}
        <div class="row">
          <span class="status-dot" class:ok={s.operational} class:down={!s.operational}></span>
          <span>{s.name}</span>
          <span class="spacer"></span>
          <span class="muted">{s.operational ? "operational" : "down"}</span>
        </div>
      {/each}
    {/if}
  </div>
</section>

<section>
  <h2>Recent conversations</h2>
  <div class="card">
    {#if recent.length === 0}
      <p class="muted">No conversations yet.</p>
    {:else}
      {#each recent as c}
        <div class="conv-item">
          <a href="#/history">
            <strong>{c.id.slice(0, 8)}</strong>
            <span class="muted"> · {c.channel} · {fmt(c.updated_at)}</span>
          </a>
        </div>
      {/each}
    {/if}
  </div>
</section>

<section>
  <h2>Pending notifications</h2>
  <div class="card">
    {#if notifications.length === 0}
      <p class="muted">Nothing pending.</p>
    {:else}
      {#each notifications as n}
        <div class="conv-item">
          <strong>[{n.priority}] {n.title}</strong>
          <div class="muted">{n.message}</div>
          <small class="muted">{n.domain} · {fmt(n.created_at)}</small>
        </div>
      {/each}
    {/if}
  </div>
</section>
