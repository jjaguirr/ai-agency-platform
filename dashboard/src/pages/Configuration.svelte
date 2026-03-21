<script lang="ts">
  import Card from '../components/ui/Card.svelte';
  import Spinner from '../components/ui/Spinner.svelte';
  import { api } from '../lib/auth/store';
  import type { CustomerSettings } from '../lib/api/types';

  let settings = $state<CustomerSettings>({});
  let loading = $state(true);
  let saving = $state(false);
  let saveMsg = $state('');

  async function load() {
    loading = true;
    try {
      settings = await api.getSettings();
    } catch { /* defaults */ }
    loading = false;
  }

  async function save() {
    saving = true;
    saveMsg = '';
    try {
      settings = await api.updateSettings(settings);
      saveMsg = 'Settings saved';
      setTimeout(() => saveMsg = '', 3000);
    } catch (e: any) {
      saveMsg = 'Failed to save: ' + (e.message || 'unknown error');
    }
    saving = false;
  }

  load();
</script>

<div class="config-page">
  <div class="page-header">
    <h1>Configuration</h1>
    <div class="actions">
      {#if saveMsg}
        <span class="save-msg" class:error={saveMsg.startsWith('Failed')}>{saveMsg}</span>
      {/if}
      <button class="btn-primary" onclick={save} disabled={saving || loading}>
        {saving ? 'Saving...' : 'Save changes'}
      </button>
    </div>
  </div>

  {#if loading}
    <Spinner />
  {:else}
    <div class="sections">
      <!-- Working Hours -->
      <Card title="Working Hours">
        <div class="form-grid">
          <label class="field">
            <span class="label">Start time</span>
            <input type="time" bind:value={settings.working_hours_start} />
          </label>
          <label class="field">
            <span class="label">End time</span>
            <input type="time" bind:value={settings.working_hours_end} />
          </label>
          <label class="field">
            <span class="label">Timezone</span>
            <input type="text" bind:value={settings.timezone} placeholder="America/New_York" />
          </label>
        </div>
      </Card>

      <!-- Briefing Schedule -->
      <Card title="Briefing Schedule">
        <div class="form-grid">
          <label class="field checkbox-field">
            <input type="checkbox" bind:checked={settings.briefing_enabled} />
            <span>Enable morning briefing</span>
          </label>
          <label class="field">
            <span class="label">Briefing time</span>
            <input type="time" bind:value={settings.briefing_time} />
          </label>
        </div>
      </Card>

      <!-- Proactive Settings -->
      <Card title="Proactive Messaging">
        <div class="form-grid">
          <label class="field">
            <span class="label">Priority threshold</span>
            <select bind:value={settings.proactive_priority_threshold}>
              <option value={null}>-- Not set --</option>
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
            </select>
          </label>
          <label class="field">
            <span class="label">Daily cap</span>
            <input type="number" bind:value={settings.proactive_daily_cap} min="0" max="100" placeholder="No limit" />
          </label>
          <label class="field">
            <span class="label">Idle nudge (minutes)</span>
            <input type="number" bind:value={settings.proactive_idle_nudge_minutes} min="0" max="1440" placeholder="Disabled" />
          </label>
        </div>
      </Card>

      <!-- Connected Services -->
      <Card title="Connected Services">
        <!-- TODO: Actual connection flows are out of scope for this task.
             Display-only: shows which integrations are active. -->
        <div class="services-grid">
          <div class="service-item">
            <span class="service-name">Calendar</span>
            <span class="service-status connected">Connected</span>
          </div>
          <div class="service-item">
            <span class="service-name">n8n Workflows</span>
            <span class="service-status disconnected">Not configured</span>
          </div>
          <div class="service-item">
            <span class="service-name">WhatsApp</span>
            <span class="service-status connected">Connected</span>
          </div>
        </div>
      </Card>
    </div>
  {/if}
</div>

<style>
  .config-page { display: flex; flex-direction: column; gap: var(--space-6); }
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--space-3);
  }
  .actions { display: flex; align-items: center; gap: var(--space-3); }
  .save-msg { font-size: var(--text-sm); color: var(--color-success); }
  .save-msg.error { color: var(--color-danger); }
  .sections { display: flex; flex-direction: column; gap: var(--space-5); }
  .form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-4);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .checkbox-field {
    flex-direction: row;
    align-items: center;
    gap: var(--space-2);
    grid-column: 1 / -1;
  }
  .label { font-size: var(--text-sm); font-weight: 500; color: var(--color-text-secondary); }
  input[type="text"], input[type="time"], input[type="number"], select {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  input:focus, select:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.15);
  }
  .btn-primary {
    background: var(--color-primary);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    padding: var(--space-2) var(--space-5);
    font-weight: 500;
    cursor: pointer;
  }
  .btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .services-grid { display: flex; flex-direction: column; gap: var(--space-3); }
  .service-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--color-border);
  }
  .service-item:last-child { border-bottom: none; }
  .service-name { font-weight: 500; }
  .service-status { font-size: var(--text-sm); }
  .connected { color: var(--color-success); }
  .disconnected { color: var(--color-text-secondary); }
</style>
