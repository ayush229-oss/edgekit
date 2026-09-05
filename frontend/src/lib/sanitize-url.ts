// Defensive sanitiser for backend-origin environment variables.
//
// Env values reach us via dashboards, copy-paste and shell heredocs, and they
// routinely pick up decoration that `new URL()` refuses to parse. The failure
// mode is nasty: the value *looks* right in the Vercel UI, but every server-side
// fetch dies with `TypeError: Failed to parse URL from …`. Observed in prod:
//
//   [https://edgekit-v2.onrender.com](https://edgekit-v2.onrender.com)
//     ↑ a Markdown auto-link, pasted out of a chat client or a README
//   ﻿https://edgekit-v2.onrender.com
//     ↑ BOM prefix from a UTF-8-with-signature file
//   "https://edgekit-v2.onrender.com/"
//     ↑ shell quotes preserved verbatim + trailing slash → `//graph/v2/nodes`
//
// `sanitizeBaseUrl` peels all of that off and validates what's left, so a
// malformed variable degrades to the known-good fallback instead of taking
// every API call down with it.

/** `[label](target)` → `target`. Markdown auto-links repeat the URL in both halves. */
const MARKDOWN_LINK = /^\[([^\]]*)\]\(\s*([^)\s]+)\s*\)$/;

/** `<https://example.com>` — RFC 3986 angle-bracket delimiters. */
const ANGLE_WRAPPED = /^<(.*)>$/;

/** Matching leading/trailing quote pair, straight or curly. */
const QUOTE_WRAPPED = /^(["'`‘’“”])(.*)\1$/;

/** Anything outside printable ASCII: BOM, zero-width joiners, stray newlines. */
const NON_PRINTABLE = /[^\x20-\x7E]/g;

/**
 * Strip formatting artefacts from a URL-ish string.
 *
 * Unwrapping runs in a loop because decorations nest — a value can arrive as
 * `"[<https://host>](<https://host>)"`, and peeling one layer exposes the next.
 */
function unwrap(value: string): string {
  let out = value.replace(NON_PRINTABLE, "").trim();

  // Bounded so a pathological input can never spin here.
  for (let i = 0; i < 5; i++) {
    const before = out;

    const quoted = QUOTE_WRAPPED.exec(out);
    if (quoted) out = quoted[2].trim();

    const markdown = MARKDOWN_LINK.exec(out);
    // Prefer the parenthesised target: in Markdown that is the actual
    // destination, and the label may be display text rather than a URL.
    if (markdown) out = markdown[2].trim();

    const angled = ANGLE_WRAPPED.exec(out);
    if (angled) out = angled[1].trim();

    if (out === before) break;
  }

  return out;
}

/**
 * Normalise a backend base URL so it can be safely concatenated with a path.
 *
 * Returns an origin (plus optional base path) with **no trailing slash**, so
 * `` `${base}/graph/v2/nodes` `` yields exactly one separator. If `raw` cannot
 * be salvaged into a valid http(s) URL, `fallback` is returned instead — the
 * fallback is sanitised too, so a bad default can't slip through either.
 */
export function sanitizeBaseUrl(raw: string | undefined | null, fallback: string): string {
  const cleaned = unwrap(raw ?? "");

  if (isUsableBaseUrl(cleaned)) return stripTrailingSlashes(cleaned);

  const cleanedFallback = unwrap(fallback);
  if (isUsableBaseUrl(cleanedFallback)) return stripTrailingSlashes(cleanedFallback);

  // Both unusable: return the stripped fallback rather than throwing at module
  // scope, which in Next.js would fail the whole route render rather than the
  // single request that actually needed the backend.
  return stripTrailingSlashes(cleanedFallback);
}

/** Trailing `/` removal, guarding against a value that is only slashes. */
function stripTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

/** True when `value` parses as an absolute http(s) URL. */
function isUsableBaseUrl(value: string): boolean {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Strip non-printables from a secret (API keys pasted from a BOM'd file carry
 * the same corruption, and an invalid header value throws inside `fetch`).
 */
export function sanitizeHeaderValue(raw: string | undefined | null): string {
  return (raw ?? "").replace(NON_PRINTABLE, "").trim();
}
