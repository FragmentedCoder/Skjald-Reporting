<script lang="ts">
  import type { Snippet } from "svelte";
  import darkScene from "#lib/assets/login-scene-dark.svg";
  import lightScene from "#lib/assets/login-scene-light.svg";
  import Brand from "./Brand.svelte";

  // The sign-in and setup pages: a card over a fjord scene, light or dark with the
  // page. When the theme changes (as when someone's own choice applies after their
  // password) the scenes fade across.

  let {
    heading,
    intro,
    eyebrow,
    children,
    footer,
  }: {
    heading: string;
    intro?: string;
    eyebrow?: string;
    children: Snippet;
    footer?: Snippet;
  } = $props();
</script>

<main class="page">
  <div class="scene" aria-hidden="true">
    <img class="light" src={lightScene} alt="" decoding="async" />
    <img class="dark" src={darkScene} alt="" decoding="async" />
  </div>
  <div class="card">
    <header class="brand">
      <Brand size={40} tagline />
    </header>
    <div class="heading">
      {#if eyebrow}<p class="eyebrow muted">{eyebrow}</p>{/if}
      <h1 class="title">{heading}</h1>
    </div>
    {#if intro}<p class="muted">{intro}</p>{/if}
    {@render children()}
    {#if footer}
      <footer class="footer">{@render footer()}</footer>
    {/if}
  </div>
</main>

<style>
  .page {
    position: relative;
    isolation: isolate;
    display: grid;
    place-items: center;
    min-height: 100vh;
    padding: var(--space-6) var(--space-4);
  }
  .scene {
    position: fixed;
    inset: 0;
    z-index: -1;
  }
  .scene img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: opacity 800ms ease;
  }
  /* The dark scene lies over the light one and fades in and out. */
  .scene .dark {
    opacity: 0;
  }
  :global(:root[data-theme="dark"]) .scene .dark {
    opacity: 1;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme="light"])) .scene .dark {
      opacity: 1;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .scene img {
      transition: none;
    }
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    width: 100%;
    max-width: 440px;
    padding: var(--space-8);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
    box-shadow: 0 12px 40px rgb(11 20 32 / 0.25);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .eyebrow {
    font: var(--type-overline);
    letter-spacing: var(--type-overline-tracking);
    text-transform: uppercase;
  }
  .footer {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--border);
  }
  @media (max-width: 480px) {
    .card {
      padding: var(--space-6);
    }
  }
</style>
