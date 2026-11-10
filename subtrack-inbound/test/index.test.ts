import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";

const env: Env = { BACKEND_URL: "https://backend.test", INBOUND_EMAIL_SECRET: "k" };

function fakeMessage(rawSize = 5) {
  return {
    from: "a@x.com",
    to: "u@pocketday.app",
    rawSize,
    raw: new Blob(["hello"]).stream(),
    setReject: vi.fn(),
  } as unknown as ForwardableEmailMessage;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  fetchMock.mockReset();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("email handler", () => {
  it("posts a signed body to the backend", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    await worker.email(fakeMessage(), env);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://backend.test/inbound/email");
    expect(init.headers["X-Inbound-Signature"]).toMatch(/^[0-9a-f]{64}$/);
    expect(JSON.parse(init.body).raw).toBe(btoa("hello"));
  });

  it("rejects over 8 MB without calling the backend", async () => {
    const msg = fakeMessage(8 * 1024 * 1024 + 1);
    await worker.email(msg, env);
    expect(msg.setReject).toHaveBeenCalledWith("Message too large");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retries a 5xx exactly once", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 503 }));
    await worker.email(fakeMessage(), env);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not retry a 4xx", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    await worker.email(fakeMessage(), env);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries once on a network error", async () => {
    fetchMock.mockRejectedValue(new Error("boom"));
    await worker.email(fakeMessage(), env);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
