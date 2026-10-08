/** The maintained firmware's logical framebuffer and HTTP image contract. */
export const PANEL_WIDTH = 480;
export const PANEL_HEIGHT = 320;
export const PANEL_PORT = 18086;
export const PIXEL_BYTES = PANEL_WIDTH * PANEL_HEIGHT * 2;
export const BODY_BYTES = 16 + PIXEL_BYTES;
export const MAX_IMAGE_BYTES = 1024 * 1024;
export const CAPABILITY_TIMEOUT_MS = 10_000;
export const UPLOAD_TIMEOUT_MS = 60_000;

export type ImageFormat = "png" | "jpeg" | "vimg";

/** Content, not filename or Content-Type, determines the upload format. */
export function imageFormat(body: Uint8Array): ImageFormat {
  if (body.length < 1 || body.length > MAX_IMAGE_BYTES)
    throw new Error("图片文件大小必须在 1 字节到 1 MiB 之间。");
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (png.every((byte, index) => body[index] === byte)) return "png";
  if (body[0] === 0xff && body[1] === 0xd8) return "jpeg";
  if (body[0] === 0x56 && body[1] === 0x49 && body[2] === 0x4d && body[3] === 0x47) {
    if (body.length !== BODY_BYTES)
      throw new Error("VIMG Payload 必须恰好为 307216 字节。");
    return "vimg";
  }
  throw new Error("请选择 PNG、JPEG 或完整 VIMG Payload。");
}

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

/** Read the panel endpoint from the firmware redirect's device query parameter. */
export function queryEndpoint(search: string): string | null {
  const values = new URLSearchParams(search).getAll("device");
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

export type UploadErrorKind = "http" | "transport" | "invalid-input" | "capability";

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
  409: "面板的图片存储存在冲突，本次画面未替换。",
  411: "设备未收到图片长度。",
  413: "图片数据超过设备要求的大小。",
  415: "设备不支持这种图片格式或编码。",
  417: "设备不支持此请求方式。",
  422: "图片尺寸或内容校验失败，原图片未替换。",
  431: "请求头过大。",
  503: "设备暂时无法接收图片，请稍后手动重试。",
};

/** Explicit send-time probe. Only the deployed firmware's 404 selects legacy VIMG. */
export async function getImageCapabilities(
  endpoint: string,
  fetcher: typeof fetch = fetch,
): Promise<{ formats: ImageFormat[]; persistent: boolean }> {
  let address: string;
  try {
    address = normalizeDeviceEndpoint(endpoint);
  } catch (error) {
    throw new PanelUploadError((error as Error).message, "invalid-input");
  }
  let response: Response;
  try {
    response = await fetcher(`${address}/api/image`, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(CAPABILITY_TIMEOUT_MS),
    });
  } catch {
    throw new PanelUploadError(
      "无法读取面板的图片能力，尚未上传。请检查网络及浏览器的本地网络权限，再手动重试。",
      "transport",
    );
  }
  if (response.status === 404) return { formats: ["vimg"], persistent: false };
  if (response.status !== 200)
    throw new PanelUploadError(
      `读取图片能力时面板返回 HTTP ${response.status}，尚未上传。`,
      "http",
      response.status,
    );
  try {
    const value: unknown = await response.json();
    const capability = value as { formats?: unknown; persistent?: unknown } | null;
    const formats = capability?.formats;
    if (!Array.isArray(formats) ||
        formats.some((format) => typeof format !== "string")) throw new Error();
    if (capability?.persistent !== undefined && typeof capability.persistent !== "boolean")
      throw new Error();
    const supported = formats.filter((format): format is ImageFormat =>
      format === "png" || format === "jpeg" || format === "vimg");
    if (!supported.length) throw new Error();
    return { formats: [...new Set(supported)], persistent: capability?.persistent === true };
  } catch {
    throw new PanelUploadError(
      "面板的图片能力响应无效，尚未上传。请确认设备固件。",
      "capability",
    );
  }
}

export async function getImageFormats(
  endpoint: string,
  fetcher: typeof fetch = fetch,
): Promise<ImageFormat[]> {
  return (await getImageCapabilities(endpoint, fetcher)).formats;
}

/** Capture both representations before probing; never retry a failed POST in another format. */
export async function sendCanvasImage(
  endpoint: string,
  png: Uint8Array,
  vimg: Uint8Array,
  fetcher: typeof fetch = fetch,
): Promise<{ status: 202; accepted: true; persistent: boolean }> {
  const capability = await getImageCapabilities(endpoint, fetcher);
  const body = capability.formats.includes("png") ? png : capability.formats.includes("vimg") ? vimg : null;
  if (!body) throw new PanelUploadError("面板未提供 PNG 或 VIMG 上传能力，尚未上传。", "capability");
  return { ...(await sendImage(endpoint, body, fetcher)), persistent: capability.persistent };
}

/** One request only. HTTP 202 means queued in RAM, not LCD completion or persistent storage. */
export async function sendImage(
  endpoint: string,
  body: Uint8Array,
  fetcher: typeof fetch = fetch,
): Promise<{ status: 202; accepted: true }> {
  let address: string;
  try {
    address = normalizeDeviceEndpoint(endpoint);
    imageFormat(body);
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
      redirect: "error",
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
