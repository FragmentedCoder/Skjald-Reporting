// Mirrors backend/app/mail.py and backend/app/server_routes.py.

export type MailSecurity = "starttls" | "tls" | "none";

export interface MailServer {
  host: string;
  port: number;
  security: MailSecurity;
  username: string;
  from_address: string;
  from_name: string;
}

export interface MailStatus {
  server: MailServer;
  password_set: boolean;
}

// Each with its usual port, which picking it fills in.
export const SECURITY: { value: MailSecurity; name: string; port: number }[] = [
  { value: "starttls", name: "STARTTLS (port 587)", port: 587 },
  { value: "tls", name: "TLS (port 465)", port: 465 },
  { value: "none", name: "None (a local relay)", port: 25 },
];

/** What's saved, as the form sends it; an empty password keeps the saved one. */
export function mailBody(server: MailServer, password: string) {
  return { ...server, password: password === "" ? null : password };
}
