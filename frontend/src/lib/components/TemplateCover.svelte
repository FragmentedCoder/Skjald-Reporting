<script lang="ts">
  import PdfPages from "#lib/components/preview/PdfPages.svelte";
  import type { PreviewStyle } from "#lib/reportStyles/preview.svelte.js";
  import type { TemplateSummary } from "#lib/templates/api.js";
  import type { Covers } from "#lib/templates/covers.js";
  import type { Paged } from "#lib/templates/pages.js";

  // A template's first page, small, for its card: worked out once the card comes into
  // view, in the company's default style. Only a picture: the card's link opens it.
  let { template, covers, looks }: {
    template: TemplateSummary;
    /** Without it (for those who can't open templates), there's no picture. */
    covers?: Covers;
    looks: PreviewStyle;
  } = $props();

  let frame = $state<HTMLDivElement>();
  let paged = $state<Paged | null>(null);
  let progress = $state<"waiting" | "drawing" | "done">("waiting");

  $effect(() => {
    const drawer = covers;
    if (!frame || !drawer) return;
    const observer = new IntersectionObserver(async ([seen]) => {
      if (!seen.isIntersecting || progress !== "waiting") return;
      observer.disconnect();
      progress = "drawing";
      paged = await drawer.firstPage(template, looks.texts);
      progress = "done";
    }, { rootMargin: "200px" });
    observer.observe(frame);
    return () => observer.disconnect();
  });
</script>

<div class="cover" bind:this={frame} aria-hidden="true">
  {#if paged}
    <PdfPages {paged} look={looks.look(undefined)} />
  {:else}
    <div class="blank small muted">{!covers ? "No picture" : progress === "done" ? "No pages yet" : "Drawing the first page…"}</div>
  {/if}
</div>

<style>
  .cover {
    overflow: hidden;
    pointer-events: none;
  }
  .cover :global(.why) {
    display: none;
  }
  .cover :global(.paper) {
    border: 0;
  }
  .blank {
    display: grid;
    place-items: center;
    aspect-ratio: 210 / 297;
    background: var(--surface-subtle);
  }
</style>
