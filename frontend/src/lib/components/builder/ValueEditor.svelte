<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import type { Choice, NameEntry } from "#lib/templates/catalogue.js";
  import { OPS, type Condition, type Group, type Shape, type ValueRule } from "#lib/templates/rules.js";
  import ConditionEditor from "./ConditionEditor.svelte";
  import LiteralInput from "./LiteralInput.svelte";

  // A value worked out by rules: always the same, IF / ELSE IF / ELSE, or SWITCH on one
  // answer's value.
  let { rule = $bindable(), result, entries, choices, label = "Value" }: {
    rule: ValueRule;
    result: Shape;
    entries: NameEntry[];
    /** Values to pick from, such as a callout's tones. */
    choices?: Choice[];
    label?: string;
  } = $props();

  const switchable = $derived(entries.filter((e) => e.shape === "text" || e.shape === "whole"));
  const switched = $derived.by(() => {
    const current = rule;
    return current.kind === "switch" ? entries.find((e) => e.name === current.name) : undefined;
  });
  const resultCanSwitch = $derived(result === "text" || result === "number" || result === "whole");

  const asGroup = (c: Condition): Group =>
    c.kind === "all" || c.kind === "any" || c.kind === "one" ? c : { kind: "all", items: [c] };

  function blankCondition(): Group {
    const first = entries.find((e) => e.group === "Answers" && e.shape !== "other") ?? entries[0];
    return { kind: "all", items: [{ kind: "compare", name: first?.name ?? "", op: OPS[first?.shape ?? "text"][0]?.op ?? "eq" }] };
  }

  function setKind(kind: ValueRule["kind"]) {
    const keep = rule.kind === "fixed" ? rule.value : rule.otherwise;
    if (kind === "fixed") rule = { kind, value: keep };
    else if (kind === "if") rule = { kind, branches: [{ when: blankCondition(), value: keep }], otherwise: keep };
    else rule = { kind, name: switchable[0]?.name ?? "", cases: [{ match: "", value: keep }], otherwise: keep };
  }
</script>

<div class="value-rule">
  <select class="input kind" aria-label="{label}: how it's worked out" value={rule.kind} onchange={(e) => setKind(e.currentTarget.value as ValueRule["kind"])}>
    <option value="fixed">Always the same</option>
    <option value="if">By conditions (IF / ELSE)</option>
    {#if resultCanSwitch && switchable.length}<option value="switch">By one answer (SWITCH)</option>{/if}
  </select>

  {#if rule.kind === "fixed"}
    <LiteralInput bind:value={rule.value} shape={result} {choices} label={label} />
  {:else if rule.kind === "if"}
    {#each rule.branches as branch, index (index)}
      <div class="branch">
        <div class="branch-head">
          <span class="keyword">{index === 0 ? "If" : "Else if"}</span>
          {#if rule.branches.length > 1}
            <button class="mini" type="button" aria-label="Remove {index === 0 ? 'the IF' : `ELSE IF ${index}`}" onclick={() => rule.kind === "if" && rule.branches.splice(index, 1)}><X size={14} aria-hidden="true" /></button>
          {/if}
        </div>
        <ConditionEditor bind:condition={() => asGroup(branch.when), (v) => (branch.when = v)} {entries} label="{label}, {index === 0 ? 'if' : `else if ${index}`}" />
        <div class="then">
          <span class="keyword">then</span>
          <LiteralInput bind:value={branch.value} shape={result} {choices} label="{label}, {index === 0 ? 'if' : `else if ${index}`}: then" />
        </div>
      </div>
    {/each}
    <button class="link-button small" type="button" onclick={() => rule.kind === "if" && rule.branches.push({ when: blankCondition(), value: rule.otherwise })}>
      <Plus size={14} aria-hidden="true" /> Add an ELSE IF
    </button>
    <div class="then">
      <span class="keyword">Otherwise</span>
      <LiteralInput bind:value={rule.otherwise} shape={result} {choices} label="{label}: otherwise" />
    </div>
  {:else}
    <div class="then">
      <span class="keyword">Look at</span>
      <select class="input" aria-label="{label}: the answer it depends on" bind:value={rule.name}>
        {#each switchable as e (e.name)}<option value={e.name}>{e.label}</option>{/each}
      </select>
    </div>
    {#each rule.cases as c, index (index)}
      <div class="case">
        <span class="keyword">When it's</span>
        <LiteralInput bind:value={c.match} shape={switched?.shape === "whole" ? "whole" : "text"} choices={switched?.choices} label="{label}, case {index + 1}: when" />
        <span class="keyword">give</span>
        <LiteralInput bind:value={c.value} shape={result} {choices} label="{label}, case {index + 1}: give" />
        <button class="mini" type="button" aria-label="Remove case {index + 1}" disabled={rule.cases.length === 1}
          onclick={() => rule.kind === "switch" && rule.cases.splice(index, 1)}><X size={14} aria-hidden="true" /></button>
      </div>
    {/each}
    <button class="link-button small" type="button" onclick={() => rule.kind === "switch" && rule.cases.push({ match: "", value: rule.otherwise })}>
      <Plus size={14} aria-hidden="true" /> Add a case
    </button>
    <div class="then">
      <span class="keyword">Otherwise</span>
      <LiteralInput bind:value={rule.otherwise} shape={result} {choices} label="{label}: otherwise" />
    </div>
  {/if}
</div>

<style>
  .value-rule {
    display: grid;
    gap: var(--space-2);
  }
  .branch {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }
  .branch-head,
  .then,
  .case {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }
  .branch-head {
    justify-content: space-between;
  }
  .then > :global(.input),
  .case > :global(.input) {
    flex: 1 1 120px;
  }
  .keyword {
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .mini {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .mini:disabled {
    opacity: 0.35;
  }
</style>
