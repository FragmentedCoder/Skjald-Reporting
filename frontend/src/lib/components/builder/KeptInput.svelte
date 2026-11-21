<script lang="ts">
  // A field that keeps only what passes its check, such as a variable name: while
  // what's typed doesn't pass (empty, not a name, taken by another), the value stays
  // as it was and `problem` says why; leaving the field shows what's kept. So the
  // draft never holds a value the server would refuse to save.
  let { value = $bindable(), problem = $bindable(null), check, id, label, maxlength, mono = false }: {
    value: string;
    /** Why what's typed isn't kept, while it isn't. */
    problem?: string | null;
    check: (text: string) => string | null;
    id?: string;
    label?: string;
    maxlength?: number;
    mono?: boolean;
  } = $props();

  function typed(text: string) {
    problem = text === value ? null : check(text);
    if (!problem) value = text;
  }
</script>

<input {id} class="input" class:mono {maxlength} aria-label={label} aria-invalid={problem ? "true" : undefined} title={problem ?? undefined}
  spellcheck="false" autocomplete="off" {value} oninput={(e) => typed(e.currentTarget.value)}
  onblur={(e) => { e.currentTarget.value = value; problem = null; }} />
