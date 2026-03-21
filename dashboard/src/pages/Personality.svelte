<script lang="ts">
  import Card from '../components/ui/Card.svelte';
  import Spinner from '../components/ui/Spinner.svelte';
  import { api } from '../lib/auth/store';
  import type { CustomerSettings, Tone } from '../lib/api/types';

  let settings = $state<CustomerSettings>({});
  let loading = $state(true);
  let saving = $state(false);
  let saveMsg = $state('');

  const toneOptions: { value: Tone; label: string; description: string }[] = [
    { value: 'professional', label: 'Professional', description: 'Formal and business-appropriate' },
    { value: 'friendly', label: 'Friendly', description: 'Warm and approachable' },
    { value: 'concise', label: 'Concise', description: 'Brief and to the point' },
    { value: 'detailed', label: 'Detailed', description: 'Thorough with full context' },
  ];

  const languageOptions = [
    { value: 'en', label: 'English' },
    { value: 'es', label: 'Spanish' },
    { value: 'fr', label: 'French' },
    { value: 'de', label: 'German' },
    { value: 'pt', label: 'Portuguese' },
    { value: 'ja', label: 'Japanese' },
    { value: 'zh', label: 'Chinese' },
  ];

  async function load() {
    loading = true;
    try { settings = await api.getSettings(); } catch { /* defaults */ }
    loading = false;
  }

  async function save() {
    saving = true;
    saveMsg = '';
    try {
      settings = await api.updateSettings(settings);
      saveMsg = 'Personality saved';
      setTimeout(() => saveMsg = '', 3000);
    } catch (e: any) {
      saveMsg = 'Failed to save: ' + (e.message || 'unknown error');
    }
    saving = false;
  }

  load();
</script>

<div class="personality-page">
  <div class="page-header">
    <h1>Personality</h1>
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
      <!-- EA Name -->
      <Card title="Assistant Name">
        <p class="card-desc">What your EA calls itself in conversations.</p>
        <label class="field">
          <input
            type="text"
            bind:value={settings.ea_name}
            placeholder="e.g. Aria, Max, Atlas"
            maxlength="64"
          />
        </label>
      </Card>

      <!-- Tone -->
      <Card title="Communication Tone">
        <p class="card-desc">How your EA communicates with you.</p>
        <div class="tone-grid">
          {#each toneOptions as opt}
            <label class="tone-option" class:selected={settings.tone === opt.value}>
              <input
                type="radio"
                name="tone"
                value={opt.value}
                checked={settings.tone === opt.value}
                onchange={() => settings.tone = opt.value}
              />
              <div class="tone-content">
                <strong>{opt.label}</strong>
                <span>{opt.description}</span>
              </div>
            </label>
          {/each}
        </div>
      </Card>

      <!-- Language -->
      <Card title="Primary Language">
        <p class="card-desc">The language your EA uses for responses.</p>
        <label class="field">
          <select bind:value={settings.language}>
            <option value={null}>-- Auto-detect --</option>
            {#each languageOptions as lang}
              <option value={lang.value}>{lang.label}</option>
            {/each}
          </select>
        </label>
      </Card>
    </div>
  {/if}
</div>

<style>
  .personality-page { display: flex; flex-direction: column; gap: var(--space-6); }
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
  .card-desc {
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
    margin-bottom: var(--space-4);
  }
  .field { display: flex; flex-direction: column; gap: var(--space-1); }
  input[type="text"], select {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    max-width: 400px;
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
  .tone-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-3);
  }
  .tone-option {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-4);
    border: 2px solid var(--color-border);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .tone-option:hover { border-color: var(--color-primary); }
  .tone-option.selected { border-color: var(--color-primary); background: #f0f6ff; }
  .tone-option input[type="radio"] { margin-top: 2px; }
  .tone-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .tone-content span {
    font-size: var(--text-sm);
    color: var(--color-text-secondary);
  }
</style>
