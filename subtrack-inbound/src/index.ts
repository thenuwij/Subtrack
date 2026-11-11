import { MAX_RAW_BYTES, buildBody, signBody } from "./sign";

export interface Env {
  BACKEND_URL: string;
  INBOUND_EMAIL_SECRET: string;
}

const MAX_ATTEMPTS = 2;

async function post(env: Env, body: string): Promise<number | null> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = await signBody(env.INBOUND_EMAIL_SECRET, timestamp, body);
  try {
    const res = await fetch(`${env.BACKEND_URL}/inbound/email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Inbound-Timestamp": timestamp,
        "X-Inbound-Signature": signature,
      },
      body,
    });
    return res.status;
  } catch {
    return null;
  }
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    if (message.rawSize > MAX_RAW_BYTES) {
      message.setReject("Message too large");
      return;
    }

    const raw = new Uint8Array(await new Response(message.raw).arrayBuffer());
    const body = buildBody(message.from, message.to, raw);

    // Retry once on network error or 5xx, then drop. Log status codes only.
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      const status = await post(env, body);
      console.log(`inbound attempt ${attempt}: ${status ?? "network error"}`);
      if (status !== null && status < 500) return;
    }
  },
} satisfies ExportedHandler<Env>;
