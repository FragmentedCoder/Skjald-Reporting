// Whether an answer to a typed question is valid: the form's copy of
// backend/app/templates/answers.py, held to the same verdicts and words by
// shared/fields/cases.json. Addresses are parsed by hand, as on the server. An empty
// answer isn't checked here: whether one is needed is the question's "required".

import * as calculator from "ae-cvss-calculator";
import { RE2JS } from "re2js";

const V31_EXAMPLE = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H";
export const MESSAGES = {
  ip: "Enter an IP address, such as 198.51.100.23 or 2001:db8::5.",
  v4: "Enter an IPv4 address, such as 198.51.100.23.",
  v6: "Enter an IPv6 address, such as 2001:db8::5.",
  no_prefix: "Enter the address without a prefix such as /24.",
  prefix: "Add the prefix length, such as /24.",
  hostname: "Enter a host name, such as srv-01.fjordvik.example.",
  mac: "Enter a MAC address: six pairs of hex digits, such as 00:1A:2B:3C:4D:5E.",
  email: "Enter an email address, such as name@fjordvik.example.",
  phone: "Enter a phone number: digits, spaces and + ( ) - only.",
  cvss: `Enter a CVSS 3.1 or 4.0 vector, such as ${V31_EXAMPLE}.`,
  pattern: "This doesn't match what the template asks for.",
};

const OCTET = /^(0|[1-9][0-9]{0,2})$/;
const HEX = /^[0-9A-Fa-f]{1,4}$/;
const LABEL = /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/;
const MACS = [/^[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$/, /^[0-9A-Fa-f]{12}$/, /^[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}$/];
const LOCAL = /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$/;
const PHONE = /^\+?[0-9 ()\-.]+$/;

export function isIpv4(text: string): boolean {
  const parts = text.split(".");
  return parts.length === 4 && parts.every((p) => OCTET.test(p) && Number(p) <= 255);
}

export function isIpv6(text: string): boolean {
  const doubles = text.split("::").length - 1;
  if (doubles > 1) return false;
  let groups: string[];
  if (doubles === 1) {
    const [head, tail] = text.split("::");
    groups = [...(head ? head.split(":") : []), ...(tail ? tail.split(":") : [])];
  } else {
    groups = text.split(":");
  }
  let count = 0;
  for (const [index, group] of groups.entries()) {
    if (index === groups.length - 1 && group.includes(".")) {
      if (!isIpv4(group)) return false;
      count += 2;
    } else if (HEX.test(group)) {
      count += 1;
    } else {
      return false;
    }
  }
  return doubles === 1 ? count <= 7 : count === 8;
}

function ip(value: string, settings: Record<string, unknown>): string | null {
  const versions = settings.versions ?? "any";
  const wrong = versions === "v4" ? MESSAGES.v4 : versions === "v6" ? MESSAGES.v6 : MESSAGES.ip;
  const slash = value.indexOf("/");
  const address = slash < 0 ? value : value.slice(0, slash);
  const prefix = slash < 0 ? null : value.slice(slash + 1);
  const v4 = isIpv4(address);
  const v6 = isIpv6(address);
  if (!v4 && !v6) return wrong;
  if (prefix !== null && (!OCTET.test(prefix) || Number(prefix) > (v4 ? 32 : 128))) return wrong;
  if (versions === "v4" && !v4) return MESSAGES.v4;
  if (versions === "v6" && !v6) return MESSAGES.v6;
  const cidr = settings.cidr ?? "no";
  if (prefix !== null && cidr === "no") return MESSAGES.no_prefix;
  if (prefix === null && cidr === "required") return MESSAGES.prefix;
  return null;
}

export function isHostname(text: string): boolean {
  return text.length <= 253 && text.split(".").every((label) => label.length <= 63 && LABEL.test(label));
}

function email(value: string): boolean {
  const at = value.lastIndexOf("@");
  if (at < 0) return false;
  const local = value.slice(0, at);
  const domain = value.slice(at + 1);
  return value.length <= 254 && local.length <= 64 && LOCAL.test(local) && domain.includes(".") && isHostname(domain);
}

function phone(value: string): boolean {
  const digits = [...value].filter((c) => c >= "0" && c <= "9").length;
  return PHONE.test(value) && digits >= 4 && digits <= 20;
}

// CVSS vectors: every base metric once, and only the metrics each version has.
const CVSS31: Record<string, string> = { AV: "NALP", AC: "LH", PR: "NLH", UI: "NR", S: "UC", C: "HLN", I: "HLN", A: "HLN" };
const CVSS31_MORE: Record<string, string> = {
  E: "XUPFH", RL: "XOTWU", RC: "XURC", CR: "XLMH", IR: "XLMH", AR: "XLMH", MAV: "XNALP", MAC: "XLH", MPR: "XNLH",
  MUI: "XNR", MS: "XUC", MC: "XNLH", MI: "XNLH", MA: "XNLH",
};
const CVSS40: Record<string, string> = { AV: "NALP", AC: "LH", AT: "NP", PR: "NLH", UI: "NPA", VC: "HLN", VI: "HLN", VA: "HLN", SC: "HLN", SI: "HLN", SA: "HLN" };
const CVSS40_MORE: Record<string, string> = {
  E: "XAPU", CR: "XHML", IR: "XHML", AR: "XHML", MAV: "XNALP", MAC: "XLH", MAT: "XNP", MPR: "XNLH", MUI: "XNPA",
  MVC: "XHLN", MVI: "XHLN", MVA: "XHLN", MSC: "XHLN", MSI: "XSHLN", MSA: "XSHLN", S: "XNP", AU: "XNY", R: "XAUI",
  V: "XDC", RE: "XLMH",
};
const CVSS40_URGENCY = ["X", "Clear", "Green", "Amber", "Red"];

/** 3.1 or 4.0 for a well-formed vector, else null. */
export function cvssVersion(vector: string): "3.1" | "4.0" | null {
  for (const [version, base, more] of [["3.1", CVSS31, CVSS31_MORE], ["4.0", CVSS40, CVSS40_MORE]] as const) {
    const prefix = `CVSS:${version}/`;
    if (!vector.startsWith(prefix)) continue;
    const seen = new Map<string, string>();
    for (const part of vector.slice(prefix.length).split("/")) {
      const colon = part.indexOf(":");
      if (colon < 0) return null;
      const name = part.slice(0, colon);
      const value = part.slice(colon + 1);
      if (seen.has(name)) return null;
      if (version === "4.0" && name === "U") {
        if (!CVSS40_URGENCY.includes(value)) return null;
      } else {
        const allowed = base[name] ?? more[name];
        if (allowed === undefined || value.length !== 1 || !allowed.includes(value)) return null;
      }
      seen.set(name, value);
    }
    return Object.keys(base).every((name) => seen.has(name)) ? version : null;
  }
  return null;
}

export function severity(score: number): string {
  if (score === 0) return "None";
  if (score < 4) return "Low";
  if (score < 7) return "Medium";
  if (score < 9) return "High";
  return "Critical";
}

interface CvssLibrary {
  Cvss3P1: new (vector: string) => { calculateScores(): { base: number } };
  Cvss4P0: new (vector: string) => { calculateScores(): { overall: number } };
}
const cvss = ((calculator as unknown as { CvssCalculator?: CvssLibrary; default?: CvssLibrary }).CvssCalculator
  ?? (calculator as unknown as { default: CvssLibrary }).default) as CvssLibrary;

/** The score (3.1: the base score; 4.0: the vector's own) and its severity. */
export function cvssScore(vector: string): { score: number; severity: string } | null {
  const version = cvssVersion(vector);
  if (version === null) return null;
  const score = version === "3.1" ? new cvss.Cvss3P1(vector).calculateScores().base : new cvss.Cvss4P0(vector).calculateScores().overall;
  const rounded = Math.round(score * 10) / 10;
  return { score: rounded, severity: severity(rounded) };
}

const number = (value: number) => String(value);

/** What's wrong with the answer, or null if it's fine (or empty). */
export function checkAnswer(type: string, settings: Record<string, unknown>, value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value);
  switch (type) {
    case "ip":
      return ip(text, settings);
    case "hostname":
      return isHostname(text) ? null : MESSAGES.hostname;
    case "mac":
      return MACS.some((p) => p.test(text)) ? null : MESSAGES.mac;
    case "email":
      return email(text) ? null : MESSAGES.email;
    case "phone":
      return phone(text) ? null : MESSAGES.phone;
    case "cvss": {
      const version = cvssVersion(text);
      if (version === null) return MESSAGES.cvss;
      const allowed = (settings.versions as string[] | undefined) ?? ["3.1", "4.0"];
      return allowed.includes(version) ? null : `This template takes CVSS ${allowed[0]} vectors only.`;
    }
    case "number": {
      const n = Number(value);
      if (settings.whole && !Number.isInteger(n)) return "Enter a whole number.";
      const low = settings.min as number | null | undefined;
      const high = settings.max as number | null | undefined;
      const hasLow = low !== null && low !== undefined;
      const hasHigh = high !== null && high !== undefined;
      if (hasLow && hasHigh && (n < low || n > high)) return `Enter a number from ${number(low)} to ${number(high)}.`;
      if (hasLow && !hasHigh && n < low) return `Enter a number of at least ${number(low)}.`;
      if (hasHigh && !hasLow && n > high) return `Enter a number of at most ${number(high)}.`;
      return null;
    }
    case "text":
    case "serial": {
      const most = settings.max_length as number | undefined;
      if (most !== undefined && Array.from(text).length > most) return `Keep it to ${most} characters.`;
      const pattern = settings.pattern as string | null | undefined;
      if (pattern) {
        let matched: boolean;
        try {
          matched = RE2JS.compile(pattern).matcher(text).find();
        } catch {
          return null;
        }
        if (!matched) return (settings.pattern_message as string) || MESSAGES.pattern;
      }
      return null;
    }
    default:
      return null;
  }
}
