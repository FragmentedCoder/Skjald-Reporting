// Mirrors backend/app/backup_routes.py.
import { bytes } from "./format.js";

export type BackupKind = "off" | "local" | "smb" | "s3";

export interface BackupTarget {
  kind: BackupKind;
  hour: number;
  keep_days: number;
  smb_host: string;
  smb_share: string;
  smb_path: string;
  smb_username: string;
  smb_domain: string;
  s3_endpoint: string;
  s3_bucket: string;
  s3_path: string;
  s3_region: string;
  s3_access_key_id: string;
}

export type RunKind = "backup" | "restore_test" | "backup_check";

export interface BackupRun {
  id: number;
  kind: RunKind;
  state: "queued" | "running" | "done" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  requested_by: string | null;
}

export interface BackupStatus {
  target: BackupTarget;
  smb_password_set: boolean;
  s3_secret_set: boolean;
  repository: string;
  next_backup_at: string | null;
  last_backup: BackupRun | null;
  last_restore_test: BackupRun | null;
  runs: BackupRun[];
}

export const KINDS: { kind: BackupKind; name: string; about: string }[] = [
  { kind: "smb", name: "SMB share",
    about: "A folder on a file server or NAS on your network, such as a Windows share." },
  { kind: "s3", name: "S3-compatible storage",
    about: "A bucket at Amazon S3, Backblaze B2, MinIO, Wasabi or similar." },
  { kind: "local", name: "This server",
    about: "The backup folder on this server. It doesn't survive losing the server's disk." },
  { kind: "off", name: "Off", about: "Nothing is backed up." },
];

export const RUN_NAMES: Record<RunKind, string> = {
  backup: "Backup",
  restore_test: "Restore test",
  backup_check: "Connection check",
};

/** What a run did, in a line. */
export function runSummary(run: BackupRun): string {
  if (run.state === "queued") return run.error ? `Will try again: ${run.error}` : "Waiting for the worker";
  if (run.state === "running") return "Running";
  if (run.state === "failed") return run.error ?? "Failed";
  const result = run.result ?? {};
  if (run.kind === "backup") {
    return `${bytes(Number(result.bytes ?? 0))} backed up (${bytes(Number(result.added ?? 0))} new), ` +
      `snapshot ${String(result.snapshot ?? "")}`;
  }
  if (run.kind === "restore_test") {
    return `Restored snapshot ${String(result.snapshot ?? "")}: the database and ` +
      `${Number(result.audit_entries ?? 0).toLocaleString("en-GB")} audit log entries check out`;
  }
  const made = result.repository_made ? "Made a new repository. " : "";
  return `${made}Reached it: ${Number(result.snapshots ?? 0)} snapshots there`;
}

/** An hour in UTC, with what it is here today. */
export function hourLabel(hour: number): string {
  const at = new Date();
  at.setUTCHours(hour, 0, 0, 0);
  const here = at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${String(hour).padStart(2, "0")}:00 UTC (${here} here)`;
}
