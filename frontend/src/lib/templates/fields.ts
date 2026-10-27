// Field types for the Questions tab: each one's label, its settings with their
// defaults, and the names it gives expressions. Plain data, so the expression worker
// can use it too; the icons are in fieldIcons.ts. The browser's half of the plug-in
// registry whose other half is backend/app/templates/fields.py; the shared examples
// (shared/templates/checks.json) hold the names to the server's.

export type FieldGroup = "Text" | "Choices" | "Numbers and dates" | "Technical" | "Files and signing" | "Structure";

export interface FieldType {
  label: string;
  hint: string;
  group: FieldGroup;
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
  settings: () => Record<string, unknown>,
  names: FieldType["names"],
  asks = true,
): FieldType => ({ label, hint, group, settings, names, asks });

const none = () => ({});
const pattern = () => ({ pattern: null, pattern_message: "" });

export const FIELD_TYPES: Record<string, FieldType> = {
  text: field("Short text", "One line", "Text", () => ({ max_length: 500, ...pattern(), placeholder: "" }), one("string")),
  rich_text: field("Long text", "Paragraphs, lists and links", "Text", () => ({ max_length: 20000, snippets: true }), one("string")),
  dropdown: field("Dropdown", "Pick one from a list", "Choices", () => ({ options: [{ value: "option_1", label: "Option 1" }, { value: "option_2", label: "Option 2" }] }), one("string")),
  multi_select: field("Multi-select", "Pick any from a list", "Choices", () => ({ options: [{ value: "option_1", label: "Option 1" }, { value: "option_2", label: "Option 2" }], min_selected: null, max_selected: null }), one("list<string>")),
  yes_no: field("Yes or no", "A single choice", "Choices", () => ({ yes_label: "Yes", no_label: "No" }), one("bool")),
  number: field("Number", "Scores, counts, amounts", "Numbers and dates", () => ({ whole: false, min: null, max: null, decimals: 1, unit: "" }), (s) => ({ "": s.whole ? "int" : "double" })),
  datetime: field("Date and time", "When something happened", "Numbers and dates", () => ({ mode: "datetime" }), one("timestamp")),
  cvss: field("CVSS", "Vector and score, 3.1 or 4.0", "Numbers and dates", () => ({ versions: ["3.1", "4.0"] }), () => ({ ".score": "double", ".vector": "string", ".severity": "string" })),
  calculated: field("Calculated value", "Worked out from other answers", "Numbers and dates", () => ({ result: "text", show_in_form: true }), (s) => ({ "": RESULT_TYPES[String(s.result ?? "text")] })),
  ip: field("IP address", "IPv4 or IPv6, with or without a prefix", "Technical", () => ({ versions: "any", cidr: "no" }), one("string")),
  hostname: field("Host name", "Such as srv-01.fjordvik.example", "Technical", none, one("string")),
  mac: field("MAC address", "Six pairs of hex digits", "Technical", none, one("string")),
  serial: field("Serial number", "Of a device or disk", "Technical", pattern, one("string")),
  email: field("Email", "An email address", "Technical", none, one("string")),
  phone: field("Phone", "A phone number", "Technical", none, one("string")),
  secret: field("Secret", "Password or key, printed partly", "Technical", () => ({ pdf: "partial" }), () => ({ ".filled": "bool", ".printed": "string" })),
  photo: field("Photo", "Taken or uploaded", "Files and signing", () => ({ multiple: false, max_photos: 10 }), () => ({ ".filled": "bool", ".count": "int" })),
  file: field("File", "Logs, captures and other files", "Files and signing", () => ({ multiple: false, max_files: 10 }), () => ({ ".filled": "bool", ".count": "int" })),
  barcode: field("Barcode or QR code", "Read from a photo", "Files and signing", () => ({ formats: ["qr", "code128"] }), one("string")),
  signature: field("Signature pad", "Signed on screen", "Files and signing", none, () => ({ ".filled": "bool" })),
  repeating: field("Repeating group", "Rows the technician adds", "Structure", () => ({ columns: [{ key: "value", label: "Value", type: "text", required: false, settings: FIELD_TYPES.text.settings() }], min_rows: 0, max_rows: 100 }), one("list<map<string, dyn>>")),
  table: field("Table", "Fixed rows to fill in", "Structure", () => ({ rows: [{ key: "row_1", label: "Row 1" }], columns: [{ key: "value", label: "Value", type: "text", required: false, settings: FIELD_TYPES.text.settings() }] }), one("list<map<string, dyn>>")),
  heading: field("Heading", "Splits a step into parts", "Structure", none, () => ({}), false),
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
