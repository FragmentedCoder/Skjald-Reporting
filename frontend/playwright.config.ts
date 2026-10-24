import { defineConfig, devices } from "@playwright/test";

// Runs against a deployed stack (Caddy in front), not a dev server: the session
// cookie is Secure and __Host- prefixed, and passkeys need a real HTTPS origin.
// See e2e/run.sh.
export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e-results",
  workers: 1, // the tests share one server and one database
  reporter: [["list"]],
  use: {
    baseURL: process.env.SKJALD_URL ?? "https://localhost",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
