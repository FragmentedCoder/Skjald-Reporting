<script lang="ts">
  // A person's picture, or their initials on a plain tile when they have none.
  let { name, url, size = 32 }: { name: string; url: string | null; size?: number } = $props();

  const initials = $derived(
    name
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => part[0])
      .filter((_, i, all) => i === 0 || i === all.length - 1)
      .join("")
      .toUpperCase(),
  );
</script>

{#if url}
  <img class="avatar" src={url} alt="" width={size} height={size} />
{:else}
  <span class="avatar initials" aria-hidden="true">
    <svg viewBox="0 0 40 40" width={size} height={size}>
      <text x="20" y="21" text-anchor="middle" dominant-baseline="middle">{initials}</text>
    </svg>
  </span>
{/if}

<style>
  .avatar {
    flex: none;
    border-radius: 50%;
    object-fit: cover;
  }
  .initials {
    display: inline-grid;
    overflow: hidden;
    background: var(--info-bg);
    color: var(--info-text);
  }
  text {
    fill: currentColor;
    font: 600 15px var(--font-sans);
  }
</style>
