<script lang="ts">
  import { FONT_STACKS, pointsToCqi } from "#lib/reportStyles/look.js";
  import { colourOf, type Element, type Margins, type PageDesign, type ResolvedStyle } from "#lib/reportStyles/resolve.js";

  // One page's design on an A4 sheet, in millimetres from the top left: the elements
  // around the text (dragged with the mouse, or moved with the arrow keys once chosen:
  // 1 mm a press, 5 with Shift; with Ctrl or ⌘ the keys change the size), the margins
  // the text keeps to (dashed), and the art behind the page.
  let {
    design = $bindable(),
    style,
    margins,
    art = null,
    image,
    logos,
    company,
    selected = $bindable(null),
    readonly = false,
  }: {
    design: PageDesign;
    style: ResolvedStyle;
    margins: Margins;
    art?: string | null;
    image: (sha: string) => string | null;
    logos: { company: string | null; customer: string | null };
    company: string;
    selected?: string | null;
    readonly?: boolean;
  } = $props();

  const KIND_LABELS: Record<Element["kind"], string> = {
    text: "Text",
    logo: "Logo",
    image: "Image",
    line: "Line",
    box: "Box",
    page_number: "Page number",
    classification: "Classification",
    report_number: "Report number",
  };
  const SAMPLES: Partial<Record<Element["kind"], string>> = {
    page_number: "Page 2 of 7",
    classification: "TLP:AMBER",
    report_number: "INC-2026-0142",
  };

  let sheet = $state<HTMLElement>();
  const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), high);
  const round = (value: number) => Math.round(value * 2) / 2;

  function describe(e: Element): string {
    const what = e.kind === "text" ? `Text “${e.text || "empty"}”` : e.kind === "logo" ? `The ${e.logo}'s logo` : KIND_LABELS[e.kind];
    return `${what}, ${e.x} mm from the left and ${e.y} mm from the top, ${e.w} by ${e.h} mm`;
  }

  function move(e: Element, x: number, y: number) {
    e.x = round(clamp(x, 0, 210 - e.w));
    e.y = round(clamp(y, 0, 297 - e.h));
  }

  function size(e: Element, w: number, h: number) {
    e.w = round(clamp(w, e.kind === "line" ? 0 : 1, 210 - e.x));
    e.h = round(clamp(h, e.kind === "line" ? 0 : 1, 297 - e.y));
  }

  // Dragging an element, or its corner to resize it, a half millimetre at a time.
  function drag(event: PointerEvent, e: Element, resize: boolean) {
    selected = e.id;
    if (readonly || !sheet || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const target = event.currentTarget as HTMLElement;
    target.setPointerCapture(event.pointerId);
    const mm = 210 / sheet.getBoundingClientRect().width;
    const start = { px: event.clientX, py: event.clientY, x: e.x, y: e.y, w: e.w, h: e.h };
    const onMove = (m: PointerEvent) => {
      const dx = (m.clientX - start.px) * mm;
      const dy = (m.clientY - start.py) * mm;
      if (resize) size(e, start.w + dx, start.h + dy);
      else move(e, start.x + dx, start.y + dy);
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", onUp);
      target.removeEventListener("pointercancel", onUp);
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", onUp);
    target.addEventListener("pointercancel", onUp);
  }

  function key(event: KeyboardEvent, e: Element) {
    const steps: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const step = steps[event.key];
    if (!step || readonly) return;
    event.preventDefault();
    const by = event.shiftKey ? 5 : 1;
    if (event.ctrlKey || event.metaKey) size(e, e.w + step[0] * by, e.h + step[1] * by);
    else move(e, e.x + step[0] * by, e.y + step[1] * by);
  }

  function place(node: HTMLElement, e: Element) {
    const apply = (el: Element) => {
      const set = (name: string, value: string) => node.style.setProperty(name, value);
      set("left", `${(el.x / 210) * 100}%`);
      set("top", `${(el.y / 297) * 100}%`);
      set("width", `${(el.w / 210) * 100}%`);
      set("height", `${(el.h / 297) * 100}%`);
      set("font-family", FONT_STACKS[el.font === "heading" ? style.fonts.heading : el.font === "mono" ? "plex-mono" : style.fonts.body]);
      set("font-size", `${pointsToCqi(el.size)}cqi`);
      set("font-weight", el.weight === "bold" ? "600" : "400");
      set("color", colourOf(style, el.colour));
      set("justify-content", { left: "flex-start", center: "center", right: "flex-end" }[el.align]);
      set("background", el.kind === "box" && el.fill ? colourOf(style, el.fill) : "transparent");
      set("border", el.kind === "box" && el.stroke && el.stroke_width ? `${(el.stroke_width / 210) * 100}cqi solid ${colourOf(style, el.stroke)}` : "");
      set("border-radius", el.kind === "box" ? `${(el.radius / 210) * 100}cqi` : "");
    };
    apply(e);
    return { update: apply };
  }

  function guides(node: HTMLElement, m: Margins) {
    const apply = (v: Margins) => {
      node.style.setProperty("top", `${(v.top / 297) * 100}%`);
      node.style.setProperty("bottom", `${(v.bottom / 297) * 100}%`);
      node.style.setProperty("left", `${(v.left / 210) * 100}%`);
      node.style.setProperty("right", `${(v.right / 210) * 100}%`);
    };
    apply(m);
    return { update: apply };
  }
</script>

<div class="sheet" class:readonly bind:this={sheet} role="group" aria-label="The page, 210 by 297 mm">
  {#if art}<img class="art" src={art} alt="" />{/if}
  <div class="margins" use:guides={margins} aria-hidden="true"><span>The report's text goes here</span></div>
  <svg class="lines" viewBox="0 0 210 297" preserveAspectRatio="none" aria-hidden="true">
    {#each design.elements.filter((e) => e.kind === "line") as e (e.id)}
      <line x1={e.x} y1={e.y} x2={e.x + e.w} y2={e.y + e.h} stroke={e.stroke ? colourOf(style, e.stroke) : "transparent"} stroke-width={Math.max(e.stroke_width, 0.3)} />
    {/each}
  </svg>
  {#each design.elements as e (e.id)}
    <div
      class="el kind-{e.kind}"
      class:chosen={selected === e.id}
      use:place={e}
      role="button"
      tabindex="0"
      aria-label={describe(e)}
      aria-pressed={selected === e.id}
      onpointerdown={(event) => drag(event, e, false)}
      onkeydown={(event) => key(event, e)}
      onfocus={() => (selected = e.id)}
    >
      {#if e.kind === "logo"}
        {#if logos[e.logo]}<img src={logos[e.logo]} alt="" />{:else}<span class="placeholder">{e.logo === "company" ? company : "Customer logo"}</span>{/if}
      {:else if e.kind === "image"}
        {#if e.asset && image(e.asset)}<img src={image(e.asset)} alt="" />{:else}<span class="placeholder">Image</span>{/if}
      {:else if e.kind === "text"}
        <span>{e.text || "Text"}</span>
      {:else if SAMPLES[e.kind]}
        <span>{SAMPLES[e.kind]}</span>
      {/if}
      {#if selected === e.id && !readonly}
        <span class="handle" role="presentation" onpointerdown={(event) => drag(event, e, true)}></span>
      {/if}
    </div>
  {/each}
</div>

<style>
  .sheet {
    position: relative;
    container-type: inline-size;
    width: 100%;
    max-width: 640px;
    aspect-ratio: 210 / 297;
    overflow: hidden;
    border: 1px solid var(--border);
    background-color: #ffffff;
    /* A 5 mm grid. */
    background-image:
      linear-gradient(to right, rgb(43 93 138 / 0.07) 1px, transparent 1px),
      linear-gradient(to bottom, rgb(43 93 138 / 0.07) 1px, transparent 1px);
    background-size: calc(100% * 5 / 210) calc(100% * 5 / 297);
    touch-action: none;
  }
  .art,
  .lines {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .art {
    object-fit: fill;
  }
  .margins {
    position: absolute;
    display: grid;
    place-items: center;
    border: 1px dashed rgb(91 102 117 / 0.5);
    color: rgb(91 102 117 / 0.7);
    font-size: 1.6cqi;
    pointer-events: none;
  }
  .el {
    position: absolute;
    display: flex;
    align-items: center;
    min-width: 4px;
    min-height: 4px;
    overflow: visible;
    line-height: 1.2;
    white-space: nowrap;
    outline: 1px dashed rgb(43 93 138 / 0.35);
    cursor: move;
  }
  .readonly .el {
    cursor: default;
  }
  .el.kind-line {
    outline-style: dotted;
  }
  .el.chosen,
  .el:focus-visible {
    outline: 2px solid var(--link);
    z-index: 1;
  }
  .el > span:not(.handle),
  .el img {
    overflow: hidden;
  }
  .el img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    pointer-events: none;
  }
  .placeholder {
    padding: 0 0.4em;
    color: #5b6675;
  }
  .handle {
    position: absolute;
    right: -6px;
    bottom: -6px;
    width: 12px;
    height: 12px;
    border: 2px solid var(--link);
    border-radius: 2px;
    background: #ffffff;
    cursor: nwse-resize;
  }
</style>
