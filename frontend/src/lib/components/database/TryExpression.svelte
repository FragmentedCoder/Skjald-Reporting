<script lang="ts">
  import { onDestroy } from "svelte";
  import { CelClient } from "#lib/cel/client.js";
  import { DEFAULT_ZONE, human } from "#lib/cel/engine.js";
  import type { Job } from "#lib/cel/jobs.js";
  import type { Table } from "#lib/cel/library.js";
  import { shown } from "#lib/templates/nameGroups.js";
  import { printValue } from "#lib/templates/preview.js";
  import { readTyped } from "#lib/templates/text.js";

  // A box to try an expression, checked and worked out as rules and text in {{ }} are,
  // on the sample values given. It takes an expression as rules have it, the same in
  // {{ }} as the lists show names, or text with names in {{ }}, which it prints as a
  // text block would. It runs in the expression worker, with its time limit.
  let { declarations, values, language = "en", tables = {}, about, id = "try-expression" }: {
    declarations: Record<string, string>;
    values: Record<string, unknown>;
    language?: "en" | "da";
    tables?: Record<string, Table>;
    /** What it's worked out on, said under the title. */
    about: string;
    id?: string;
  } = $props();

  const worker = new CelClient();
  onDestroy(() => worker.close());

  let trying = $state('report.number + " for " + customer.name');
  let tried = $state<{ ok: boolean; text: string }>({ ok: true, text: "" });
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const typed = trying;
    // Plain copies: the worker can't be sent the app's live state.
    const declared = $state.snapshot(declarations);
    const shared = $state.snapshot(tables);
    const setup = { key: `${JSON.stringify(declared)}|${language}|${JSON.stringify(shared)}`, declarations: declared, options: { language, tables: shared } };
    const now = $state.snapshot(values) as Record<string, unknown>;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const read = readTyped(typed);
      if ("unclosed" in read) {
        tried = { ok: false, text: "Close the name with }}." };
      } else if ("expr" in read) {
        if (!read.expr) {
          tried = { ok: true, text: "" };
          return;
        }
        const [checked, result] = await worker.run(setup, now, [{ kind: "check", expr: read.expr }, { kind: "evaluate", expr: read.expr }]);
        if (!checked.ok) tried = { ok: false, text: checked.message };
        else if (!result.ok) tried = { ok: false, text: result.message };
        else tried = { ok: true, text: `${shown(result.value)}, which is ${human(String(checked.value))}` };
      } else {
        // Each name in {{ }}: checked, then worked out; the first that fails says why.
        const exprs = read.parts.map((p) => p.expr).filter(Boolean);
        const results = await worker.run(setup, now, exprs.flatMap((expr): Job[] => [{ kind: "check", expr }, { kind: "evaluate", expr }]));
        const failed = results.findIndex((r) => !r.ok);
        if (failed >= 0) {
          const result = results[failed];
          tried = { ok: false, text: `In {{${exprs[Math.floor(failed / 2)]}}}: ${result.ok ? "" : result.message}` };
          return;
        }
        let out = "";
        let last = 0;
        let n = 0;
        for (const part of read.parts) {
          out += read.text.slice(last, part.start);
          if (part.expr) {
            const result = results[n * 2 + 1];
            out += result.ok ? printValue(result.value, language, DEFAULT_ZONE) : "";
            n += 1;
          }
          last = part.end;
        }
        tried = { ok: true, text: `Prints: ${out + read.text.slice(last)}` };
      }
    }, 200);
  });
</script>

<div class="try">
  <p class="small muted">{about}</p>
  <label class="visually-hidden" for={id}>Expression</label>
  <textarea {id} class="input mono" rows="2" spellcheck="false" bind:value={trying}></textarea>
  <p class="result" class:error={!tried.ok} role="status">{tried.text}</p>
</div>

<style>
  .try {
    display: grid;
    gap: var(--space-2);
  }
  .try p {
    margin: 0;
  }
  textarea {
    width: 100%;
    font-size: 13px;
  }
  .result {
    min-height: 1.5em;
    font-family: var(--font-mono);
    font-size: 13px;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  .error {
    color: var(--critical-text);
    font-family: inherit;
  }
</style>
