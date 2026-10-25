// Mirrors backend/app/tls.py and backend/app/server_routes.py.

export type TlsMode = "internal" | "own" | "acme";

export interface Certificate {
  subject: string;
  names: string[];
  issuer: string;
  not_after: string;
}

export interface TlsSettings {
  mode: TlsMode;
  acme_email: string;
  certificate: Certificate | null;
}

export interface TlsStatus {
  settings: TlsSettings;
  host: string;
  served: Certificate | null;
  root_url: string | null;
}

export interface TlsChoice {
  mode: TlsMode;
  acme_email: string;
  certificate_pem: string;
  key_pem: string;
}

export const MODES: { mode: TlsMode; name: string; about: string }[] = [
  { mode: "internal", name: "Skjald's own certificate authority",
    about: "Works at once, offline too. Each computer that uses Skjald installs its root certificate once." },
  { mode: "own", name: "Your organisation's certificate",
    about: "A certificate for this address from your own or a public authority, with its key, as PEM files." },
  { mode: "acme", name: "Let's Encrypt",
    about: "Free and automatic, for an address the internet can reach on port 443." },
];

export function choiceFrom(status: TlsStatus): TlsChoice {
  return { mode: status.settings.mode, acme_email: status.settings.acme_email,
    certificate_pem: "", key_pem: "" };
}

/** The choice as the API takes it: files only when new ones were picked. */
export function tlsBody(choice: TlsChoice) {
  return {
    mode: choice.mode,
    acme_email: choice.acme_email,
    certificate_pem: choice.mode === "own" && choice.certificate_pem ? choice.certificate_pem : null,
    key_pem: choice.mode === "own" && choice.key_pem ? choice.key_pem : null,
  };
}

/** When a certificate runs out, in words (Caddy's own last hours, not days). */
export function expiry(certificate: Certificate, now = Date.now()): string {
  const left = new Date(certificate.not_after).getTime() - now;
  const days = Math.floor(left / 86_400_000);
  const hours = Math.floor(left / 3_600_000);
  if (left <= 0) return "expired";
  if (days >= 1) return `expires in ${days} day${days === 1 ? "" : "s"}`;
  if (hours >= 1) return `expires in ${hours} hour${hours === 1 ? "" : "s"}`;
  return "expires within the hour";
}

export const RESET_COMMAND = "docker compose exec app python -m app.console reset-certificate";
