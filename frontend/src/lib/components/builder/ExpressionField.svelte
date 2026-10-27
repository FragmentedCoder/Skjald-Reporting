<script lang="ts">
  import { Engine, ExpressionError, human } from "#lib/cel/engine.js";

  // A rule or value written in CEL, checked as it's typed against the names the
  // template can read. Empty means no rule. The visual editors (ConditionEditor,
  // ValueEditor) write the same text.
  let {
    id,
    label,
    value = $bindable(),
    engine,
    expects = null,
    hint = "",
    placeholder = "",
    rows = 2,
    problem = null,
  }: {
    id: string;
    label: string;
    value: string | null;
    engine: Engine;
    expects?: string | null;
    hint?: string;
    placeholder?: string;
    rows?: number;
    /** The server's or the template check's problem with it, if any. */
    problem?: string | null;
  } = $props();

  const live = $derived.by((): { error: string | null; type: string | null } => {
    if (!value?.trim()) return { error: null, type: null };
    try {
      const type = engine.check(value);
      if (expects && type !== "dyn" && type !== expects && !(expects === "list" && type.startsWith("list<"))) {
        return { error: `This should give ${human(expects)}, but gives ${human(type)}.`, type };
      }
      return { error: null, type };
    } catch (error) {
      return { error: error instanceof ExpressionError ? error.message : String(error), type: null };
    }
  });
  const shown = $derived(live.error ?? problem);
</script>

<div class="field expression">
  <label for={id}>{label}</label>
  <textarea {id} class="input mono" {rows} {placeholder} spellcheck="false" autocomplete="off"
    aria-invalid={shown ? "true" : undefined} aria-describedby="{id}-help"
    value={value ?? ""} oninput={(e) => (value = e.currentTarget.value === "" ? null : e.currentTarget.value)}></textarea>
  <span id="{id}-help" class="hint" class:error={shown}>
    {#if shown}{shown}{:else if live.type}Gives {human(live.type)}.{:else}{hint}{/if}
  </span>
</div>

<style>
  .expression textarea {
    min-height: 0;
    resize: vertical;
    font-size: 13px;
  }
  .error {
    color: var(--critical-text);
  }
</style>
