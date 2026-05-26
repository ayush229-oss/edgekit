/**
 * App-level encryption for sensitive fields (API keys).
 *
 * Algorithm: AES-256-GCM (authenticated encryption — tampering detected).
 * Output format (base64):  iv (12 bytes) || tag (16 bytes) || ciphertext (N bytes)
 *
 * The key comes from EDGEKIT_ENCRYPTION_KEY (64 hex chars = 32 bytes). Loss of
 * this key means stored API keys become unreadable — back it up.
 *
 * This is on top of Supabase's at-rest encryption. Defense in depth: if the
 * database is ever exposed (leak, mis-set RLS, exported backup), the API keys
 * are still useless without this key, which lives only in the server env var.
 */
import { randomBytes, createCipheriv, createDecipheriv } from "crypto";

function getKey(): Buffer {
  const hex = process.env.EDGEKIT_ENCRYPTION_KEY;
  if (!hex) {
    throw new Error(
      "EDGEKIT_ENCRYPTION_KEY is not set. Generate one with " +
      "`node -e \"console.log(require('crypto').randomBytes(32).toString('hex'))\"`"
    );
  }
  if (hex.length !== 64) {
    throw new Error(`EDGEKIT_ENCRYPTION_KEY must be 64 hex chars (32 bytes), got ${hex.length}`);
  }
  return Buffer.from(hex, "hex");
}

export function encryptString(plaintext: string): string {
  const key    = getKey();
  const iv     = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ct     = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag    = cipher.getAuthTag();
  return Buffer.concat([iv, tag, ct]).toString("base64");
}

export function decryptString(encrypted: string): string {
  const key  = getKey();
  const buf  = Buffer.from(encrypted, "base64");
  if (buf.length < 12 + 16 + 1) throw new Error("Ciphertext too short");
  const iv   = buf.subarray(0, 12);
  const tag  = buf.subarray(12, 28);
  const ct   = buf.subarray(28);
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ct), decipher.final()]).toString("utf8");
}

/** Cheap UI hint: last 4 chars of the key, masked. Stored unencrypted alongside. */
export function keyHint(plaintext: string): string {
  if (!plaintext) return "";
  if (plaintext.length <= 4) return "•".repeat(plaintext.length);
  return "••••••••" + plaintext.slice(-4);
}
