<script lang="ts">
  import type { Choice } from "#lib/templates/catalogue.js";
  import type { Literal, Shape } from "#lib/templates/rules.js";

  // One value in a rule, as its kind asks: text, a number, a date, yes or no, or one
  // of a dropdown's choices.
  let { value = $bindable(), shape, choices, label }: {
    value: Literal | undefined;
    shape: Shape;
    choices?: Choice[];
    label: string;
  } = $props();
</script>

{#if choices?.length}
  <select class="input" aria-label={label} value={String(value ?? "")} onchange={(e) => (value = e.currentTarget.value)}>
    <option value="" disabled>Choose…</option>
    {#each choices as choice (choice.value)}<option value={choice.value}>{choice.label}</option>{/each}
  </select>
{:else if shape === "number" || shape === "whole"}
  <input class="input number" type="number" step={shape === "whole" ? "1" : "any"} aria-label={label}
    value={value ?? ""} oninput={(e) => (value = e.currentTarget.value === "" ? undefined : Number(e.currentTarget.value))} />
{:else if shape === "date"}
  <input class="input" type="date" aria-label={label} value={String(value ?? "")} oninput={(e) => (value = e.currentTarget.value)} />
{:else if shape === "bool"}
  <select class="input" aria-label={label} value={value ? "true" : "false"} onchange={(e) => (value = e.currentTarget.value === "true")}>
    <option value="true">Yes</option><option value="false">No</option>
  </select>
{:else}
  <input class="input" aria-label={label} value={String(value ?? "")} oninput={(e) => (value = e.currentTarget.value)} />
{/if}

<style>
  .input {
    min-width: 0;
  }
  .number {
    max-width: 120px;
  }
</style>
