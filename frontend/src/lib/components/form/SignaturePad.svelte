<script lang="ts">
  import { drawn, PAD, type Drawn } from "#lib/templates/signature.js";

  // A signature drawn on screen with a finger, pen or mouse; kept as its strokes
  // (templates/signature.ts), which the PDF draws as lines.
  let { value = $bindable(), label }: { value: Drawn | null; label: string } = $props();

  let canvas = $state<HTMLCanvasElement>();
  let stroke: number[] | null = null;

  function pen(): CanvasRenderingContext2D | null {
    const context = canvas?.getContext("2d") ?? null;
    if (context) Object.assign(context, { lineWidth: 2, lineCap: "round", lineJoin: "round", strokeStyle: "#0F1B2D" });
    return context;
  }

  // What's kept is drawn again whenever it changes from elsewhere: on coming back to
  // the step, or when the answers are cleared.
  $effect(() => {
    const strokes = drawn(value) ?? [];
    const context = pen();
    if (!context || stroke) return;
    context.clearRect(0, 0, PAD.width, PAD.height);
    for (const points of strokes) {
      context.beginPath();
      context.moveTo(points[0], points[1]);
      for (let i = 2; i < points.length; i += 2) context.lineTo(points[i], points[i + 1]);
      if (points.length === 2) context.lineTo(points[0] + 0.1, points[1]);
      context.stroke();
    }
  });

  function point(event: PointerEvent): [number, number] {
    const box = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect();
    const at = (n: number) => Math.round(n * 10) / 10;
    return [at(((event.clientX - box.left) / box.width) * PAD.width), at(((event.clientY - box.top) / box.height) * PAD.height)];
  }

  function down(event: PointerEvent) {
    const context = pen();
    if (!context) return;
    canvas?.setPointerCapture(event.pointerId);
    stroke = point(event);
    context.beginPath();
    context.moveTo(stroke[0], stroke[1]);
  }

  function move(event: PointerEvent) {
    if (!stroke) return;
    const [x, y] = point(event);
    stroke.push(x, y);
    const context = pen();
    context?.lineTo(x, y);
    context?.stroke();
  }

  function up() {
    if (!stroke) return;
    const done = stroke;
    stroke = null;
    value = { strokes: [...(drawn(value) ?? []), done] };
  }
</script>

<div class="pad">
  <canvas bind:this={canvas} width={PAD.width} height={PAD.height} aria-label={label} onpointerdown={down} onpointermove={move} onpointerup={up} onpointerleave={up}></canvas>
  <button class="link-button small" type="button" onclick={() => (value = null)}>Clear</button>
</div>

<style>
  .pad {
    display: grid;
    gap: var(--space-1);
  }
  canvas {
    width: 100%;
    max-width: 420px;
    aspect-ratio: 3 / 1;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: #ffffff;
    touch-action: none;
  }
  button {
    justify-self: start;
  }
</style>
