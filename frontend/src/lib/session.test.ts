import { describe, expect, it } from "vitest";
import { placeFor, type SessionInfo } from "./session.svelte";

function sessionIn(second_factor: SessionInfo["second_factor"]): SessionInfo {
  return {
    user: { id: 1, username: "astrid", display_name: "Astrid Fjeld", roles: [] },
    second_factor,
    methods: [],
    csrf_token: "t",
    expires_at: "2026-10-24T12:00:00Z",
  };
}

describe("placeFor", () => {
  it.each([
    [null, "/sign-in"],
    [sessionIn("enrol"), "/sign-in/set-up"],
    [sessionIn("verify"), "/sign-in/verify"],
    [sessionIn("done"), "/"],
  ])("sends %o to %s", (info, place) => {
    expect(placeFor(info, false)).toBe(place);
  });

  it("sends everyone to the setup wizard until setup is finished", () => {
    for (const info of [null, sessionIn("enrol"), sessionIn("done")]) {
      expect(placeFor(info, true)).toBe("/setup");
    }
  });
});
