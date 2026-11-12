// A receipt number for one save (the Idempotency-Key), so a retry after a lost response cannot
// save twice. crypto.randomUUID exists only in secure contexts (https, localhost) and from Safari
// 15.4; on http at a LAN address or an older iPhone it is missing and calling it threw, so the
// answer and audiogram pages fell back or broke. getRandomValues is there in every case.
export function newReceiptKey(source = globalThis.crypto) {
  if (typeof source.randomUUID === "function") return source.randomUUID();
  const bytes = source.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
