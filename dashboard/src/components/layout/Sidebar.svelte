<script lang="ts">
  import { location } from '../../lib/router';

  const navItems = [
    { path: '/overview', label: 'Overview', icon: '~' },
    { path: '/conversations', label: 'Conversations', icon: '#' },
    { path: '/configuration', label: 'Configuration', icon: '*' },
    { path: '/personality', label: 'Personality', icon: '@' },
  ];
</script>

<nav class="sidebar">
  <div class="brand">EA Dashboard</div>
  <ul class="nav-list">
    {#each navItems as item}
      <li>
        <a
          href="#{ item.path }"
          class="nav-link"
          class:active={$location.startsWith(item.path)}
        >
          <span class="nav-icon">{item.icon}</span>
          <span class="nav-label">{item.label}</span>
        </a>
      </li>
    {/each}
  </ul>
</nav>

<style>
  .sidebar {
    width: var(--sidebar-width);
    background: var(--color-surface);
    border-right: 1px solid var(--color-border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .brand {
    padding: var(--space-4) var(--space-5);
    font-size: var(--text-lg);
    font-weight: 700;
    border-bottom: 1px solid var(--color-border);
    height: var(--header-height);
    display: flex;
    align-items: center;
  }
  .nav-list {
    list-style: none;
    padding: var(--space-3);
  }
  .nav-link {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    color: var(--color-text-secondary);
    text-decoration: none;
    font-size: var(--text-sm);
    transition: background 0.15s, color 0.15s;
  }
  .nav-link:hover {
    background: var(--color-bg);
    color: var(--color-text);
    text-decoration: none;
  }
  .nav-link.active {
    background: #e7f1ff;
    color: var(--color-primary);
    font-weight: 500;
  }
  .nav-icon {
    width: 20px;
    text-align: center;
    font-weight: 700;
  }

  @media (max-width: 768px) {
    .sidebar { width: 60px; }
    .brand { font-size: var(--text-sm); padding: var(--space-2); justify-content: center; }
    .nav-label { display: none; }
    .nav-link { justify-content: center; }
  }
</style>
