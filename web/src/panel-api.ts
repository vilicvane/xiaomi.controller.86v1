/** The maintained firmware's logical framebuffer and HTTP image contract. */
export const PANEL_WIDTH = 480;
export const PANEL_HEIGHT = 320;
export const PANEL_PORT = 18086;
export const PIXEL_BYTES = PANEL_WIDTH * PANEL_HEIGHT * 2;
export const BODY_BYTES = 16 + PIXEL_BYTES;
export const UPLOAD_TIMEOUT_MS = 60_000;

/** Accept dotted-decimal unicast IPv4 only; URL's octal/short-address coercion is unwanted. */
export function normalizeDeviceEndpoint(input: string): string {
  const match =
    /^(?:http:\/\/)?((?:0|[1-9]\d{0,2})(?:\.(?:0|[1-9]\d{0,2})){3})(?::([1-9]\d{0,4}))?\/?$/.exec(
      input.trim(),
    );
  if (!match)
    throw new Error("请输入面板的 IPv4 地址及端口，例如 203.0.113.20:18086。");
  const octets = match[1].split(".").map(Number);
  if (
    octets.some((value) => value > 255) ||
    octets[0] === 0 ||
    octets[0] === 127 ||
    octets[0] >= 224
  )
    throw new Error("请输入面板实际显示的 IPv4 单播地址。");
  const port = match[2] === undefined ? PANEL_PORT : Number(match[2]);
  if (port > 65535) throw new Error("端口应在 1 到 65535 之间。");
  return `http://${match[1]}:${port}`;
}

/** A firmware redirect carries the LAN address in a fragment, not a server-visible query. */
export function fragmentEndpoint(hash: string): string | null {
  const values = new URLSearchParams(
    hash.startsWith("#") ? hash.slice(1) : hash,
  ).getAll("device");
  if (values.length !== 1) return null;
  try {
    return normalizeDeviceEndpoint(values[0]);
  } catch {
    return null;
  }
}

export function fnv1a32(bytes: Uint8Array): number {
  let checksum = 0x811c9dc5;
  for (const byte of bytes)
    checksum = Math.imul(checksum ^ byte, 0x01000193) >>> 0;
  return checksum;
}

/** Row-major RGBA; transparency is composited onto black before RGB565 quantization. */
export function rgbaToRgb565(
  rgba: Uint8Array | Uint8ClampedArray,
): Uint8Array<ArrayBuffer> {
  if (rgba.length !== PANEL_WIDTH * PANEL_HEIGHT * 4)
    throw new Error("图像必须为 480 × 320 像素。");
  const pixels = new Uint8Array(PIXEL_BYTES);
  for (
    let source = 0, destination = 0;
    source < rgba.length;
    source += 4, destination += 2
  ) {
    const alpha = rgba[source + 3] / 255;
    const red = Math.round(rgba[source] * alpha);
    const green = Math.round(rgba[source + 1] * alpha);
    const blue = Math.round(rgba[source + 2] * alpha);
    const color = ((red >>> 3) << 11) | ((green >>> 2) << 5) | (blue >>> 3);
    pixels[destination] = color & 255;
    pixels[destination + 1] = color >>> 8;
  }
  return pixels;
}

export function imageBody(pixels: Uint8Array): Uint8Array<ArrayBuffer> {
  if (pixels.length !== PIXEL_BYTES)
    throw new Error("RGB565 像素数据必须恰好为 307200 字节。");
  const body = new Uint8Array(BODY_BYTES);
  body.set([0x56, 0x49, 0x4d, 0x47]); // VIMG
  const header = new DataView(body.buffer);
  header.setUint16(4, PANEL_WIDTH, true);
  header.setUint16(6, PANEL_HEIGHT, true);
  header.setUint32(8, PIXEL_BYTES, true);
  header.setUint32(12, fnv1a32(pixels), true);
  body.set(pixels, 16);
  return body;
}

export type UploadErrorKind = "http" | "transport" | "invalid-input";

export class PanelUploadError extends Error {
  readonly kind: UploadErrorKind;
  readonly status?: number;

  constructor(message: string, kind: UploadErrorKind, status?: number) {
    super(message);
    this.name = "PanelUploadError";
    this.kind = kind;
    this.status = status;
  }
}

const rejectionMessages: Record<number, string> = {
  400: "请求或图像格式无效。",
  404: "设备未提供图片接口，请确认维护版固件。",
  405: "设备不接受此请求方法。",
  408: "设备等待请求超时。",
  411: "设备未收到图片长度。",
  413: "图片数据超过设备要求的大小。",
  417: "设备不支持此请求方式。",
  422: "图片校验失败，原图片未替换。",
  431: "请求头过大。",
  503: "设备暂时无法接收图片，请稍后手动重试。",
};

/** One request only. HTTP 202 means queued in RAM, not LCD completion or persistent storage. */
export async function sendImage(
  endpoint: string,
  body: Uint8Array,
  fetcher: typeof fetch = fetch,
): Promise<{ status: 202; accepted: true }> {
  let address: string;
  try {
    address = normalizeDeviceEndpoint(endpoint);
    if (body.length !== BODY_BYTES)
      throw new Error("上传数据必须为 307216 字节。");
  } catch (error) {
    throw new PanelUploadError(
      error instanceof Error ? error.message : "上传参数无效。",
      "invalid-input",
    );
  }
  let response: Response;
  try {
    response = await fetcher(`${address}/api/image`, {
      method: "POST",
      body: body.slice().buffer,
      credentials: "omit",
      cache: "no-store",
      signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
    });
  } catch {
    throw new PanelUploadError(
      "未获得面板确认，图片可能已接收。请检查同一局域网、浏览器的本地网络权限及 HTTP 访问限制，再手动重试。",
      "transport",
    );
  }
  if (response.status !== 202)
    throw new PanelUploadError(
      `面板返回 HTTP ${response.status}：${rejectionMessages[response.status] ?? "上传未获接受。"}`,
      "http",
      response.status,
    );
  return { status: 202, accepted: true };
}
