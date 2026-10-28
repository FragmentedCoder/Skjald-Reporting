import { defineConfig, devices } from "@playwright/test";

// Runs against a deployed stack (Caddy in front), not a dev server: the session
// cookie is Secure and __Host- prefixed, and passkeys need a real HTTPS origin.
// See e2e/run.sh.
const LATER = /(styles|custom-fields|template-files)\.spec\.ts/;

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e-results",
  workers: 1, // the tests share one server and one database
  reporter: [["list"]],
  use: {
    baseURL: process.env.SKJALD_URL ?? "https://localhost",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [
    // A fresh install sends every page to the setup wizard, so it runs first.
    { name: "setup", testMatch: /setup\.spec\.ts/ },
    { name: "chromium", testIgnore: [/setup\.spec\.ts/, LATER], dependencies: ["setup"] },
    // These leave customers and templates behind, which the empty lists the others
    // start from don't expect: they run once the others are done.
    { name: "later", testMatch: LATER, dependencies: ["chromium"] },
  ],
});
