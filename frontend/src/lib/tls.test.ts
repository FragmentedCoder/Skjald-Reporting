import { describe, expect, it } from "vitest";
import { mailBody, type MailServer } from "./mail.js";
import { expiry, tlsBody, type Certificate } from "./tls.js";

const NOW = Date.parse("2026-10-25T12:00:00Z");

function certificate(notAfter: string): Certificate {
  return { subject: "skjald.example.com", names: [], issuer: "Test CA", not_after: notAfter };
}

describe("expiry", () => {
  it("says how long a certificate has left", () => {
    expect(expiry(certificate("2027-01-23T12:00:00Z"), NOW)).toBe("expires in 90 days");
    expect(expiry(certificate("2026-10-26T13:00:00Z"), NOW)).toBe("expires in 1 day");
    expect(expiry(certificate("2026-10-25T23:59:00Z"), NOW)).toBe("expires in 11 hours");
    expect(expiry(certificate("2026-10-25T13:30:00Z"), NOW)).toBe("expires in 1 hour");
    expect(expiry(certificate("2026-10-25T12:20:00Z"), NOW)).toBe("expires within the hour");
    expect(expiry(certificate("2026-10-24T12:00:00Z"), NOW)).toBe("expired");
  });
});

describe("tlsBody", () => {
  const files = { certificate_pem: "CERT", key_pem: "KEY", acme_email: "" };

  it("sends files only for an own certificate, and only new ones", () => {
    expect(tlsBody({ mode: "own", ...files })).toMatchObject({ certificate_pem: "CERT", key_pem: "KEY" });
    expect(tlsBody({ mode: "internal", ...files })).toMatchObject({ certificate_pem: null, key_pem: null });
    expect(tlsBody({ mode: "own", ...files, certificate_pem: "", key_pem: "" }))
      .toMatchObject({ certificate_pem: null, key_pem: null });
  });
});

describe("mailBody", () => {
  const server: MailServer = { host: "smtp.example.com", port: 587, security: "starttls",
    username: "skjald", from_address: "skjald@example.com", from_name: "" };

  it("keeps the saved password unless a new one is typed", () => {
    expect(mailBody(server, "").password).toBeNull();
    expect(mailBody(server, "new").password).toBe("new");
  });
});
