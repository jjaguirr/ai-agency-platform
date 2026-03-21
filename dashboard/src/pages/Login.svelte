<script lang="ts">
  import { login } from '../lib/auth/store';
  import { navigate } from '../lib/router';
  import { ApiRequestError } from '../lib/api/client';

  let customerIdValue = $state('');
  let secretValue = $state('');
  let error = $state('');
  let loading = $state(false);

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = '';
    loading = true;
    try {
      await login(customerIdValue, secretValue);
      navigate('/overview');
    } catch (err) {
      if (err instanceof ApiRequestError) {
        error = err.error.detail;
      } else {
        error = 'Connection failed. Is the API running?';
      }
    } finally {
      loading = false;
    }
  }
</script>

<div class="login-page">
  <div class="login-card">
    <h1>EA Dashboard</h1>
    <p class="subtitle">Sign in with your customer credentials</p>

    <form onsubmit={handleSubmit}>
      {#if error}
        <div class="error-msg">{error}</div>
      {/if}

      <label class="field">
        <span class="label">Customer ID</span>
        <input
          type="text"
          bind:value={customerIdValue}
          placeholder="cust_example"
          required
          autocomplete="username"
        />
      </label>

      <label class="field">
        <span class="label">Secret</span>
        <input
          type="password"
          bind:value={secretValue}
          placeholder="Pre-shared key"
          required
          autocomplete="current-password"
        />
      </label>

      <button type="submit" class="btn-primary" disabled={loading}>
        {loading ? 'Signing in...' : 'Sign in'}
      </button>
    </form>

    <p class="note">
      <!-- MVP bootstrap auth: customer_id + pre-shared key.
           Real OAuth integration comes in a later task. -->
      Contact your administrator for credentials.
    </p>
  </div>
</div>

<style>
  .login-page {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg);
  }
  .login-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-8);
    width: 100%;
    max-width: 400px;
    box-shadow: var(--shadow-md);
  }
  h1 {
    text-align: center;
    margin-bottom: var(--space-1);
  }
  .subtitle {
    text-align: center;
    color: var(--color-text-secondary);
    font-size: var(--text-sm);
    margin-bottom: var(--space-6);
  }
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .label {
    font-size: var(--text-sm);
    font-weight: 500;
  }
  input {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    font-size: var(--text-base);
  }
  input:focus {
    outline: none;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.15);
  }
  .btn-primary {
    background: var(--color-primary);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    padding: var(--space-2) var(--space-4);
    font-weight: 500;
    cursor: pointer;
    margin-top: var(--space-2);
  }
  .btn-primary:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }
  .btn-primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .error-msg {
    background: #f8d7da;
    color: #842029;
    border: 1px solid #f5c2c7;
    border-radius: var(--radius);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
  }
  .note {
    text-align: center;
    font-size: var(--text-xs);
    color: var(--color-text-secondary);
    margin-top: var(--space-4);
  }
</style>
