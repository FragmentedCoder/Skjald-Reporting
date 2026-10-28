// Each field type's icon, for the builder's screens (fields.ts stays plain data so
// the expression worker can use it).

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

export const FIELD_ICONS: Record<string, Icon> = {
  text: Type,
  rich_text: FileText,
  dropdown: SquareChevronDown,
  multi_select: ListChecks,
  yes_no: ToggleLeft,
  number: Hash,
  datetime: CalendarClock,
  cvss: Gauge,
  calculated: Calculator,
  ip: Network,
  hostname: Server,
  mac: EthernetPort,
  serial: Tag,
  email: Mail,
  phone: Phone,
  secret: KeyRound,
  photo: Camera,
  file: Paperclip,
  barcode: QrCode,
  signature: Signature,
  repeating: Rows3,
  table: Table,
  heading: Heading,
};

export const fieldIcon = (type: string): Icon => FIELD_ICONS[type] ?? FIELD_ICONS.text;
