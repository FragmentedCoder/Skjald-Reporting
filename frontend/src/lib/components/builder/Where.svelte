<script lang="ts">
  // Who sees something in the builder: Form (the technician, filling in), PDF (the
  // customer) or Builder only. Every element is labelled (docs/architecture.md).
  let { form = false, pdf = false, builder = false }: { form?: boolean; pdf?: boolean; builder?: boolean } = $props();
</script>

<span class="where">
  {#if form}<span class="tag form">Form</span>{/if}
  {#if pdf}<span class="tag pdf">PDF</span>{/if}
  {#if builder}<span class="tag builder">Builder only</span>{/if}
</span>

<style>
  .where {
    display: inline-flex;
    flex-wrap: wrap;
    gap: var(--space-1);
  }
  .tag {
    padding: 0 8px;
    border-radius: var(--radius-pill);
    font-size: 12px;
    font-weight: 600;
    line-height: 20px;
    white-space: nowrap;
  }
  .form {
    background: var(--info-bg);
    color: var(--info-text);
  }
  .pdf {
    background: var(--ok-bg);
    color: var(--ok-text);
  }
  .builder {
    background: var(--surface-subtle);
    color: var(--text-muted);
  }
</style>
