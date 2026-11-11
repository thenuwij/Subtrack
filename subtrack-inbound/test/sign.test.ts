import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { buildBody, signBody, toBase64 } from "../src/sign";

describe("signBody", () => {
  it("matches node:crypto HMAC-SHA256 hex", async () => {
    const expected = createHmac("sha256", "s3cret").update("1700000000.{\"a\":1}").digest("hex");
    expect(await signBody("s3cret", "1700000000", "{\"a\":1}")).toBe(expected);
  });
});

describe("buildBody", () => {
  it("has exactly the three contract fields", () => {
    const parsed = JSON.parse(buildBody("a@x.com", "b@y.com", new Uint8Array([1])));
    expect(Object.keys(parsed).sort()).toEqual(["envelope_from", "envelope_to", "raw"]);
  });

  it("round-trips binary through base64", () => {
    const bytes = Uint8Array.from({ length: 70000 }, (_, i) => i % 256);
    const parsed = JSON.parse(buildBody("a", "b", bytes));
    expect(new Uint8Array(Buffer.from(parsed.raw, "base64"))).toEqual(bytes);
    expect(toBase64(bytes)).toBe(Buffer.from(bytes).toString("base64"));
  });
});
