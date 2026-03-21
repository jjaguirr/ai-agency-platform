<script lang="ts">
  import { login } from "../lib/api";

  let customerId = "";
  let secret = "";
  let error = "";
  let loading = false;

  async function submit() {
    error = "";
    loading = true;
    try {
      await login({ customer_id: customerId.trim(), secret });
      // setSession already called inside login(); the $token reaction
      // in App.svelte will navigate to overview.
    } catch (e) {
      error = e instanceof Error ? e.message : "Login failed";
    } finally {
      loading = false;
    }
  }
</script>

<main class="container" style="max-width: 420px; margin-top: 8vh;">
  <article>
    <hgroup>
      <h1>Sign in</h1>
      <p class="muted">EA Dashboard</p>
    </hgroup>

    <form on:submit|preventDefault={submit}>
      <label>
        Customer ID
        <input
          type="text"
          bind:value={customerId}
          autocomplete="username"
          required
          disabled={loading}
        />
      </label>
      <label>
        Secret
        <input
          type="password"
          bind:value={secret}
          autocomplete="current-password"
          required
          disabled={loading}
        />
      </label>
      {#if error}
        <small style="color: var(--pico-del-color);">{error}</small>
      {/if}
      <button type="submit" aria-busy={loading} disabled={loading}>
        Sign in
      </button>
    </form>
  </article>
</main>
