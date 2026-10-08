import { icon } from "./icons.ts";
import { normalizeDeviceEndpoint } from "./panel-api.ts";
import {
  SettingsRequests,
  parseReturnSeconds,
  readSettings,
  saveSettings,
} from "./settings.ts";

type SettingsOperation = "read" | "save";
type SettingsState = "idle" | "working" | "success" | "error";

export function mountSettingsPage(root: HTMLElement): {
  deviceChanged(): void;
  leave(): void;
} {
  root.innerHTML = `
    <div class="page-heading"><h2>设置</h2></div>
    <div class="settings-layout">
      <section class="connection card" aria-labelledby="settings-device-title">
        <div class="card-heading"><div><h3 id="settings-device-title">面板连接</h3></div><span class="tiny-panel">${icon("wifi")}</span></div>
        <label class="field-label" for="settings-device">面板地址</label>
        <div class="device-field">${icon("wifi")}<input id="settings-device" type="text" placeholder="输入 IP 地址或 IP:端口" inputmode="url" autocomplete="off" spellcheck="false" aria-describedby="settings-device-help"/></div>
        <p class="field-help" id="settings-device-help">双击面板画面查看地址，默认端口 18086。</p>
        <p class="local-note">电脑或手机需与面板在同一局域网。<br>如浏览器询问本地网络访问，请选择允许。</p>
      </section>
      <section class="settings-card card" aria-labelledby="settings-title">
        <h3 id="settings-title">${icon("timer")}自动返回</h3>
        <p>原界面一段时间未触摸后，返回自定义图片。</p>
        <form id="settings-form">
          <label class="field-label" for="return-seconds">等待时间</label>
          <div class="settings-field"><input id="return-seconds" type="number" min="0" max="3600" step="1" placeholder="0–3600" inputmode="numeric" aria-describedby="settings-help"/><span>秒</span></div>
          <p id="settings-help" class="settings-help">0 表示关闭；保存的设置在重启后保留。</p>
          <div class="settings-actions"><button id="read-settings" class="button secondary" type="button" data-state="idle">${icon("refresh")}<span>读取设置</span></button><button id="save-settings" class="button secondary" type="submit" data-state="idle">${icon("save")}<span>保存设置</span></button></div>
          <p id="settings-feedback" class="settings-feedback" role="status" aria-live="polite">尚未读取当前面板设置。</p>
        </form>
      </section>
    </div>`;

  function element<T extends HTMLElement>(id: string): T {
    return root.querySelector<T>(`#${id}`)!;
  }
  const endpointInput = element<HTMLInputElement>("settings-device");
  const secondsInput = element<HTMLInputElement>("return-seconds");
  const settingsRequests = new SettingsRequests();
  let settingsController: AbortController | undefined;
  let settingsOperation: SettingsOperation | undefined;

  function settingsButton(operation: SettingsOperation, state: SettingsState) {
    const button = element<HTMLButtonElement>(`${operation}-settings`);
    const labels =
      operation === "read"
        ? { idle: "读取设置", working: "正在读取…", success: "已读取", error: "重新读取" }
        : { idle: "保存设置", working: "正在保存…", success: "已保存", error: "重新保存" };
    const symbol =
      state === "working" ? "loading"
        : state === "success" ? "check"
        : state === "error" ? "error"
        : operation === "read" ? "refresh" : "save";
    button.dataset.state = state;
    button.setAttribute("aria-busy", String(state === "working"));
    button.innerHTML = `${icon(symbol)}<span>${labels[state]}</span>`;
  }

  function settingsFeedback(message: string, state: SettingsState = "idle") {
    const feedback = element("settings-feedback");
    feedback.textContent = message;
    feedback.dataset.state = state;
  }

  function settingsBusy(busy: boolean) {
    for (const operation of ["read", "save"])
      element<HTMLButtonElement>(`${operation}-settings`).disabled = busy;
  }

  function cancelRequest() {
    settingsRequests.invalidate();
    settingsController?.abort();
    settingsController = undefined;
    settingsOperation = undefined;
    settingsBusy(false);
    settingsButton("read", "idle");
    settingsButton("save", "idle");
  }

  secondsInput.addEventListener("input", () => {
    settingsRequests.edit();
    secondsInput.removeAttribute("aria-invalid");
    if (!settingsController) {
      settingsButton("read", "idle");
      settingsButton("save", "idle");
      settingsFeedback("设置已编辑，尚未保存。");
    }
  });

  async function updateSettings(operation: SettingsOperation) {
    if (settingsController) return;
    let endpoint: string;
    let seconds: number | undefined;
    try {
      endpoint = normalizeDeviceEndpoint(endpointInput.value);
    } catch (cause) {
      settingsButton(operation, "error");
      settingsFeedback((cause as Error).message, "error");
      endpointInput.focus();
      return;
    }
    if (operation === "save") {
      try {
        seconds = parseReturnSeconds(secondsInput.value);
      } catch (cause) {
        settingsButton(operation, "error");
        settingsFeedback((cause as Error).message, "error");
        secondsInput.setAttribute("aria-invalid", "true");
        secondsInput.focus();
        return;
      }
    }
    const request = settingsRequests.begin();
    const controller = new AbortController();
    settingsController = controller;
    settingsOperation = operation;
    settingsBusy(true);
    settingsButton("read", "idle");
    settingsButton("save", "idle");
    settingsButton(operation, "working");
    settingsFeedback(
      operation === "read" ? "正在读取面板设置…" : "正在保存设置…",
      "working",
    );
    try {
      const settings =
        operation === "read"
          ? await readSettings(endpoint, fetch, controller.signal)
          : await saveSettings(endpoint, seconds!, fetch, controller.signal);
      const result = settingsRequests.result(request);
      if (result === "stale") return;
      if (result === "unchanged") {
        secondsInput.value = String(settings.return_after_seconds);
        secondsInput.removeAttribute("aria-invalid");
      }
      const value =
        settings.return_after_seconds === 0
          ? "自动返回已关闭"
          : `未触摸 ${settings.return_after_seconds} 秒后自动返回`;
      settingsButton(operation, "success");
      settingsFeedback(
        `${operation === "read" ? "面板当前设置" : "已保存"}：${value}。${result === "edited" ? "输入已更改，未覆盖；新输入尚未保存。" : ""}`,
        "success",
      );
    } catch (cause) {
      if (settingsRequests.result(request) === "stale") return;
      settingsButton(operation, "error");
      settingsFeedback(
        cause instanceof Error ? cause.message : "设置请求未获确认，请手动重试。",
        "error",
      );
    } finally {
      if (settingsRequests.result(request) !== "stale") {
        settingsController = undefined;
        settingsOperation = undefined;
        settingsBusy(false);
      }
    }
  }

  element("read-settings").addEventListener("click", () =>
    void updateSettings("read"),
  );
  element<HTMLFormElement>("settings-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void updateSettings("save");
  });

  return {
    deviceChanged() {
      const wasSaving = settingsOperation === "save";
      cancelRequest();
      settingsFeedback(
        "面板地址已更改，尚未读取此面板设置。" +
          (wasSaving
            ? "上一面板的保存请求已中断（可能已保存，请切回原地址重新读取确认）。"
            : ""),
      );
    },
    leave() {
      const operation = settingsOperation;
      if (!settingsController) return;
      cancelRequest();
      if (operation === "save") {
        settingsButton("save", "error");
        settingsFeedback("保存请求已中断（可能已保存，请重新读取确认）。", "error");
      } else {
        settingsFeedback("读取请求已中断，尚未确认当前面板设置。");
      }
    },
  };
}
