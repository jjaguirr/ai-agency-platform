<script lang="ts">
  import { location, matchRoute, replace } from './lib/router';
  import { isAuthenticated } from './lib/auth/store';

  import Login from './pages/Login.svelte';
  import Overview from './pages/Overview.svelte';
  import Conversations from './pages/Conversations.svelte';
  import Configuration from './pages/Configuration.svelte';
  import Personality from './pages/Personality.svelte';
  import Shell from './components/layout/Shell.svelte';

  let currentPage = $state<any>(null);
  let currentParams = $state<Record<string, string>>({});
  let showShell = $state(false);

  // React to location + auth changes
  $effect(() => {
    const path = $location;
    const authed = $isAuthenticated;

    if (path === '/login') {
      currentPage = Login;
      showShell = false;
      return;
    }

    if (!authed) {
      replace('/login');
      return;
    }

    // Match routes
    let params: Record<string, string> | null;

    if (path === '/' || path === '') {
      replace('/overview');
      return;
    } else if (path === '/overview') {
      currentPage = Overview;
      currentParams = {};
    } else if ((params = matchRoute('/conversations/:id', path))) {
      currentPage = Conversations;
      currentParams = params;
    } else if (path === '/conversations') {
      currentPage = Conversations;
      currentParams = {};
    } else if (path === '/configuration') {
      currentPage = Configuration;
      currentParams = {};
    } else if (path === '/personality') {
      currentPage = Personality;
      currentParams = {};
    } else {
      replace('/overview');
      return;
    }
    showShell = true;
  });
</script>

{#if showShell && currentPage}
  <Shell page={currentPage} params={currentParams} />
{:else if currentPage}
  <Login />
{/if}
