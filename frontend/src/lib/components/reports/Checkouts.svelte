<script lang="ts">
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import { dateTime } from "#lib/format.js";
  import { heldPart, type Checkout } from "#lib/reports/api.js";
  import { attempt } from "#lib/reports/attempt.js";
  import type { ReportEditor } from "#lib/reports/editor.svelte.js";
  import type { Step } from "#lib/templates/types.js";
  import { toast } from "#lib/toast.svelte.js";

  // Who has what of the report checked out, and since when. One's own are released
  // here; an Administrator can end someone else's, after being told what that does.
  // The whole report is checked out here too; a single step, in the form at that step.
  let { editor, steps }: { editor: ReportEditor; steps: Step[] } = $props();
  const uid = $props.id();

  const report = $derived(editor.report);
  const mine = $derived(editor.checkouts.filter((c) => c.mine));
  const others = $derived(editor.checkouts.filter((c) => !c.mine));
  let busy = $state(false);
  let ending = $state<Checkout | null>(null);

  async function run(action: () => Promise<unknown>, otherwise: string, done?: string) {
    busy = true;
    try {
      if ((await attempt(action, otherwise)) && done) toast(done, "ok", { key: "checkout" });
    } finally {
      busy = false;
    }
  }

  function end() {
    const checkout = ending;
    ending = null;
    if (checkout) void run(() => editor.endCheckout(checkout), "The checkout couldn't be ended.", `${checkout.holder.name}'s checkout is ended.`);
  }
</script>

{#if report}
  <section class="section" aria-labelledby="{uid}-title">
    <div class="heading-row">
      <h2 class="section-title" id="{uid}-title">Checked out</h2>
      <!-- The whole report takes the place of the steps one holds; nobody else may hold a part of it. -->
      {#if report.may_edit && !others.length && !mine.some((c) => c.step === null)}
        <button class="button button-secondary" type="button" disabled={busy}
          onclick={() => run(() => editor.checkOut(null), "The report couldn't be checked out.")}>Check out the whole report</button>
      {/if}
    </div>
    {#if editor.checkouts.length}
      <ul class="held">
        {#each editor.checkouts as checkout (checkout.id)}
          <li>
            <span id="{uid}-{checkout.id}">
              <strong>{checkout.mine ? "You" : checkout.holder.name}</strong>
              {checkout.mine ? "have" : "has"} {heldPart(checkout, steps)} since {dateTime(checkout.taken_at)}.
              {#if checkout.stale}<Pill tone="warning" text="Stale" /> <span class="muted">Nothing was saved under it since {dateTime(checkout.active_at)}.</span>{/if}
            </span>
            {#if checkout.mine}
              <button class="button button-secondary" type="button" disabled={busy} aria-describedby="{uid}-{checkout.id}"
                onclick={() => run(() => editor.release(checkout), "The checkout couldn't be released.")}>Release</button>
            {:else if report.may_break}
              <button class="button button-secondary" type="button" disabled={busy} aria-describedby="{uid}-{checkout.id}"
                onclick={() => (ending = checkout)}>End it</button>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="small muted">Nobody has this report checked out.{report.may_edit ? " To change it, check out a step in the form, or the whole report." : ""}</p>
    {/if}
  </section>
{/if}

<Dialog bind:open={() => ending !== null, (open) => { if (!open) ending = null; }} title={ending ? `End ${ending.holder.name}'s checkout` : "End the checkout"}>
  {#if ending}
    <p>
      {ending.holder.name} has {heldPart(ending, steps)} checked out. What they saved is kept; anything they typed since stays in their
      browser until they check it out again.
    </p>
    <p>{ending.holder.name} is told by email, when email is set up and Skjald has an address for them. Ending a checkout is logged.</p>
  {/if}
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (ending = null)}>Cancel</button>
    <button class="button button-primary" type="button" onclick={end}>End the checkout</button>
  {/snippet}
</Dialog>

<style>
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
  .held {
    display: grid;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .held li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-4);
  }
</style>
