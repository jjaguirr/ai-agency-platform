<script lang="ts">
  import { onMount } from "svelte";
  import { getSettings, putSettings, ApiError } from "../lib/api";
  import type { Settings, Tone } from "../lib/types";

  // Personality lives inside the same Settings document as everything
  // else. We load the full settings, edit the personality slice, and
  // PUT the whole thing back. The other slices pass through untouched.
  let settings: Settings | null = null;
  let loading = true;
  let saving = false;
  let status = "";

  const tones: Tone[] = ["professional", "friendly", "concise", "detailed"];

  onMount(async () => {
    try {
      settings = await getSettings();
    } catch (e) {
      status = e instanceof ApiError ? e.message : "Failed to load";
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

<h1>Personality</h1>
<p class="muted">How your EA communicates. These preferences are stored now; the EA reads them in a later task.</p>

{#if loading}
  <p aria-busy="true">Loading…</p>
{:else if !settings}
  <p>{status}</p>
{:else}
  <form on:submit|preventDefault={save}>
    <article>
      <label>
        Name
        <input type="text" bind:value={settings.personality.name} placeholder="Assistant" />
        <small class="muted">What the EA calls itself in messages.</small>
      </label>

      <label>
        Tone
        <select bind:value={settings.personality.tone}>
          {#each tones as t}<option value={t}>{t}</option>{/each}
        </select>
      </label>

      <label>
        Language
        <input type="text" bind:value={settings.personality.language} placeholder="en" />
        <small class="muted">Primary language for responses (ISO code or name).</small>
      </label>
    </article>

    <div class="row">
      <button type="submit" aria-busy={saving} disabled={saving}>Save</button>
      {#if status}<span class="muted">{status}</span>{/if}
    </div>
  </form>
{/if}
