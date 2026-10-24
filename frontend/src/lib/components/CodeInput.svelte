<script lang="ts">
  import { onMount } from "svelte";

  // A six-digit code with a line under each digit, so it's plain a code goes here.
  // One real input underneath does the typing, pasting and autofill; the digits
  // on top are only drawn.
  let {
    id,
    value = $bindable(""),
    length = 6,
    describedby,
    autofocus = false,
  }: {
    id: string;
    value?: string;
    length?: number;
    describedby?: string;
    autofocus?: boolean;
  } = $props();

  let input: HTMLInputElement;

  // So people can type the code straight away, without clicking first.
  onMount(() => {
    if (autofocus) input.focus();
  });

  const digits = $derived(value.slice(0, length).split(""));
  const active = $derived(Math.min(value.length, length - 1));
</script>

<div class="otp">
  <input
    bind:this={input}
    {id}
    class="otp-input"
    inputmode="numeric"
    autocomplete="one-time-code"
    pattern="[0-9]*"
    maxlength={length}
    required
    aria-describedby={describedby}
    bind:value={() => value, (typed) => (value = typed.replace(/\D/g, "").slice(0, length))}
  />
  <div class="slots" aria-hidden="true">
    {#each { length }, i (i)}
      <span class="slot" class:active={i === active} class:filled={i < digits.length}>
        {digits[i] ?? ""}
      </span>
    {/each}
  </div>
</div>

<style>
  .otp {
    position: relative;
    width: fit-content;
    border-radius: var(--radius-sm);
  }
  .otp:focus-within {
    outline: 2px solid var(--link);
    outline-offset: 4px;
  }
  .otp-input {
    position: absolute;
    inset: 0;
    width: 100%;
    opacity: 0;
    font-size: 16px; /* no zoom on phones */
    cursor: text;
  }
  .slots {
    display: flex;
    gap: var(--space-3);
    padding: var(--space-1) var(--space-1) 0;
  }
  .slot {
    display: grid;
    place-items: end center;
    width: 32px;
    height: 44px;
    padding-bottom: 6px;
    border-bottom: 2px solid var(--border-strong);
    font: var(--type-code);
    font-size: 24px;
    line-height: 1;
  }
  .otp:focus-within .slot.active {
    border-bottom-color: var(--link);
  }
  .slot.filled {
    border-bottom-color: var(--text);
  }
  @media (max-width: 400px) {
    .slots {
      gap: var(--space-2);
    }
    .slot {
      width: 28px;
    }
  }
</style>
