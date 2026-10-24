import { describe, expect, it, vi } from "vitest";
import { checkApiHealth } from "./health";

function fakeFetch(body: unknown): typeof fetch {
  return vi.fn().mockResolvedValue({ json: () => Promise.resolve(body) }) as unknown as typeof fetch;
}

describe("checkApiHealth", () => {
  it("reports reachable when the API answers ok", async () => {
    expect(await checkApiHealth(fakeFetch({ status: "ok" }))).toBe("The API is reachable.");
  });

  it("reports an unexpected response otherwise", async () => {
    expect(await checkApiHealth(fakeFetch({ status: "down" }))).toBe(
      "Unexpected response from the API.",
    );
  });

  it("reports unreachable when the fetch throws", async () => {
    const throwingFetch = vi.fn().mockRejectedValue(new Error("network")) as unknown as typeof fetch;
    expect(await checkApiHealth(throwingFetch)).toBe("The API could not be reached.");
  });
});
