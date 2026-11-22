import { describe, expect, it } from "vitest";
import type { Question, Step } from "#lib/templates/types.js";
import { blank, differs, held, merged, same, toSave, toSend, unsaved } from "./answers";
import type { Checkout } from "./api";

const OPTIONS = [{ value: "low", label: "Low" }, { value: "high", label: "High" }];

const question = (id: string, type: string, extra: Partial<Question> = {}): Question => ({
  id, key: id.slice(2), type, label: id, help: "", required: false, required_when: null, visible_when: null,
  default: null, valid_when: null, valid_message: "", value: null, settings: {}, ...extra,
});

const FORM: Step[] = [
  { id: "s_details", title: "Details", help: "", visible_when: null, questions: [
    question("q_title", "text"),
    // Starts as "low" by its rule.
    question("q_severity", "dropdown", { default: '"low"', settings: { options: OPTIONS } }),
    question("q_cvss", "cvss"),
  ] },
  { id: "s_access", title: "Access", help: "", visible_when: null, questions: [
    question("q_password", "secret"),
    question("q_lead", "person", { settings: { who: "team" } }),
    question("q_hosts", "repeating", { settings: { columns: [{ key: "name", label: "Name", type: "hostname" }, { key: "port", label: "Port", type: "number" }] } }),
  ] },
];

const checkout = (step: string | null, mine = true): Checkout =>
  ({ id: 1, step, holder: { id: 4, name: "Astrid Fjeld" }, taken_at: "2026-10-24T08:00:00Z", active_at: "2026-10-24T08:00:00Z", stale: false, mine });

describe("what counts as an answer", () => {
  it("reads nothing, an empty list, a CVSS answer with no vector and an unconfirmed signature as no answer", () => {
    const text = question("q", "text");
    for (const value of [null, undefined, "", [], {}]) expect(blank(text, value)).toBe(true);
    for (const value of ["x", 0, false, ["low"], { type: "doc", content: [] }]) expect(blank(text, value)).toBe(false);
    const cvss = question("q", "cvss");
    expect(blank(cvss, { vector: " ", score: 0, severity: "" })).toBe(true);
    expect(blank(cvss, { vector: "CVSS:3.1/AV:N", score: 0, severity: "" })).toBe(false);
    const signature = question("q", "signature");
    expect(blank(signature, { name: "Mette Lund", confirmed: false })).toBe(true);
    expect(blank(signature, { name: "  ", confirmed: true })).toBe(true);
    expect(blank(signature, { name: "Mette Lund", confirmed: true, at: "2026-10-24T12:00:00Z" })).toBe(false);
  });

  it("forgets an emptied answer, and keeps one that would start as something as cleared", () => {
    expect(held(FORM[0].questions[0], "")).toBeUndefined();
    expect(held(FORM[0].questions[0], "Portal")).toBe("Portal");
    expect(held(FORM[0].questions[1], null)).toBeNull();
    expect(held(FORM[0].questions[1], "high")).toBe("high");
    expect(held(question("q", "yes_no"), false)).toBe(false);
  });
});

describe("whether two answers are the same", () => {
  it("doesn't mind the order of their parts, or an empty cell that isn't written", () => {
    expect(same({ vector: "V", score: 9.8 }, { score: 9.8, vector: "V" })).toBe(true);
    expect(same([{ name: "srv-01" }], [{ name: "srv-01", port: null }])).toBe(true);
    expect(same([{ name: "srv-01" }, null], [{ name: "srv-01" }, undefined])).toBe(true);
    expect(same([{ name: "srv-01" }], [{ name: "srv-02" }])).toBe(false);
    expect(same([{ name: "srv-01" }], [{ name: "srv-01" }, { name: "srv-02" }])).toBe(false);
    expect(same(["low", "high"], ["high", "low"])).toBe(false);
    expect(same({ name: "" }, { name: null })).toBe(false);
    expect(same("12", 12)).toBe(false);
  });

  it("tells an answer cleared on purpose from one not given", () => {
    expect(differs("q", {}, {})).toBe(false);
    expect(differs("q", { q: null }, { q: null })).toBe(false);
    expect(differs("q", { q: null }, {})).toBe(true);
    expect(differs("q", {}, { q: "x" })).toBe(true);
    expect(differs("q", { q: "x" }, { q: "x" })).toBe(false);
    expect(differs("q", { q: { masked: true, printed: "So••••••rd" } }, { q: { printed: "So••••••rd", masked: true } })).toBe(false);
    expect(differs("q", { q: "Sommer2026!Fjord" }, { q: { masked: true, printed: "So••••••rd" } })).toBe(true);
  });
});

describe("what a save sends", () => {
  it("sends an empty answer as null, a picked person by ID alone, and a secret as typed", () => {
    expect(toSend(question("q", "text"), "")).toBeNull();
    expect(toSend(question("q", "text"), undefined)).toBeNull();
    expect(toSend(question("q", "multi_select"), [])).toBeNull();
    expect(toSend(question("q", "cvss"), { vector: "", score: 0, severity: "" })).toBeNull();
    expect(toSend(question("q", "person"), { id: "7", technician: true, reviewer: false, on_team: true, display_name: "Bo Berg", email: "bo@nordlys.example" }))
      .toEqual({ id: "7" });
    expect(toSend(question("q", "secret"), "Sommer2026!Fjord")).toBe("Sommer2026!Fjord");
    expect(toSend(question("q", "yes_no"), false)).toBe(false);
    expect(toSend(question("q", "number"), 0)).toBe(0);
  });

  it("sends only the answers that changed", () => {
    const kept = { q_title: "Portal brute force", q_severity: "high", q_password: { masked: true, printed: "So••••••rd" } };
    const here = { ...kept, q_title: "Portal brute force, October" };
    expect(toSave(FORM, [checkout(null)], here, kept)).toEqual({ q_title: "Portal brute force, October" });
    expect(toSave(FORM, [checkout(null)], kept, kept)).toEqual({});
    expect(unsaved(FORM, here, kept).map((c) => [c.step, c.question.id])).toEqual([["s_details", "q_title"]]);
  });

  it("sends only what's in the steps this person holds", () => {
    const kept = {};
    const here = { q_title: "Mine", q_password: "hunter2hunter2" };
    expect(toSave(FORM, [checkout("s_details")], here, kept)).toEqual({ q_title: "Mine" });
    expect(toSave(FORM, [checkout("s_access")], here, kept)).toEqual({ q_password: "hunter2hunter2" });
    // The whole report covers every step; someone else's checkout covers nothing.
    expect(toSave(FORM, [checkout(null)], here, kept)).toEqual(here);
    expect(toSave(FORM, [checkout(null, false)], here, kept)).toEqual({});
    expect(toSave(FORM, [], here, kept)).toEqual({});
  });

  it("sends an answer that was emptied as null, whether it's forgotten or kept as cleared", () => {
    const kept = { q_title: "Portal brute force", q_severity: "high" };
    // The title is forgotten here; the severity, which starts as something, is kept as cleared.
    const here = { q_severity: null };
    expect(toSave(FORM, [checkout(null)], here, kept)).toEqual({ q_title: null, q_severity: null });
    // Cleared on both sides already: nothing to send.
    expect(toSave(FORM, [checkout(null)], { q_severity: null }, { q_severity: null })).toEqual({});
  });
});

describe("taking in the report fetched again", () => {
  it("takes other people's answers, and keeps what isn't saved here", () => {
    const kept = { q_title: "Portal brute force", q_severity: "high" };
    const here = { q_title: "Portal brute force, October", q_severity: "high" };
    const fetched = { q_title: "Portal brute force", q_severity: "low", q_password: { masked: true, printed: "bo••••••ue" }, q_hosts: [{ name: "srv-01", port: 443 }] };
    expect(merged(FORM, here, kept, fetched)).toEqual({
      q_title: "Portal brute force, October",
      q_severity: "low",
      q_password: { masked: true, printed: "bo••••••ue" },
      q_hosts: [{ name: "srv-01", port: 443 }],
    });
  });

  it("drops what someone else cleared, and keeps what was cleared here", () => {
    const kept = { q_title: "Portal brute force", q_cvss: { vector: "V", score: 9.8, severity: "Critical" }, q_severity: "high" };
    // Here the title was emptied and not saved yet; someone else cleared the CVSS answer and the severity.
    const here = { q_cvss: kept.q_cvss, q_severity: "high" };
    const fetched = { q_title: "Portal brute force", q_severity: null };
    expect(merged(FORM, here, kept, fetched)).toEqual({ q_severity: null });
  });

  it("keeps the answer held here when the server's is the same, so a field isn't disturbed", () => {
    const rows = [{ name: "srv-01" }];
    const here = { q_hosts: rows };
    const next = merged(FORM, here, { q_hosts: [{ name: "srv-01", port: null }] }, { q_hosts: [{ port: null, name: "srv-01" }] });
    expect(next.q_hosts).toBe(rows);
  });
});
