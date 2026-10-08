import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  imageBody as firmwareImageBody,
  uploadFileBody,
  uploadImage,
} from "../../firmware/tools/upload.ts";
import {
  BODY_BYTES,
  CAPABILITY_TIMEOUT_MS,
  MAX_IMAGE_BYTES,
  PANEL_HEIGHT,
  PANEL_PORT,
  PANEL_WIDTH,
  PIXEL_BYTES,
  UPLOAD_TIMEOUT_MS,
  PanelUploadError,
  fnv1a32,
  getImageFormats,
  getImageCapabilities,
  queryEndpoint,
  imageBody,
  imageFormat,
  normalizeDeviceEndpoint,
  rgbaToRgb565,
  sendImage,
  sendCanvasImage,
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

test("redirect queries decode exactly once and reject ambiguous or malformed targets", () => {
  assert.equal(
    queryEndpoint("?device=http%3A%2F%2F192.168.1.20%3A18086"),
    "http://192.168.1.20:18086",
  );
  assert.equal(
    queryEndpoint("?mode=image&device=10.0.0.9"),
    "http://10.0.0.9:18086",
  );
  for (const invalid of [
    "",
    "?hello",
    "?device=",
    "?device=%ZZ",
    "?device=http%253A%252F%252F192.168.1.20",
    "?device=192.168.1.20&device=192.168.1.21",
    "?device=https%3A%2F%2F192.168.1.20",
  ])
    assert.equal(queryEndpoint(invalid), null, invalid);
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
    assert.equal(init?.redirect, "error");
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

const png = new Uint8Array(readFileSync(new URL("../public/github-card.png", import.meta.url)));
// Client tests identify signatures only; the device decoder validates complete JPEG contents.
const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
const vimg = imageBody(new Uint8Array(PIXEL_BYTES));
const capabilities = () => Response.json({ formats: ["png", "jpeg", "vimg"] });

test("standard image signatures accept variable file lengths without trusting filenames", () => {
  assert.equal(imageFormat(png), "png");
  assert.equal(imageFormat(jpeg), "jpeg");
  assert.equal(imageFormat(vimg), "vimg");
  for (const invalid of [
    new Uint8Array(),
    new Uint8Array(MAX_IMAGE_BYTES + 1),
    png.subarray(0, 7),
    new Uint8Array([0x56, 0x49, 0x4d, 0x47]),
    new TextEncoder().encode("GIF89a"),
  ]) assert.throws(() => imageFormat(invalid));
});

test("capability GET is explicit, has no extra request headers and only 404 selects deployed VIMG", async (context) => {
  context.mock.method(AbortSignal, "timeout", (milliseconds: number) => {
    assert.equal(milliseconds, CAPABILITY_TIMEOUT_MS);
    return new AbortController().signal;
  });
  let calls = 0;
  assert.deepEqual(await getImageFormats("192.0.2.20", async (url, init) => {
    calls++;
    assert.equal(url, "http://192.0.2.20:18086/api/image");
    assert.equal(init?.method, "GET");
    assert.equal(init?.headers, undefined);
    assert.equal(init?.body, undefined);
    assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.redirect, "error");
    return Response.json({ formats: ["png", "jpeg", "vimg", "png"] });
  }), ["png", "jpeg", "vimg"]);
  assert.equal(calls, 1);
  assert.deepEqual(await getImageFormats("192.0.2.20", async () =>
    new Response(null, { status: 404 })), ["vimg"]);
});

test("canvas upload selects PNG on new firmware and VIMG only on an explicit legacy 404", async () => {
  for (const legacy of [false, true]) {
    const methods: string[] = [];
    const result = await sendCanvasImage("192.0.2.20", png, vimg, async (url, init) => {
      methods.push(init!.method!);
      if (init?.method === "GET")
        return legacy ? new Response(null, { status: 404 }) : capabilities();
      assert.equal(init?.headers, undefined);
      assert.equal(new Request(url, init).headers.has("Content-Type"), false);
      assert.deepEqual(new Uint8Array(init?.body as ArrayBuffer), legacy ? vimg : png);
      return new Response(null, { status: 202 });
    });
    assert.deepEqual(methods, ["GET", "POST"]);
    assert.deepEqual(result, { status: 202, accepted: true, persistent: false });
  }
});

test("saved confirmation requires an explicit persistence capability and a successful POST", async () => {
  for (const persistent of [true, false, undefined]) {
    const methods: string[] = [];
    const result = await sendCanvasImage("192.0.2.20", png, vimg, async (_url, init) => {
      methods.push(init!.method!);
      return init?.method === "GET" ? Response.json({ formats: ["png"], persistent }) :
        new Response(null, { status: 202 });
    });
    assert.deepEqual(methods, ["GET", "POST"]);
    assert.deepEqual(result, { status: 202, accepted: true, persistent: persistent === true });
  }
  assert.deepEqual(await getImageCapabilities("192.0.2.20", async () => new Response(null, { status: 404 })),
    { formats: ["vimg"], persistent: false });
  await assert.rejects(sendCanvasImage("192.0.2.20", png, vimg, async (_url, init) =>
    init?.method === "GET" ? Response.json({ formats: ["png"], persistent: true }) :
      new Response(null, { status: 503 })), /HTTP 503|无法接收/);
});

test("failed or invalid capability reads never POST and never silently select VIMG", async () => {
  const failures = [
    () => { throw new TypeError("Network failed"); },
    () => new Response(null, { status: 503 }),
    () => new Response("not JSON", { status: 200 }),
    () => Response.json({ formats: [] }),
    () => Response.json({ formats: "png" }),
    () => Response.json({ formats: ["png", 1] }),
    () => Response.json({ formats: ["png"], persistent: "true" }),
    () => Response.json({ formats: ["jpeg"] }),
  ];
  for (const failure of failures) {
    const methods: string[] = [];
    await assert.rejects(sendCanvasImage("192.0.2.20", png, vimg, async (_url, init) => {
      methods.push(init!.method!);
      return failure();
    }), PanelUploadError);
    assert.deepEqual(methods, ["GET"]);
  }
});

test("a failed PNG POST stays uncertain or rejected without a second POST in VIMG", async () => {
  for (const transport of [false, true]) {
    const methods: string[] = [];
    await assert.rejects(sendCanvasImage("192.0.2.20", png, vimg, async (_url, init) => {
      methods.push(init!.method!);
      if (init?.method === "GET") return capabilities();
      if (transport) throw new TypeError("Connection lost after send");
      return new Response(null, { status: 422 });
    }), (error: unknown) => error instanceof PanelUploadError &&
      error.kind === (transport ? "transport" : "http"));
    assert.deepEqual(methods, ["GET", "POST"]);
  }
});

test("direct PNG and JPEG POST preserve file bytes and require only HTTP 202", async () => {
  for (const file of [png, jpeg]) {
    await sendImage("192.0.2.20", file, async (url, init) => {
      assert.equal(init?.method, "POST");
      const request = new Request(url, init);
      assert.equal(request.headers.has("Content-Type"), false);
      assert.deepEqual(new Uint8Array(await request.arrayBuffer()), file);
      return new Response(null, { status: 202 });
    });
  }
});

test("CLI keeps standard files intact and requires explicit .rgb565 for raw pixels", () => {
  assert.deepEqual(new Uint8Array(uploadFileBody(png, "wallpaper.dat")), png);
  assert.deepEqual(new Uint8Array(uploadFileBody(jpeg, "photo.png")), jpeg);
  assert.deepEqual(new Uint8Array(uploadFileBody(vimg, "wallpaper.vimg")), vimg);
  assert.deepEqual(new Uint8Array(uploadFileBody(new Uint8Array(PIXEL_BYTES), "raw.RGB565")), vimg);
  assert.throws(() => uploadFileBody(new Uint8Array(PIXEL_BYTES), "raw.png"));
});

test("CLI standard-file capability probes precede one exact POST; VIMG stays usable on deployed firmware", async () => {
  for (const file of [png, jpeg, vimg]) {
    const methods: string[] = [];
    await uploadImage("192.0.2.20", file, async (url, init) => {
      methods.push(init!.method!);
      if (init?.method === "GET") return capabilities();
      assert.equal(init?.redirect, "error");
      const request = new Request(url, init);
      assert.equal(request.headers.has("Content-Type"), false);
      assert.deepEqual(new Uint8Array(await request.arrayBuffer()), file);
      return new Response(null, { status: 202 });
    });
    assert.deepEqual(methods, file === vimg ? ["POST"] : ["GET", "POST"]);
  }
});

test("CLI rejects old, unavailable or invalid standard-file capabilities before any POST", async () => {
  for (const response of [
    new Response(null, { status: 404 }),
    new Response(null, { status: 503 }),
    new Response("invalid", { status: 200 }),
    Response.json({ formats: [] }),
    Response.json({ formats: ["png", 1] }),
  ]) {
    const methods: string[] = [];
    await assert.rejects(uploadImage("192.0.2.20", png, async (_url, init) => {
      methods.push(init!.method!);
      return response;
    }), /no image was uploaded/);
    assert.deepEqual(methods, ["GET"]);
  }
});

test("CLI does not retry a rejected or uncertain standard-image POST", async () => {
  for (const transport of [false, true]) {
    const methods: string[] = [];
    await assert.rejects(uploadImage("192.0.2.20", png, async (_url, init) => {
      methods.push(init!.method!);
      if (init?.method === "GET") return capabilities();
      if (transport) throw new TypeError("Connection lost");
      return new Response(null, { status: 503 });
    }), transport ? /may have been accepted/ : /HTTP 503/);
    assert.deepEqual(methods, ["GET", "POST"]);
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
