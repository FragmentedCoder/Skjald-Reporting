<script lang="ts">
  // A whole number within limits, such as the longest answer a question takes. Only a
  // number within them is kept: while the field is empty or holds something else the
  // value stays as it was (so emptying the field to type another number doesn't put
  // the default back under the cursor), and leaving the field shows what's kept.
  let { value = $bindable(), min, max, id, label, optional = false, narrow = false }: {
    value: number | null;
    min: number;
    max: number;
    id?: string;
    label?: string;
    /** Whether the field can be left empty, for no limit. */
    optional?: boolean;
    narrow?: boolean;
  } = $props();

  function typed(text: string) {
    if (text.trim() === "") {
      if (optional) value = null;
      return;
    }
    const n = Number(text);
    if (Number.isInteger(n) && n >= min && n <= max) value = n;
  }

  // What's left in the field when it's left: the nearest number within the limits.
  function left(field: HTMLInputElement) {
    const n = Number(field.value);
    if (field.value.trim() !== "" && Number.isFinite(n)) value = Math.min(max, Math.max(min, Math.round(n)));
    field.value = value === null ? "" : String(value);
  }
</script>

<input {id} class="input" class:narrow type="number" step="1" {min} {max} aria-label={label} value={value ?? ""}
  oninput={(e) => typed(e.currentTarget.value)} onchange={(e) => left(e.currentTarget)} onblur={(e) => left(e.currentTarget)} />

<style>
  .narrow {
    max-width: 140px;
  }
</style>
