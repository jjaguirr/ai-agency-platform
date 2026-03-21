<script lang="ts">
  import { onMount } from "svelte";
  import { getSettings, putSettings, ApiError } from "../lib/api";
  import type { Settings, Priority } from "../lib/types";

  let settings: Settings | null = null;
  let loading = true;
  let saving = false;
  let status = "";

  const priorities: Priority[] = ["LOW", "MEDIUM", "HIGH", "URGENT"];

  onMount(async () => {
    try {
      settings = await getSettings();
    } catch (e) {
      status = e instanceof ApiError ? e.message : "Failed to load settings";
    } finally {
      loading = false;
    }
  });

  async function save() {
    if (!settings) return;
    saving = true;
    status = "";
    try {
      settings = await putSettings(settings);
      status = "Saved.";
    } catch (e) {
      status = e instanceof ApiError ? e.message : "Save failed";
    } finally {
      saving = false;
    }
  }
</script>

<h1>Configuration</h1>

{#if loading}
  <p aria-busy="true">Loading…</p>
{:else if !settings}
  <p>{status}</p>
{:else}
  <form on:submit|preventDefault={save}>
    <article>
      <header><strong>Working hours</strong></header>
      <div class="grid">
        <label>
          Start
          <input type="time" bind:value={settings.working_hours.start} />
        </label>
        <label>
          End
          <input type="time" bind:value={settings.working_hours.end} />
        </label>
      </div>
      <label>
        Timezone
        <input
          type="text"
          bind:value={settings.working_hours.timezone}
          placeholder="America/New_York"
        />
      </label>
    </article>

    <article>
      <header><strong>Morning briefing</strong></header>
      <label>
        <input type="checkbox" role="switch" bind:checked={settings.briefing.enabled} />
        Enable daily briefing
      </label>
      <label>
        Briefing time
        <input type="time" bind:value={settings.briefing.time} disabled={!settings.briefing.enabled} />
      </label>
    </article>

    <article>
      <header><strong>Proactive messages</strong></header>
      <label>
        Minimum priority
        <select bind:value={settings.proactive.priority_threshold}>
          {#each priorities as p}<option value={p}>{p}</option>{/each}
        </select>
      </label>
      <div class="grid">
        <label>
          Daily cap
          <input type="number" min="0" max="50" bind:value={settings.proactive.daily_cap} />
        </label>
        <label>
          Idle nudge (minutes)
          <input type="number" min="0" bind:value={settings.proactive.idle_nudge_minutes} />
        </label>
      </div>
    </article>

    <article>
      <header><strong>Connected services</strong></header>
      <p class="muted">Connection flows are managed externally. Display only.</p>
      <div class="row">
        <span class="status-dot" class:ok={settings.connected_services.calendar} class:down={!settings.connected_services.calendar}></span>
        <span>Calendar</span>
        <span class="spacer"></span>
        <span class="muted">{settings.connected_services.calendar ? "connected" : "not connected"}</span>
      </div>
      <div class="row">
        <span class="status-dot" class:ok={settings.connected_services.n8n} class:down={!settings.connected_services.n8n}></span>
        <span>n8n</span>
        <span class="spacer"></span>
        <span class="muted">{settings.connected_services.n8n ? "connected" : "not connected"}</span>
      </div>
    </article>

    <div class="row">
      <button type="submit" aria-busy={saving} disabled={saving}>Save</button>
      {#if status}<span class="muted">{status}</span>{/if}
    </div>
  </form>
{/if}
