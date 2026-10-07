import { normalizeDeviceEndpoint } from "./panel-api.ts";

export const SETTINGS_TIMEOUT_MS = 10_000;
export const MAX_RETURN_SECONDS = 3600;
export type PanelSettings = { return_after_seconds: number };
type SettingsErrorKind = "invalid-input" | "http" | "transport" | "response";

export class PanelSettingsError extends Error {
  readonly kind: SettingsErrorKind;
  readonly status?: number;

  constructor(
    message: string,
    kind: SettingsErrorKind,
    status?: number,
  ) {
    super(message);
    this.name = "PanelSettingsError";
    this.kind = kind;
    this.status = status;
  }
}

export function validateReturnSeconds(value: unknown): number {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < 0 ||
    value > MAX_RETURN_SECONDS
  )
    throw new PanelSettingsError(
      "自动返回时间应为 0 到 3600 之间的整数秒。",
      "invalid-input",
    );
  return value;
}

export function parseReturnSeconds(input: string): number {
  if (!/^\d+$/.test(input.trim()))
    throw new PanelSettingsError(
      "请填写整数秒，0 表示关闭自动返回。",
      "invalid-input",
    );
  return validateReturnSeconds(Number(input.trim()));
}

async function requestSettings(
  endpoint: string,
  seconds: number | undefined,
  fetcher: typeof fetch,
  signal?: AbortSignal,
): Promise<PanelSettings> {
  let address: string;
  try {
    address = normalizeDeviceEndpoint(endpoint);
  } catch (cause) {
    throw new PanelSettingsError((cause as Error).message, "invalid-input");
  }
  const timeout = AbortSignal.timeout(SETTINGS_TIMEOUT_MS);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetcher(`${address}/api/settings`, {
      method: seconds === undefined ? "GET" : "POST",
      ...(seconds === undefined
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ return_after_seconds: seconds }),
          }),
      credentials: "omit",
      cache: "no-store",
      signal: requestSignal,
    });
  } catch {
    if (requestSignal.aborted)
      throw new PanelSettingsError(
        seconds === undefined
          ? "读取设置已超时或中断，请手动重试。"
          : "保存响应已超时或中断，设置可能已保存；请重新读取确认。",
        "transport",
      );
    throw new PanelSettingsError(
      seconds === undefined
        ? "未读取到设置，请检查面板地址、同一局域网和本地网络权限后手动重试。"
        : "未获得保存确认，设置可能已保存。请手动重新读取后再决定是否重试。",
      "transport",
    );
  }
  if (response.status !== 200)
    throw new PanelSettingsError(
      `面板返回 HTTP ${response.status}：${response.status === 404 ? "当前固件未提供设置接口。" : seconds === undefined ? "未读取到设置，请手动重试。" : "保存未获确认，请重新读取设置。"}`,
      "http",
      response.status,
    );
  let settings: PanelSettings;
  try {
    const json: unknown = await response.json();
    if (typeof json !== "object" || json === null || Array.isArray(json))
      throw new Error("Invalid settings object");
    settings = {
      return_after_seconds: validateReturnSeconds(
        (json as Record<string, unknown>).return_after_seconds,
      ),
    };
  } catch {
    if (requestSignal.aborted)
      throw new PanelSettingsError(
        seconds === undefined
          ? "读取设置已超时或中断，请手动重试。"
          : "保存响应已超时或中断，设置可能已保存；请重新读取确认。",
        "transport",
      );
    throw new PanelSettingsError(
      seconds === undefined
        ? "面板返回的设置格式无效，未更改当前输入。"
        : "保存响应格式无效，无法确认结果；请重新读取设置。",
      "response",
    );
  }
  if (seconds !== undefined && settings.return_after_seconds !== seconds)
    throw new PanelSettingsError(
      "面板确认值与请求不一致，请重新读取设置。",
      "response",
    );
  return settings;
}

/** Each click makes one request; failed writes are never retried automatically. */
export function readSettings(
  endpoint: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<PanelSettings> {
  return requestSettings(endpoint, undefined, fetcher, signal);
}

export async function saveSettings(
  endpoint: string,
  seconds: number,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<PanelSettings> {
  validateReturnSeconds(seconds);
  return requestSettings(endpoint, seconds, fetcher, signal);
}

type SettingsRequest = { sequence: number; editRevision: number };

/** Keep responses from older addresses/requests out of the current editable form. */
export class SettingsRequests {
  private sequence = 0;
  private editRevision = 0;

  begin(): SettingsRequest {
    return { sequence: ++this.sequence, editRevision: this.editRevision };
  }

  edit(): void {
    ++this.editRevision;
  }

  invalidate(): void {
    ++this.sequence;
    this.edit();
  }

  result(request: SettingsRequest): "stale" | "edited" | "unchanged" {
    if (request.sequence !== this.sequence) return "stale";
    return request.editRevision === this.editRevision ? "unchanged" : "edited";
  }
}
