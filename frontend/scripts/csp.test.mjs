import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { expect, test } from "vitest";
import { ANNOUNCER_STYLE_HASH } from "../vite.config.ts";

test("the CSP's announcer hash matches the installed SvelteKit", () => {
  const require = createRequire(import.meta.url);
  const kit = dirname(require.resolve("@sveltejs/kit/package.json"));
  // SvelteKit 3 keeps the announcer in its root component, attributes on separate lines.
  const source = readFileSync(join(kit, "src/runtime/components/root.svelte"), "utf8");
  const style = source.match(/id="svelte-announcer"[^>]*?style="([^"]+)"/s)?.[1];
  expect(style, "SvelteKit's announcer markup changed").toBeTruthy();

  const hash = `sha256-${createHash("sha256").update(style).digest("base64")}`;
  expect(ANNOUNCER_STYLE_HASH).toBe(hash);
});
