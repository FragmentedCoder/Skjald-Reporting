<script lang="ts">
  import { onMount } from "svelte";
  import { checkApiHealth } from "$lib/health";

  let status: string = "checking…";

  onMount(async () => {
    status = await checkApiHealth();
  });
</script>

<main>
  <h1>Skjald</h1>
  <p>{status}</p>
</main>
