<div class="spinner"></div>

<style>
  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    margin: var(--space-4) auto;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
