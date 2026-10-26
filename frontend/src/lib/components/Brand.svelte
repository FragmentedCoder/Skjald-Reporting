<script lang="ts">
  import { branding } from "#lib/branding.svelte.js";
  import Mark from "./Mark.svelte";

  // The company's logo and site name when an Administrator set them, else Skjald's;
  // the version, when given, beside the name.
  let {
    size = 32,
    tagline = false,
    version = null,
  }: { size?: number; tagline?: boolean; version?: string | null } = $props();

  const look = $derived(branding.current);
</script>

<span class="brand">
  {#if look.logo_url}
    <img class="logo" src={look.logo_url} alt="" height={size} />
  {:else}
    <Mark {size} />
  {/if}
  <span class="names">
    <span class="name-line">
      <span class="wordmark">{look.site_name}</span>
      {#if version}<span class="version small muted" title="Skjald {version}">{version}</span>{/if}
    </span>
    {#if tagline && look.tagline}<span class="tagline small muted">{look.tagline}</span>{/if}
  </span>
</span>

<style>
  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
  }
  .logo {
    flex: none;
    width: auto;
    max-width: 160px;
    object-fit: contain;
  }
  .names {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .name-line {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
  }
  .wordmark,
  .version {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .wordmark {
    font: var(--type-subheading);
  }
  /* A long build name (a commit past a release) gives way before the site name. */
  .version {
    flex-shrink: 4;
    min-width: 3ch;
  }
</style>
