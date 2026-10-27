<script lang="ts">
  import { onMount } from "svelte";

  // A signature drawn on screen with a finger, pen or mouse; kept as a PNG data URL.
  let { value = $bindable(), label }: { value: string | null; label: string } = $props();

  let canvas = $state<HTMLCanvasElement>();
  let drawing = false;

  onMount(() => {
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.lineWidth = 2;
    context.lineCap = "round";
    context.strokeStyle = "#0F1B2D";
    if (value) {
      const image = new Image();
      image.onload = () => context.drawImage(image, 0, 0);
      image.src = value;
    }
  });

  function point(event: PointerEvent): [number, number] {
    const box = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect();
    return [((event.clientX - box.left) / box.width) * 600, ((event.clientY - box.top) / box.height) * 200];
  }

  function down(event: PointerEvent) {
    const context = canvas?.getContext("2d");
    if (!context) return;
    drawing = true;
    canvas?.setPointerCapture(event.pointerId);
    context.beginPath();
    context.moveTo(...point(event));
  }

  function move(event: PointerEvent) {
    if (!drawing) return;
    const context = canvas?.getContext("2d");
    context?.lineTo(...point(event));
    context?.stroke();
  }

  function up() {
    if (!drawing) return;
    drawing = false;
    value = canvas?.toDataURL("image/png") ?? null;
  }

  function clear() {
    canvas?.getContext("2d")?.clearRect(0, 0, 600, 200);
    value = null;
  }
</script>

<div class="pad">
  <canvas bind:this={canvas} width="600" height="200" aria-label={label} onpointerdown={down} onpointermove={move} onpointerup={up} onpointerleave={up}></canvas>
  <button class="link-button small" type="button" onclick={clear}>Clear</button>
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
