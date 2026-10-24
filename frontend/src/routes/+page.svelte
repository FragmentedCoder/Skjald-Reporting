<script lang="ts">
  import { onMount } from "svelte";

  let status: string = "checking…";

  onMount(async () => {
    try {
      const response = await fetch("/api/health");
      const body = await response.json();
      status = body.status === "ok" ? "The API is reachable." : "Unexpected response from the API.";
    } catch {
      status = "The API could not be reached.";
    }
  });
</script>

<main>
  <h1>Skjald</h1>
  <p>{status}</p>
</main>
