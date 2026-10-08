import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { useMatch } from "react-router";
import { Check, CircleAlert, LoaderCircle, RefreshCw, Save, Timer } from "lucide-react";
import { usePanel } from "./panel-context.tsx";
import { normalizeDeviceEndpoint } from "./panel-api.ts";
import {
  PanelSettingsError,
  SettingsRequests,
  parseReturnSeconds,
  readSettings,
  saveSettings,
} from "./settings.ts";

type Operation = "read" | "save";
type ButtonState = "idle" | "working" | "success" | "error";
type FormState = {
  seconds: string;
  invalid: boolean;
  busy: boolean;
  read: ButtonState;
  save: ButtonState;
  feedback: string;
  feedbackState: ButtonState;
};
type PendingRequest = {
  controller: AbortController;
  operation: Operation;
  endpoint: string;
  ticket: ReturnType<SettingsRequests["begin"]>;
  revision: number;
};
type SettingsContextValue = {
  form: FormState;
  editSeconds(value: string): void;
  update(operation: Operation): Promise<void>;
  secondsInput: RefObject<HTMLInputElement | null>;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

function uncertainSaveMessage(endpoint: string) {
  return `面板（${endpoint.slice(7)}）的保存结果未获确认，可能已保存；请切回该地址重新读取确认。`;
}

function saveMayHaveSucceeded(cause: unknown) {
  // These maintained-protocol rejections occur before the settings file write.
  return !(cause instanceof PanelSettingsError &&
    (cause.kind === "invalid-input" ||
      (cause.kind === "http" && [400, 404, 405, 408, 409, 411, 413, 415, 417, 422, 431].includes(cause.status!))));
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const panel = usePanel();
  const onSettings = useMatch("/settings") !== null;
  const [requests] = useState(() => new SettingsRequests());
  const lifetime = useRef(0);
  const pending = useRef<PendingRequest | undefined>(undefined);
  const uncertainSave = useRef<string | undefined>(undefined);
  const committed = useRef({ revision: panel.revision, onSettings });
  const secondsInput = useRef<HTMLInputElement | null>(null);
  const [form, setForm] = useState<FormState>({
    seconds: "",
    invalid: false,
    busy: false,
    read: "idle",
    save: "idle",
    feedback: "尚未读取当前面板设置。",
    feedbackState: "idle",
  });

  useLayoutEffect(() => {
    const previous = committed.current;
    committed.current = { revision: panel.revision, onSettings };
    const addressChanged = previous.revision !== panel.revision;
    const leftPage = previous.onSettings && !onSettings;
    if (!addressChanged && !leftPage) return;

    const request = pending.current;
    requests.invalidate();
    pending.current = undefined;
    request?.controller.abort();
    if (request?.operation === "save") uncertainSave.current = request.endpoint;
    const warning = uncertainSave.current ? uncertainSaveMessage(uncertainSave.current) : "";
    if (addressChanged) {
      setForm((current) => ({
        ...current,
        busy: false,
        read: "idle",
        save: "idle",
        feedbackState: "idle",
        feedback: "面板地址已更改，尚未读取此面板设置。" + warning,
      }));
    } else if (request) {
      const wasSaving = request.operation === "save";
      setForm((current) => ({
        ...current,
        busy: false,
        read: "idle",
        save: wasSaving ? "error" : "idle",
        feedbackState: wasSaving ? "error" : "idle",
        feedback: wasSaving ? warning : "读取请求已中断，尚未确认当前面板设置。" + warning,
      }));
    }
  }, [panel.revision, onSettings, requests]);

  useEffect(() => {
    const mountedLifetime = ++lifetime.current;
    return () => {
      // StrictMode and Fast Refresh retain the form and reclaim its pending request.
      // Dispose only when no setup reclaimed that ownership in the same effect flush.
      queueMicrotask(() => {
        if (lifetime.current !== mountedLifetime) return;
        requests.invalidate();
        pending.current?.controller.abort();
        pending.current = undefined;
      });
    };
  }, [requests]);

  function editSeconds(value: string) {
    requests.edit();
    const duringRequest = pending.current !== undefined;
    const warning = uncertainSave.current ? uncertainSaveMessage(uncertainSave.current) : "";
    setForm((current) => ({
      ...current,
      seconds: value,
      invalid: false,
      ...(!duringRequest ? {
        read: "idle" as const,
        save: "idle" as const,
        feedback: "设置已编辑，尚未保存。" + warning,
        feedbackState: "idle" as const,
      } : {}),
    }));
  }

  async function update(operation: Operation) {
    if (pending.current || !onSettings || panel.getRevision() !== panel.revision) return;
    const warning = uncertainSave.current ? uncertainSaveMessage(uncertainSave.current) : "";
    let endpoint: string;
    let seconds: number | undefined;
    try {
      endpoint = panel.endpoint ?? normalizeDeviceEndpoint(panel.address);
    } catch (cause) {
      setForm((current) => ({
        ...current,
        [operation]: "error",
        feedback: (cause as Error).message + warning,
        feedbackState: "error",
      }));
      panel.focusAddress();
      return;
    }
    if (operation === "save") {
      try {
        seconds = parseReturnSeconds(form.seconds);
      } catch (cause) {
        setForm((current) => ({
          ...current,
          save: "error",
          invalid: true,
          feedback: (cause as Error).message + warning,
          feedbackState: "error",
        }));
        secondsInput.current?.focus();
        return;
      }
    }

    const request: PendingRequest = {
      controller: new AbortController(),
      operation,
      endpoint,
      ticket: requests.begin(),
      revision: panel.revision,
    };
    const previousUncertain = uncertainSave.current;
    pending.current = request;
    const target = endpoint.slice(7);
    setForm((current) => ({
      ...current,
      busy: true,
      read: "idle",
      save: "idle",
      [operation]: "working",
      feedback: (operation === "read"
        ? `正在读取面板（${target}）设置…`
        : `正在保存面板（${target}）设置…`) +
        (previousUncertain && previousUncertain !== endpoint
          ? `此前面板（${previousUncertain.slice(7)}）的保存结果尚未确认；本次操作仅针对 ${target}。`
          : ""),
      feedbackState: "working",
    }));

    function result() {
      if (
        pending.current !== request ||
        panel.getRevision() !== request.revision ||
        !committed.current.onSettings
      ) return "stale";
      return requests.result(request.ticket);
    }

    try {
      const settings = operation === "read"
        ? await readSettings(endpoint, fetch, request.controller.signal)
        : await saveSettings(endpoint, seconds!, fetch, request.controller.signal);
      const status = result();
      if (status === "stale") return;
      if (uncertainSave.current === endpoint) uncertainSave.current = undefined;
      const remainingWarning = uncertainSave.current ? uncertainSaveMessage(uncertainSave.current) : "";
      const value = settings.return_after_seconds === 0
        ? "自动返回已关闭"
        : `未触摸 ${settings.return_after_seconds} 秒后自动返回`;
      setForm((current) => ({
        ...current,
        ...(status === "unchanged" ? {
          seconds: String(settings.return_after_seconds),
          invalid: false,
        } : {}),
        [operation]: "success",
        feedback: `面板（${target}）${operation === "read" ? "当前设置" : "已保存"}：${value}。${status === "edited" ? "输入已更改，未覆盖；新输入尚未保存。" : ""}${remainingWarning}`,
        feedbackState: "success",
      }));
    } catch (cause) {
      if (result() === "stale") return;
      if (operation === "save" && saveMayHaveSucceeded(cause)) uncertainSave.current = endpoint;
      const remainingWarning = uncertainSave.current ? uncertainSaveMessage(uncertainSave.current) : "";
      setForm((current) => ({
        ...current,
        [operation]: "error",
        feedback: `面板（${target}）：${cause instanceof Error ? cause.message : "设置请求未获确认，请手动重试。"}${remainingWarning}`,
        feedbackState: "error",
      }));
    } finally {
      // Address edits can precede React's commit. Let the effect record POST uncertainty.
      if (result() !== "stale") {
        pending.current = undefined;
        setForm((current) => ({ ...current, busy: false }));
      }
    }
  }

  return <SettingsContext.Provider value={{ form, editSeconds, update, secondsInput }}>
    {children}
  </SettingsContext.Provider>;
}

function SettingsButton({ operation, state, busy, onClick }: {
  operation: Operation;
  state: ButtonState;
  busy: boolean;
  onClick?: () => void;
}) {
  const labels = operation === "read"
    ? { idle: "读取设置", working: "正在读取…", success: "已读取", error: "重新读取" }
    : { idle: "保存设置", working: "正在保存…", success: "已保存", error: "重新保存" };
  const Icon = state === "working" ? LoaderCircle
    : state === "success" ? Check
    : state === "error" ? CircleAlert
    : operation === "read" ? RefreshCw : Save;
  return <button id={`${operation}-settings`} className="button secondary"
    type={operation === "read" ? "button" : "submit"}
    data-state={state} aria-busy={state === "working"} disabled={busy} onClick={onClick}>
    <Icon strokeWidth={1.65} aria-hidden="true" /><span>{labels[state]}</span>
  </button>;
}

export function SettingsPage() {
  const { form, editSeconds, update, secondsInput } = useContext(SettingsContext)!;
  return <section id="settings-page">
    <div className="settings-layout">
      <section className="settings-card card" aria-labelledby="settings-title">
        <h2 id="settings-title"><Timer strokeWidth={1.65} aria-hidden="true" />自动返回</h2>
        <p>原界面一段时间未触摸后，返回自定义图片。</p>
        <form id="settings-form" onSubmit={(event) => {
          event.preventDefault();
          void update("save");
        }}>
          <label className="field-label" htmlFor="return-seconds">等待时间</label>
          <div className="settings-controls">
            <div className="settings-field"><input ref={secondsInput} id="return-seconds" type="number"
              min="0" max="3600" step="1" placeholder="60" inputMode="numeric"
              aria-describedby="settings-help" aria-invalid={form.invalid || undefined}
              value={form.seconds} onChange={(event) => editSeconds(event.target.value)} /><span>秒</span></div>
            <div className="settings-actions">
              <SettingsButton operation="read" state={form.read} busy={form.busy} onClick={() => void update("read")} />
              <SettingsButton operation="save" state={form.save} busy={form.busy} />
            </div>
          </div>
          <p id="settings-help" className="settings-help">0 表示关闭，最多 3600 秒；保存后重启仍保留。</p>
          <p id="settings-feedback" className="settings-feedback" role="status" aria-live="polite"
            data-state={form.feedbackState}>{form.feedback}</p>
        </form>
      </section>
    </div>
  </section>;
}
