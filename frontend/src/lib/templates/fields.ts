// Field types for the Questions tab: each one's label, its settings with their
// defaults, and the names it gives expressions. The browser's half of the plug-in
// registry whose other half is backend/app/templates/fields.py; the shared examples
// (shared/templates/checks.json) hold the names to the server's.

import Calculator from "@lucide/svelte/icons/calculator";
import CalendarClock from "@lucide/svelte/icons/calendar-clock";
import Camera from "@lucide/svelte/icons/camera";
import EthernetPort from "@lucide/svelte/icons/ethernet-port";
import FileText from "@lucide/svelte/icons/file-text";
import Gauge from "@lucide/svelte/icons/gauge";
import Hash from "@lucide/svelte/icons/hash";
import Heading from "@lucide/svelte/icons/heading";
import KeyRound from "@lucide/svelte/icons/key-round";
import ListChecks from "@lucide/svelte/icons/list-checks";
import Mail from "@lucide/svelte/icons/mail";
import Network from "@lucide/svelte/icons/network";
import Paperclip from "@lucide/svelte/icons/paperclip";
import Phone from "@lucide/svelte/icons/phone";
import QrCode from "@lucide/svelte/icons/qr-code";
import Rows3 from "@lucide/svelte/icons/rows-3";
import Server from "@lucide/svelte/icons/server";
import Signature from "@lucide/svelte/icons/signature";
import SquareChevronDown from "@lucide/svelte/icons/square-chevron-down";
import Table from "@lucide/svelte/icons/table";
import Tag from "@lucide/svelte/icons/tag";
import ToggleLeft from "@lucide/svelte/icons/toggle-left";
import Type from "@lucide/svelte/icons/type";
import type { Component } from "svelte";

export type Icon = Component<{ size?: number; "aria-hidden"?: boolean | "true" }>;

export type FieldGroup = "Text" | "Choices" | "Numbers and dates" | "Technical" | "Files and signing" | "Structure";

export interface FieldType {
  label: string;
  hint: string;
  group: FieldGroup;
  icon: Icon;
  /** The settings a new question of this type starts with (the server's defaults). */
  settings: () => Record<string, unknown>;
  /** The names it adds under answers.<key>: "" for the key itself, ".score" and so on. */
  names: (settings: Record<string, unknown>) => Record<string, string>;
  /** Headings ask nothing. */
  asks: boolean;
}

const one = (type: string) => () => ({ "": type });
const RESULT_TYPES: Record<string, string> = { text: "string", number: "double", whole: "int", yes_no: "bool", date: "timestamp" };

const field = (
  label: string,
  hint: string,
  group: FieldGroup,
  icon: Icon,
  settings: () => Record<string, unknown>,
  names: FieldType["names"],
  asks = true,
): FieldType => ({ label, hint, group, icon, settings, names, asks });

const none = () => ({});
const pattern = () => ({ pattern: null, pattern_message: "" });

export const FIELD_TYPES: Record<string, FieldType> = {
  text: field("Short text", "One line", "Text", Type, () => ({ max_length: 500, ...pattern(), placeholder: "" }), one("string")),
  rich_text: field("Long text", "Paragraphs, lists and links", "Text", FileText, () => ({ max_length: 20000, snippets: true }), one("string")),
  dropdown: field("Dropdown", "Pick one from a list", "Choices", SquareChevronDown, () => ({ options: [{ value: "option_1", label: "Option 1" }, { value: "option_2", label: "Option 2" }] }), one("string")),
  multi_select: field("Multi-select", "Pick any from a list", "Choices", ListChecks, () => ({ options: [{ value: "option_1", label: "Option 1" }, { value: "option_2", label: "Option 2" }], min_selected: null, max_selected: null }), one("list<string>")),
  yes_no: field("Yes or no", "A single choice", "Choices", ToggleLeft, () => ({ yes_label: "Yes", no_label: "No" }), one("bool")),
  number: field("Number", "Scores, counts, amounts", "Numbers and dates", Hash, () => ({ whole: false, min: null, max: null, decimals: 1, unit: "" }), (s) => ({ "": s.whole ? "int" : "double" })),
  datetime: field("Date and time", "When something happened", "Numbers and dates", CalendarClock, () => ({ mode: "datetime" }), one("timestamp")),
  cvss: field("CVSS", "Vector and score, 3.1 or 4.0", "Numbers and dates", Gauge, () => ({ versions: ["3.1", "4.0"] }), () => ({ ".score": "double", ".vector": "string", ".severity": "string" })),
  calculated: field("Calculated value", "Worked out from other answers", "Numbers and dates", Calculator, () => ({ result: "text", show_in_form: true }), (s) => ({ "": RESULT_TYPES[String(s.result ?? "text")] })),
  ip: field("IP address", "IPv4 or IPv6, with or without a prefix", "Technical", Network, () => ({ versions: "any", cidr: "no" }), one("string")),
  hostname: field("Host name", "Such as srv-01.fjordvik.example", "Technical", Server, none, one("string")),
  mac: field("MAC address", "Six pairs of hex digits", "Technical", EthernetPort, none, one("string")),
  serial: field("Serial number", "Of a device or disk", "Technical", Tag, pattern, one("string")),
  email: field("Email", "An email address", "Technical", Mail, none, one("string")),
  phone: field("Phone", "A phone number", "Technical", Phone, none, one("string")),
  secret: field("Secret", "Password or key, printed partly", "Technical", KeyRound, () => ({ pdf: "partial" }), () => ({ ".filled": "bool", ".printed": "string" })),
  photo: field("Photo", "Taken or uploaded", "Files and signing", Camera, () => ({ multiple: false, max_photos: 10 }), () => ({ ".filled": "bool", ".count": "int" })),
  file: field("File", "Logs, captures and other files", "Files and signing", Paperclip, () => ({ multiple: false, max_files: 10 }), () => ({ ".filled": "bool", ".count": "int" })),
  barcode: field("Barcode or QR code", "Read from a photo", "Files and signing", QrCode, () => ({ formats: ["qr", "code128"] }), one("string")),
  signature: field("Signature pad", "Signed on screen", "Files and signing", Signature, none, () => ({ ".filled": "bool" })),
  repeating: field("Repeating group", "Rows the technician adds", "Structure", Rows3, () => ({ columns: [{ key: "value", label: "Value", type: "text", required: false, settings: FIELD_TYPES.text.settings() }], min_rows: 0, max_rows: 100 }), one("list<map<string, dyn>>")),
  table: field("Table", "Fixed rows to fill in", "Structure", Table, () => ({ rows: [{ key: "row_1", label: "Row 1" }], columns: [{ key: "value", label: "Value", type: "text", required: false, settings: FIELD_TYPES.text.settings() }] }), one("list<map<string, dyn>>")),
  heading: field("Heading", "Splits a step into parts", "Structure", Heading, none, () => ({}), false),
};

export const FIELD_GROUPS: FieldGroup[] = ["Text", "Choices", "Numbers and dates", "Technical", "Files and signing", "Structure"];

/** The types a repeating group's or table's column can have. */
export const COLUMN_TYPES = ["text", "number", "yes_no", "dropdown", "datetime", "ip", "hostname", "mac", "serial", "email", "phone"];

export function fieldType(type: string): FieldType {
  return FIELD_TYPES[type] ?? FIELD_TYPES.text;
}

/** A question's settings with the type's defaults filled in where they're missing. */
export function settingsOf(type: string, settings: Record<string, unknown>): Record<string, unknown> {
  return { ...fieldType(type).settings(), ...settings };
}
