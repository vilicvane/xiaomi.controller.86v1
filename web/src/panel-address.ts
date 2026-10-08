import { normalizeDeviceEndpoint, queryEndpoint } from "./panel-api.ts";

export const PANEL_ADDRESS_KEY = "xiaomi.controller.86v1.device";
export type PanelAddressStorage = Pick<Storage, "getItem" | "setItem">;
export type ConnectionReturnTo = { pathname: "/" | "/settings" | "/api"; hash: "" };

/** A valid redirect address wins; invalid or missing queries use this browser's saved target. */
export function resolvePanelEndpoint(search: string, storage: PanelAddressStorage | null): string | null {
  const incoming = queryEndpoint(search);
  if (incoming) return incoming;
  try {
    const saved = storage?.getItem(PANEL_ADDRESS_KEY);
    return saved ? normalizeDeviceEndpoint(saved) : null;
  } catch {
    return null;
  }
}

/** Explicit saves must finish persistence before the caller switches the active target. */
export function savePanelEndpoint(address: string, storage: PanelAddressStorage | null): string {
  const endpoint = normalizeDeviceEndpoint(address);
  if (!storage) throw new Error("Browser storage is unavailable");
  storage.setItem(PANEL_ADDRESS_KEY, endpoint);
  return endpoint;
}

export function deviceSearch(search: string, endpoint: string | null): string {
  const params = new URLSearchParams(search);
  params.delete("device");
  if (endpoint) params.set("device", endpoint);
  return params.size ? "?" + params.toString() : "";
}

/** Router state is only an internal destination, never a URL supplied by another site. */
export function connectionReturnTo(state: unknown): ConnectionReturnTo {
  if (!state || typeof state !== "object") return { pathname: "/", hash: "" };
  const target = (state as { returnTo?: unknown }).returnTo;
  if (!target || typeof target !== "object") return { pathname: "/", hash: "" };
  const { pathname } = target as { pathname?: unknown };
  const page = pathname === "/settings" || pathname === "/settings/" ? "/settings"
    : pathname === "/api" || pathname === "/api/" ? "/api" : "/";
  return { pathname: page, hash: "" };
}
