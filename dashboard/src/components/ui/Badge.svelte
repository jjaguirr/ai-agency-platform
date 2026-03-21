<script lang="ts">
  let { variant = 'default', label }: { variant?: 'success' | 'warning' | 'danger' | 'info' | 'default'; label: string } = $props();
</script>

<span class="badge {variant}">{label}</span>

<style>
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: var(--text-xs);
    font-weight: 500;
    line-height: 1.5;
  }
  .default { background: #e9ecef; color: #495057; }
  .success { background: #d1e7dd; color: #0f5132; }
  .warning { background: #fff3cd; color: #664d03; }
  .danger { background: #f8d7da; color: #842029; }
  .info { background: #cff4fc; color: #055160; }
</style>
