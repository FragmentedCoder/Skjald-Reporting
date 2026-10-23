<script>
  // The Ansuz mark from docs/brand. On dark backgrounds the framed variant is used, so the tile edge reads.
  let {size = 28} = $props()
</script>

<svg width={size} height={size} viewBox="0 0 160 160" role="img" aria-label="Skjald">
  <rect width="160" height="160" rx="36" fill="#0F1B2D" />
  <rect class="frame" x="4" y="4" width="152" height="152" rx="33" fill="none" stroke-width="4" />
  <path d="M62 36 V124 M62 40 L98 64 M62 64 L98 88" fill="none" stroke="#C8862A" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" />
</svg>

<style>
  svg { display: block; flex: none; }
  .frame { stroke: var(--mark-frame); }
</style>
