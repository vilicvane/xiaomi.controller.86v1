import test from "node:test";
import assert from "node:assert/strict";
import {
  PANEL_ADDRESS_KEY,
  connectionReturnTo,
  deviceSearch,
  resolvePanelEndpoint,
  savePanelEndpoint,
  type PanelAddressStorage,
} from "../src/panel-address.ts";

const A = "http://192.0.2.21:18086", B = "http://192.0.2.22:18086";
function storage(value: string | null): PanelAddressStorage & { writes: [string, string][] } {
  const writes: [string, string][] = [];
  return { writes, getItem: key => key === PANEL_ADDRESS_KEY ? value : null,
    setItem: (key, next) => { writes.push([key, next]); value = next; } };
}

test("valid query takes priority without reading storage, including storage access failures", () => {
  const inaccessible = { getItem: () => { throw new Error("denied"); }, setItem: () => {} };
  assert.equal(resolvePanelEndpoint("?device=192.0.2.21", storage(B)), A);
  assert.equal(resolvePanelEndpoint("?device=192.0.2.21", inaccessible), A);
  assert.equal(resolvePanelEndpoint("?device=192.0.2.21", null), A);
});

test("missing, invalid and duplicate device queries fall back to a valid saved endpoint", () => {
  for (const query of ["", "?other=value", "?device=https://192.0.2.21", "?device=bad", "?device=192.0.2.21&device=192.0.2.22"])
    assert.equal(resolvePanelEndpoint(query, storage(" 192.0.2.22/ ")), B);
});

test("bad or inaccessible saved endpoints never become active targets and are not rewritten", () => {
  for (const saved of [null, "", "javascript:alert(1)", "http://example.com", "127.1", "192.0.2.21:0"])
    assert.equal(resolvePanelEndpoint("", storage(saved)), null);
  assert.equal(resolvePanelEndpoint("", null), null);
  assert.equal(resolvePanelEndpoint("", { getItem: () => { throw new Error("denied"); }, setItem: () => {} }), null);
  const saved = storage("192.0.2.22");
  assert.equal(resolvePanelEndpoint("", saved), B);
  assert.deepEqual(saved.writes, []);
});

test("explicit save validates before writing and persists a single project-only canonical endpoint", () => {
  const saved = storage(null);
  assert.equal(savePanelEndpoint(" 192.0.2.21/ ", saved), A);
  assert.deepEqual(saved.writes, [[PANEL_ADDRESS_KEY, A]]);
  assert.equal(resolvePanelEndpoint("", saved), A);
  assert.throws(() => savePanelEndpoint("http://192.0.2.22/path", saved));
  assert.equal(saved.writes.length, 1);
});

test("failed explicit storage writes throw rather than reporting a successful save", () => {
  assert.throws(() => savePanelEndpoint(A, null), /unavailable/);
  assert.throws(() => savePanelEndpoint(A, { getItem: () => B, setItem: () => { throw new Error("quota"); } }), /quota/);
});

test("device query generation canonicalizes active target without retaining duplicate or invalid device values", () => {
  const search = deviceSearch("?other=one&device=bad&device=other", A);
  assert.deepEqual([...new URLSearchParams(search)], [["other", "one"], ["device", A]]);
  assert.equal(deviceSearch("?device=bad", null), "");
  assert.equal(deviceSearch("?other=one&device=bad", null), "?other=one");
});

test("return destination accepts only known internal pages and clears unrelated anchors", () => {
  assert.deepEqual(connectionReturnTo({ returnTo: { pathname: "/", hash: "#api" } }), { pathname: "/", hash: "" });
  for (const pathname of ["/settings", "/settings/"])
    assert.deepEqual(connectionReturnTo({ returnTo: { pathname, hash: "#api" } }), { pathname: "/settings", hash: "" });
  for (const pathname of ["/api", "/api/"])
    assert.deepEqual(connectionReturnTo({ returnTo: { pathname } }), { pathname: "/api", hash: "" });
  for (const state of [null, {}, { returnTo: "https://example.com" }, { returnTo: { pathname: "https://example.com", hash: "#api" } }, { returnTo: { pathname: "//example.com" } }, { returnTo: { pathname: "/connection" } }])
    assert.deepEqual(connectionReturnTo(state), { pathname: "/", hash: "" });
});
