export const MAX_RAW_BYTES = 8 * 1024 * 1024;

const CHUNK = 0x8000;

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

export function buildBody(
  envelopeFrom: string,
  envelopeTo: string,
  raw: Uint8Array,
): string {
  return JSON.stringify({
    envelope_from: envelopeFrom,
    envelope_to: envelopeTo,
    raw: toBase64(raw),
  });
}

/** Lowercase hex HMAC-SHA256 of `${timestamp}.${body}`. */
export async function signBody(
  secret: string,
  timestamp: string,
  body: string,
): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(`${timestamp}.${body}`));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
