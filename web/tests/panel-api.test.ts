import assert from "node:assert/strict";
import { test } from "node:test";
import { imageBody as firmwareImageBody } from "../../firmware/tools/upload.ts";
import {
  BODY_BYTES,
  PANEL_HEIGHT,
  PANEL_PORT,
  PANEL_WIDTH,
  PIXEL_BYTES,
  UPLOAD_TIMEOUT_MS,
  PanelUploadError,
  fnv1a32,
  fragmentEndpoint,
  imageBody,
  normalizeDeviceEndpoint,
  rgbaToRgb565,
  sendImage,
} from "../src/panel-api.ts";

test("device addresses use explicit dotted-decimal IPv4 and a canonical port", () => {
  assert.equal(
    normalizeDeviceEndpoint(" 192.168.1.20 "),
    "http://192.168.1.20:18086",
  );
  assert.equal(
    normalizeDeviceEndpoint("192.168.1.20:81"),
    "http://192.168.1.20:81",
  );
  assert.equal(
    normalizeDeviceEndpoint("http://10.0.0.9:18086/"),
    "http://10.0.0.9:18086",
  );
  assert.equal(
    normalizeDeviceEndpoint("169.254.1.20"),
    "http://169.254.1.20:18086",
  );
  assert.equal(
    normalizeDeviceEndpoint("192.0.2.20:65535"),
    "http://192.0.2.20:65535",
  );
  for (const invalid of [
    "",
    "panel.local",
    "https://192.168.1.20",
    "http://user@192.168.1.20",
    "192.168.1.20:0",
    "192.168.1.20:65536",
    "192.168.1.20:018086",
    "192.168.1.20/api/image",
    "192.168.1.20?foo",
    "192.168.1.20#foo",
    "192.168.1.256",
    "192.168.01.20",
    "0xC0.168.1.20",
    "192.168.20",
    "3232235796",
    "0.0.0.0",
    "0.1.2.3",
    "127.0.0.1",
    "224.0.0.1",
    "255.255.255.255",
    "[::1]",
  ])
    assert.throws(() => normalizeDeviceEndpoint(invalid), Error, invalid);
});

test("redirect fragments decode exactly once and reject ambiguous or malformed targets", () => {
  assert.equal(
    fragmentEndpoint("#device=http%3A%2F%2F192.168.1.20%3A18086"),
    "http://192.168.1.20:18086",
  );
  assert.equal(
    fragmentEndpoint("#mode=image&device=10.0.0.9"),
    "http://10.0.0.9:18086",
  );
  for (const invalid of [
    "",
    "#hello",
    "#device=",
    "#device=%ZZ",
    "#device=http%253A%252F%252F192.168.1.20",
    "#device=192.168.1.20&device=192.168.1.21",
    "#device=https%3A%2F%2F192.168.1.20",
  ])
    assert.equal(fragmentEndpoint(invalid), null, invalid);
});

test("RGBA color oracle verifies RGB565 little-endian, black alpha composition and row ordering", () => {
  assert.equal(PANEL_WIDTH, 480);
  assert.equal(PANEL_HEIGHT, 320);
  assert.equal(PANEL_PORT, 18086);
  const rgba = new Uint8ClampedArray(PANEL_WIDTH * PANEL_HEIGHT * 4);
  rgba.set([
    255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255, 255, 0,
    0, 128, 255, 255, 255, 0,
  ]);
  rgba.set([255, 255, 0, 255], PANEL_WIDTH * 4);
  rgba.set([0, 255, 255, 255], rgba.length - 4);
  const pixels = rgbaToRgb565(rgba);
  assert.equal(pixels.length, 307200);
  assert.deepEqual(
    [...pixels.slice(0, 12)],
    [0x00, 0xf8, 0xe0, 0x07, 0x1f, 0x00, 0xff, 0xff, 0x00, 0x80, 0x00, 0x00],
  );
  assert.deepEqual(
    [...pixels.slice(PANEL_WIDTH * 2, PANEL_WIDTH * 2 + 2)],
    [0xe0, 0xff],
  );
  assert.deepEqual([...pixels.slice(-2)], [0xff, 0x07]);
  assert.throws(() => rgbaToRgb565(rgba.subarray(4)), /480/);
});

test("FNV known vectors and full body independently match the existing firmware upload tool", () => {
  assert.equal(fnv1a32(new Uint8Array()), 0x811c9dc5);
  assert.equal(fnv1a32(new TextEncoder().encode("foobar")), 0xbf9cf968);
  const pixels = Uint8Array.from(
    { length: PIXEL_BYTES },
    (_, index) => (index * 17 + 43) & 255,
  );
  const body = imageBody(pixels);
  assert.equal(body.length, BODY_BYTES);
  assert.deepEqual(
    [...body.slice(0, 12)],
    [0x56, 0x49, 0x4d, 0x47, 0xe0, 0x01, 0x40, 0x01, 0x00, 0xb0, 0x04, 0x00],
  );
  assert.deepEqual(body, new Uint8Array(firmwareImageBody(pixels)));
  assert.deepEqual(body.slice(16), pixels);
  assert.throws(() => imageBody(pixels.subarray(2)), /307200/);
});

test("upload POST omits Content-Type, preserves the binary body and only 202 reports RAM acceptance", async (context) => {
  const body = imageBody(new Uint8Array(PIXEL_BYTES));
  context.mock.method(AbortSignal, "timeout", (milliseconds: number) => {
    assert.equal(milliseconds, 60_000);
    assert.equal(milliseconds, UPLOAD_TIMEOUT_MS);
    return new AbortController().signal;
  });
  let calls = 0;
  const accepted = await sendImage("192.0.2.20", body, async (url, init) => {
    calls++;
    assert.equal(url, "http://192.0.2.20:18086/api/image");
    assert.equal(init?.method, "POST");
    assert.equal(init?.headers, undefined);
    const request = new Request(url, init);
    assert.equal(request.headers.has("Content-Type"), false);
    assert.deepEqual(new Uint8Array(await request.arrayBuffer()), body);
    assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store");
    assert.ok(init?.signal instanceof AbortSignal);
    assert.equal(init.signal.aborted, false);
    assert.deepEqual(new Uint8Array(init?.body as ArrayBuffer), body);
    return new Response(null, { status: 202 });
  });
  assert.deepEqual(accepted, { status: 202, accepted: true });
  assert.equal(calls, 1);
  for (const status of [200, 204, 400, 422, 503]) {
    await assert.rejects(
      sendImage("192.0.2.20", body, async () => new Response(null, { status })),
      (error: unknown) => {
        assert.ok(error instanceof PanelUploadError);
        assert.equal(error.kind, "http");
        assert.equal(error.status, status);
        return true;
      },
    );
  }
});

test("transport failures remain uncertain and are never retried; invalid input never starts a request", async () => {
  const body = imageBody(new Uint8Array(PIXEL_BYTES));
  for (const cause of [
    new TypeError("Network error"),
    new DOMException("Expired", "TimeoutError"),
  ]) {
    let calls = 0;
    await assert.rejects(
      sendImage("192.0.2.20", body, async () => {
        calls++;
        throw cause;
      }),
      (error: unknown) => {
        assert.ok(error instanceof PanelUploadError);
        assert.equal(error.kind, "transport");
        assert.match(error.message, /可能已接收/);
        assert.equal(error.status, undefined);
        return true;
      },
    );
    assert.equal(calls, 1);
  }
  const neverFetch: typeof fetch = async () => {
    assert.fail("Invalid input must not reach fetch");
  };
  await assert.rejects(
    sendImage("bad-host", body, neverFetch),
    (error: unknown) =>
      error instanceof PanelUploadError && error.kind === "invalid-input",
  );
  await assert.rejects(
    sendImage("192.0.2.20", body.subarray(16), neverFetch),
    (error: unknown) =>
      error instanceof PanelUploadError && error.kind === "invalid-input",
  );
});
