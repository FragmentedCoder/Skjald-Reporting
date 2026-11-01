<script lang="ts">
  import { fieldType, typeCode } from "#lib/templates/fields.js";

  // A field type's two-letter shorthand, such as YN for yes or no. Beside the type's
  // name it says nothing more, so screen readers skip it.
  let { type }: { type: string } = $props();
</script>

<span class="type-code" title={fieldType(type).label} aria-hidden="true">{typeCode(type)}</span>

<style>
  .type-code {
    display: inline-block;
    flex: none;
    min-width: 2.6em;
    padding: 0 4px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    line-height: 16px;
    letter-spacing: 0.04em;
    text-align: center;
    vertical-align: 1px;
  }
</style>
