<script lang="ts">
  import Braces from "@lucide/svelte/icons/braces";
  import { tick } from "svelte";
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import { complete, matching, printable, typedName } from "#lib/templates/suggest.js";
  import NameSuggestions from "./NameSuggestions.svelte";

  // A line of text that can hold names in {{ }}: typing "{{" suggests the names that
  // match what follows it, and the { } button starts one where the caret is.
  let { value = $bindable(), entries, id, label, invalid = false, maxlength = 500 }: {
    value: string;
    entries: NameEntry[];
    id?: string;
    /** For a field with no <label> of its own. */
    label?: string;
    invalid?: boolean;
    maxlength?: number;
  } = $props();

  const uid = $props.id();
  let input = $state<HTMLInputElement>();
  let query = $state<string | null>(null);
  let active = $state(0);

  const options = $derived(query === null ? [] : matching(printable(entries), query));
  const open = $derived(options.length > 0);

  // What's typed after an unclosed "{{" before the caret, if anything.
  function look() {
    if (!input) return;
    const typed = typedName(input.value.slice(0, input.selectionStart ?? input.value.length));
    if (typed?.query !== query) active = 0;
    query = typed ? typed.query : null;
  }

  async function put(text: string, caret: number) {
    value = text;
    await tick();
    input?.focus();
    input?.setSelectionRange(caret, caret);
    look();
  }

  function pick(entry: NameEntry) {
    if (!input) return;
    const done = complete(input.value, input.selectionStart ?? input.value.length, entry.name);
    query = null;
    void put(done.text, done.caret);
  }

  function start() {
    if (!input) return;
    const caret = document.activeElement === input ? (input.selectionStart ?? value.length) : value.length;
    void put(value.slice(0, caret) + "{{" + value.slice(caret), caret + 2);
  }

  function keydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      active = (active + (event.key === "ArrowDown" ? 1 : options.length - 1)) % options.length;
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      pick(options[active]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      query = null;
    }
  }
</script>

<div class="name-input">
  <input {id} bind:this={input} class="input" {maxlength} aria-label={label} aria-invalid={invalid ? "true" : undefined}
    role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls="{uid}-names"
    aria-activedescendant={open ? `${uid}-names-${active}` : undefined}
    bind:value oninput={look} onclick={look} onkeyup={(e) => ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key) && look()}
    onkeydown={keydown} onblur={() => (query = null)} />
  <button class="start" type="button" aria-label="Insert a name" title="Insert a name" onmousedown={(e) => e.preventDefault()} onclick={start}>
    <Braces size={15} aria-hidden="true" />
  </button>
  {#if open}<NameSuggestions id="{uid}-names" {options} {active} onpick={pick} />{/if}
</div>

<style>
  .name-input {
    position: relative;
    min-width: 0;
  }
  .name-input .input {
    width: 100%;
    padding-right: 36px;
  }
  .start {
    position: absolute;
    top: 50%;
    right: 4px;
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    translate: 0 -50%;
  }
  .start:hover,
  .start:focus-visible {
    border-color: var(--border);
    color: var(--text);
  }
</style>
