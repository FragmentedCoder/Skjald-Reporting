export async function checkApiHealth(fetchImpl: typeof fetch = fetch): Promise<string> {
  try {
    const response = await fetchImpl("/api/health");
    const body = await response.json();
    return body.status === "ok" ? "The API is reachable." : "Unexpected response from the API.";
  } catch {
    return "The API could not be reached.";
  }
}
