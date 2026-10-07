import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MAX_RETURN_SECONDS,
  SETTINGS_TIMEOUT_MS,
  PanelSettingsError,
  SettingsRequests,
  parseReturnSeconds,
  readSettings,
  saveSettings,
  validateReturnSeconds,
} from "../src/settings.ts";

const address = "192.0.2.20";
const reply = (seconds: number) =>
  new Response(JSON.stringify({ return_after_seconds: seconds }), { status: 200 });

test("return time accepts only integer seconds from disabled through one hour", () => {
  assert.equal(MAX_RETURN_SECONDS, 3600);
  for (const seconds of [0, 1, 60, 3600]) {
    assert.equal(validateReturnSeconds(seconds), seconds);
    assert.equal(parseReturnSeconds(` ${seconds} `), seconds);
  }
  for (const invalid of [-1, 3601, 0.5, NaN, Infinity, "60", null, undefined, true])
    assert.throws(() => validateReturnSeconds(invalid), PanelSettingsError);
  for (const invalid of ["", " ", "-1", "3601", "1.5", "1e3", "0x10", "Infinity"])
    assert.throws(() => parseReturnSeconds(invalid), PanelSettingsError);
});

test("explicit read performs one uncached, credential-free GET with a ten-second timeout", async (context) => {
  const timeout = new AbortController();
  context.mock.method(AbortSignal, "timeout", (milliseconds: number) => {
    assert.equal(milliseconds, 10_000);
    assert.equal(milliseconds, SETTINGS_TIMEOUT_MS);
    return timeout.signal;
  });
  let calls = 0;
  const settings = await readSettings(address, async (url, init) => {
    calls++;
    assert.equal(url, "http://192.0.2.20:18086/api/settings");
    assert.equal(init?.method, "GET");
    assert.equal(init?.body, undefined);
    assert.equal(init?.headers, undefined);
    assert.equal(init?.credentials, "omit");
    assert.equal(init?.cache, "no-store");
    assert.equal(init?.signal, timeout.signal);
    return reply(60);
  });
  assert.deepEqual(settings, { return_after_seconds: 60 });
  assert.equal(calls, 1);
});

test("save sends exact JSON including zero and requires a matching 200 confirmation", async () => {
  for (const seconds of [0, 60, 3600]) {
    let calls = 0;
    const settings = await saveSettings(address, seconds, async (url, init) => {
      calls++;
      assert.equal(url, "http://192.0.2.20:18086/api/settings");
      assert.equal(init?.method, "POST");
      const request = new Request(url, init);
      assert.equal(request.headers.get("Content-Type"), "application/json");
      assert.equal(await request.text(), `{"return_after_seconds":${seconds}}`);
      assert.equal(init?.credentials, "omit");
      assert.equal(init?.cache, "no-store");
      assert.ok(init?.signal instanceof AbortSignal);
      return reply(seconds);
    });
    assert.deepEqual(settings, { return_after_seconds: seconds });
    assert.equal(calls, 1);
  }
  await assert.rejects(
    saveSettings(address, 60, async () => reply(0)),
    (cause: unknown) => cause instanceof PanelSettingsError && cause.kind === "response" && /确认值/.test(cause.message),
  );
});

test("invalid address or seconds never contact the device", async () => {
  const neverFetch: typeof fetch = async () => assert.fail("Invalid input reached fetch");
  await assert.rejects(readSettings("panel.local", neverFetch), PanelSettingsError);
  await assert.rejects(saveSettings("https://192.0.2.20", 60, neverFetch), PanelSettingsError);
  for (const invalid of [-1, 3601, 0.5, undefined, "60"])
    await assert.rejects(saveSettings(address, invalid as number, neverFetch), PanelSettingsError);
});

test("non-200 responses remain errors, including a body that otherwise looks valid", async () => {
  for (const status of [202, 204, 400, 404, 503]) {
    await assert.rejects(
      readSettings(address, async () => new Response(status === 204 ? null : '{"return_after_seconds":60}', { status })),
      (cause: unknown) => {
        assert.ok(cause instanceof PanelSettingsError);
        assert.equal(cause.kind, "http");
        assert.equal(cause.status, status);
        if (status === 404) assert.match(cause.message, /未提供设置接口/);
        return true;
      },
    );
  }
});

test("malformed JSON and out-of-range device values cannot become settings", async () => {
  for (const body of [
    "not json", "null", "[]", "60", "{}", '{"return_after_seconds":"60"}',
    '{"return_after_seconds":-1}', '{"return_after_seconds":3601}',
    '{"return_after_seconds":0.5}',
  ]) {
    await assert.rejects(
      readSettings(address, async () => new Response(body, { status: 200 })),
      (cause: unknown) => cause instanceof PanelSettingsError && cause.kind === "response",
      body,
    );
  }
});

test("transport failure never retries and writes preserve uncertainty", async () => {
  for (const write of [false, true]) {
    let calls = 0;
    const fetcher: typeof fetch = async () => {
      calls++;
      throw new TypeError("Network error");
    };
    await assert.rejects(
      write ? saveSettings(address, 60, fetcher) : readSettings(address, fetcher),
      (cause: unknown) => {
        assert.ok(cause instanceof PanelSettingsError);
        assert.equal(cause.kind, "transport");
        if (write) assert.match(cause.message, /可能已保存.*重新读取/);
        return true;
      },
    );
    assert.equal(calls, 1);
  }
});

test("caller cancellation and the timeout both abort the combined signal without retry", async (context) => {
  for (const expire of [false, true]) {
    const caller = new AbortController();
    const timeout = new AbortController();
    context.mock.method(AbortSignal, "timeout", () => timeout.signal);
    let calls = 0;
    const pending = readSettings(address, async (_url, init) => {
      calls++;
      const signal = init!.signal!;
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
    }, caller.signal);
    if (expire) timeout.abort(new DOMException("Expired", "TimeoutError"));
    else caller.abort();
    await assert.rejects(pending, (cause: unknown) => cause instanceof PanelSettingsError && cause.kind === "transport");
    assert.equal(calls, 1);
  }
});

test("interrupted response bodies preserve save uncertainty instead of reporting bad JSON", async (context) => {
  for (const write of [false, true]) {
    const timeout = new AbortController();
    context.mock.method(AbortSignal, "timeout", () => timeout.signal);
    const response = reply(60);
    context.mock.method(response, "json", async () => {
      timeout.abort(new DOMException("Expired", "TimeoutError"));
      throw timeout.signal.reason;
    });
    await assert.rejects(
      write ? saveSettings(address, 60, async () => response) : readSettings(address, async () => response),
      (cause: unknown) => {
        assert.ok(cause instanceof PanelSettingsError);
        assert.equal(cause.kind, "transport");
        assert.match(cause.message, /超时或中断/);
        if (write) assert.match(cause.message, /可能已保存.*重新读取/);
        return true;
      },
    );
  }
});

test("late responses cannot replace edits or cross an address change, even after switching back", () => {
  const requests = new SettingsRequests();
  const read = requests.begin();
  assert.equal(requests.result(read), "unchanged");
  requests.edit();
  requests.edit(); // Returning to the original input still counts as a new edit.
  assert.equal(requests.result(read), "edited");
  const save = requests.begin();
  assert.equal(requests.result(read), "stale");
  assert.equal(requests.result(save), "unchanged");
  requests.invalidate(); // Device A → B.
  requests.invalidate(); // Device B → A must not revive A's previous response.
  assert.equal(requests.result(save), "stale");
  const current = requests.begin();
  assert.equal(requests.result(current), "unchanged");
});
