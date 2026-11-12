import { describe, expect, it, vi } from "vitest";

import { newReceiptKey } from "./receipt-key.js";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newReceiptKey", () => {
  it("uses the browser's randomUUID where there is one", () => {
    const fake = { randomUUID: vi.fn(() => "made-by-the-browser"), getRandomValues: vi.fn() };
    expect(newReceiptKey(fake)).toBe("made-by-the-browser");
    expect(fake.getRandomValues).not.toHaveBeenCalled();
  });

  // http on a LAN address, or Safari before iOS 15.4: no randomUUID, but getRandomValues is there.
  it("makes a version 4 UUID from getRandomValues without randomUUID", () => {
    const { getRandomValues } = globalThis.crypto;
    const fake = { getRandomValues: getRandomValues.bind(globalThis.crypto) };
    const keys = new Set(Array.from({ length: 50 }, () => newReceiptKey(fake)));
    expect(keys.size).toBe(50);
    for (const key of keys) expect(key).toMatch(UUID_V4);
  });
});
