<script lang="ts">
  import { route, navigate, type Route } from "./lib/router";
  import { token, customerId, clearSession } from "./lib/auth";

  import Login from "./pages/Login.svelte";
  import Overview from "./pages/Overview.svelte";
  import Configuration from "./pages/Configuration.svelte";
  import History from "./pages/History.svelte";
  import Personality from "./pages/Personality.svelte";

  // Auth guard: any route other than login requires a token.
  // Reactive — if token clears (401 handler in api.ts), we bounce.
  $: if ($token === null && $route !== "login") {
    navigate("login");
  }
  $: if ($token !== null && $route === "login") {
    navigate("overview");
  }

  const nav: { route: Route; label: string }[] = [
    { route: "overview", label: "Overview" },
    { route: "configuration", label: "Configuration" },
    { route: "history", label: "Conversations" },
    { route: "personality", label: "Personality" },
  ];

  function logout() {
    clearSession();
    navigate("login");
  }
</script>

{#if $token === null}
  <Login />
{:else}
  <div class="app-shell">
    <aside class="sidebar">
      <hgroup>
        <h4>EA Dashboard</h4>
        <small class="muted">{$customerId}</small>
      </hgroup>
      <nav>
        {#each nav as item}
          <a href="#/{item.route}" class:active={$route === item.route}>
            {item.label}
          </a>
        {/each}
      </nav>
      <hr />
      <button class="secondary outline" on:click={logout}>Sign out</button>
    </aside>

    <main class="content">
      {#if $route === "overview"}
        <Overview />
      {:else if $route === "configuration"}
        <Configuration />
      {:else if $route === "history"}
        <History />
      {:else if $route === "personality"}
        <Personality />
      {/if}
    </main>
  </div>
{/if}
