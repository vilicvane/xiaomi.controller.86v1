import "./style.css";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CodeXml,
  Download,
  Image as ImageIcon,
  LoaderCircle,
  RefreshCw,
  Save,
  Timer,
  Upload,
  Wifi,
  createElement,
  type IconNode,
} from "lucide";
import {
  FRAME,
  constrain,
  sourceRect,
  zoomAt,
  type Crop,
  type Point,
} from "./crop.ts";
import {
  queryEndpoint,
  imageBody,
  normalizeDeviceEndpoint,
  rgbaToRgb565,
  sendImage,
} from "./panel-api.ts";
import {
  SettingsRequests,
  parseReturnSeconds,
  readSettings,
  saveSettings,
} from "./settings.ts";

const icons = {
  panel: ImageIcon,
  upload: Upload,
  arrow: ArrowRight,
  image: ImageIcon,
  download: Download,
  code: CodeXml,
  wifi: Wifi,
  check: Check,
  loading: LoaderCircle,
  error: CircleAlert,
  refresh: RefreshCw,
  save: Save,
  timer: Timer,
} satisfies Record<string, IconNode>;
const icon = (name: keyof typeof icons) =>
  createElement(icons[name], {
    "stroke-width": 1.65,
    "aria-hidden": "true",
    class: "lucide",
  }).outerHTML;
const github =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .8a11.2 11.2 0 0 0-3.54 21.83c.56.1.77-.24.77-.54v-2.1c-3.12.68-3.78-1.32-3.78-1.32-.51-1.3-1.24-1.65-1.24-1.65-1.02-.7.08-.68.08-.68 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.62 1.22 3.26.93.1-.73.39-1.22.71-1.5-2.49-.28-5.1-1.24-5.1-5.54 0-1.23.44-2.23 1.16-3.01-.12-.28-.5-1.42.11-2.96 0 0 .95-.3 3.08 1.15a10.7 10.7 0 0 1 5.6 0c2.14-1.45 3.08-1.15 3.08-1.15.61 1.54.23 2.68.11 2.96.73.78 1.16 1.78 1.16 3.01 0 4.32-2.61 5.26-5.11 5.54.4.35.76 1.03.76 2.08v3.08c0 .3.2.65.77.54A11.2 11.2 0 0 0 12 .8Z"/></svg>';
const PREVIEW_MARGIN = 32;
const STAGE = {
  width: FRAME.width + 2 * PREVIEW_MARGIN,
  height: FRAME.height + 2 * PREVIEW_MARGIN,
};

document.querySelector("#app")!.innerHTML = `
  <header class="site-header">
    <a class="brand" href="./"><span class="brand-mark">${icon("panel")}</span><h1>小米智能家庭面板</h1><span class="beta">86v1</span></a>
    <nav aria-label="主导航"><a href="#api" class="nav-link">${icon("code")}API 指南</a><a class="github-link" href="https://github.com/vilicvane/xiaomi.controller.86v1" target="_blank" rel="noopener noreferrer">${github}<span>GitHub</span></a></nav>
  </header>
  <main>
    <div class="workspace">
      <section class="editor card" aria-labelledby="preview-title">
        <div class="card-heading"><div><span class="step">01</span><h2 id="preview-title">调整画面</h2></div><span class="dimension">480 × 320 <span>·</span> 3:2</span></div>
        <div class="preview-well" id="drop-zone"><div class="canvas-wrap"><canvas id="preview" width="${STAGE.width}" height="${STAGE.height}" tabindex="0" aria-label="图片裁切预览。拖动调整位置，滚轮或双指缩放。键盘方向键移动，加减号缩放，0 重置。"></canvas><div class="crop-frame"><div class="crop-guides" aria-hidden="true"></div><span class="sample-tag" id="sample-tag">默认画面</span></div></div><div class="drop-overlay">松开以更换图片</div></div>
        <div class="image-row"><span class="image-info">${icon("image")}<span><strong id="file-name">GitHub 自定义界面</strong><small id="image-size">480 × 320 · 默认画面</small></span></span><button id="choose-image" class="button secondary">选择图片</button><input id="file-input" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden /></div>
        <p id="image-error" class="inline-error" role="alert" hidden></p>
      </section>
      <aside class="sidebar">
        <section class="connection card" aria-labelledby="send-title"><div class="card-heading"><div><span class="step">02</span><h2 id="send-title">发送到面板</h2></div><span class="tiny-panel">${icon("panel")}</span></div>
          <form id="send-form"><label class="field-label" for="device">面板地址</label><div class="device-field">${icon("wifi")}<input id="device" type="text" placeholder="输入 IP 地址或 IP:端口" inputmode="url" autocomplete="off" spellcheck="false" aria-describedby="device-help" required/></div><p class="field-help" id="device-help">双击面板画面查看地址，默认端口 18086。</p><button id="send" class="button primary" type="submit" data-state="idle" aria-live="polite"><span id="send-icon">${icon("upload")}</span><span id="send-label">发送画面</span>${icon("arrow")}</button><p id="send-feedback" class="send-feedback" role="status" aria-live="polite" hidden></p></form>
          <p class="local-note">电脑或手机需与面板在同一局域网。<br>如浏览器询问本地网络访问，请选择允许。</p>
        </section>
        <section class="settings-card card" aria-labelledby="settings-title"><h3 id="settings-title">${icon("timer")}自动返回</h3><p>原界面一段时间未触摸后，返回自定义图片。</p><form id="settings-form"><label class="field-label" for="return-seconds">等待时间</label><div class="settings-field"><input id="return-seconds" type="number" min="0" max="3600" step="1" placeholder="0–3600" inputmode="numeric" aria-describedby="settings-help"/><span>秒</span></div><p id="settings-help" class="settings-help">0 表示关闭；保存的设置在重启后保留。</p><div class="settings-actions"><button id="read-settings" class="button secondary" type="button" data-state="idle">${icon("refresh")}<span>读取设置</span></button><button id="save-settings" class="button secondary" type="submit" data-state="idle">${icon("save")}<span>保存设置</span></button></div><p id="settings-feedback" class="settings-feedback" role="status" aria-live="polite">尚未读取当前面板设置。</p></form></section>
        <section class="export-card card"><h3>下载当前画面</h3><p>保留原图名称，附带尺寸和格式后缀。</p><div class="export-buttons"><button id="download-png" class="button secondary">${icon("download")}PNG 图片</button><button id="download-payload" class="button secondary">VIMG Payload</button></div></section>
      </aside>
    </div>
    <section class="api card" id="api" aria-labelledby="api-title"><div class="api-heading"><span class="api-icon">${icon("code")}</span><h2 id="api-title">图片上传 API</h2><span class="api-badge">HTTP</span></div>
      <div class="api-body"><dl class="request-fields"><div><dt>Method</dt><dd><code class="method">POST</code></dd></div><div><dt>URL</dt><dd><code id="api-url">http://PANEL_IPV4:18086/api/image</code></dd></div><div><dt>Content-Length</dt><dd><code>307216</code> 字节</dd></div><div><dt>Payload</dt><dd>16 字节 VIMG 头 + 307200 字节 RGB565LE 像素</dd></div></dl><div><p>需要先将图片裁切缩放为 <strong>480 × 320</strong>，再编码成 RGB565LE，并添加 VIMG 头和 FNV-1a 校验。网页发送时会完成转换；下载的 VIMG Payload 已包含完整头部，可直接作为请求 body。</p><h3>cURL 示例</h3><pre class="api-example"><code id="api-curl"></code></pre><p>保留文件名前的 <code>@</code>，它表示让 cURL 读取本地文件内容。只将 <code>@</code> 后面的文件名或路径替换为下载的 <code>.vimg</code> 文件。cURL 会自动发送 Content-Length。</p><p><code>202</code> 表示面板已接收并排队显示。图片保存在 RAM，重启后清除。</p><a class="text-link" href="https://github.com/vilicvane/xiaomi.controller.86v1/blob/main/docs/http-image-api.md" target="_blank" rel="noopener noreferrer">完整协议 ${icon("arrow")}</a></div></div></section>
  </main><footer><span><strong>xiaomi.controller.86v1</strong></span><a href="https://github.com/vilicvane/xiaomi.controller.86v1" target="_blank" rel="noopener noreferrer">vilicvane ${icon("arrow")}</a></footer>`;

function element<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}
const canvas = element<HTMLCanvasElement>("preview");
const view = canvas.getContext("2d", { willReadFrequently: true })!;
const imageCanvas = document.createElement("canvas");
imageCanvas.width = FRAME.width;
imageCanvas.height = FRAME.height;
const ctx = imageCanvas.getContext("2d", { willReadFrequently: true })!;
const input = element<HTMLInputElement>("file-input");
const endpointInput = element<HTMLInputElement>("device");
const dropZone = element("drop-zone");
let source: ImageBitmap | HTMLImageElement;
let size = { width: 480, height: 320 };
let crop: Crop = { zoom: 1, x: 0, y: 0 };
let basename = "xiaomi-panel-github";
let loadGeneration = 0;
let sending = false;
let revision = 0;
for (const id of ["send", "download-png", "download-payload"])
  element<HTMLButtonElement>(id).disabled = true;

function render() {
  if (!source) return;
  const rect = sourceRect(crop, size);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, FRAME.width, FRAME.height);
  // Resample the source smoothly into panel pixels, including fractional zoom/pan.
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(
    source,
    rect.x,
    rect.y,
    rect.width,
    rect.height,
    0,
    0,
    FRAME.width,
    FRAME.height,
  );
  view.fillStyle = "#101010";
  view.fillRect(0, 0, STAGE.width, STAGE.height);
  view.imageSmoothingEnabled = ctx.imageSmoothingEnabled;
  view.imageSmoothingQuality = "high";
  const scale = FRAME.width / rect.width;
  view.drawImage(
    source,
    PREVIEW_MARGIN + (FRAME.width - size.width * scale) / 2 + crop.x,
    PREVIEW_MARGIN + (FRAME.height - size.height * scale) / 2 + crop.y,
    size.width * scale,
    size.height * scale,
  );
  // Copy the final panel pixels unchanged; CSS enlarges this bitmap as a pixel grid.
  view.imageSmoothingEnabled = false;
  view.drawImage(imageCanvas, PREVIEW_MARGIN, PREVIEW_MARGIN);
  view.fillStyle = "rgba(0, 0, 0, 0.55)";
  view.fillRect(0, 0, STAGE.width, PREVIEW_MARGIN);
  view.fillRect(0, PREVIEW_MARGIN + FRAME.height, STAGE.width, PREVIEW_MARGIN);
  view.fillRect(0, PREVIEW_MARGIN, PREVIEW_MARGIN, FRAME.height);
  view.fillRect(
    PREVIEW_MARGIN + FRAME.width,
    PREVIEW_MARGIN,
    PREVIEW_MARGIN,
    FRAME.height,
  );
  for (const id of ["download-png", "download-payload"])
    element<HTMLButtonElement>(id).disabled = false;
  element<HTMLButtonElement>("send").disabled = sending;
}

function changed() {
  ++revision;
  if (!sending) status();
}
function changeZoom(zoom: number, anchor: Point = { x: 0, y: 0 }) {
  crop = zoomAt(crop, zoom, anchor, size);
  changed();
  render();
}
function pan(x: number, y: number) {
  crop = constrain({ ...crop, x: crop.x + x, y: crop.y + y }, size);
  changed();
  render();
}
function reset() {
  crop = { zoom: 1, x: 0, y: 0 };
  changed();
  render();
}
element("choose-image").addEventListener("click", () => input.click());

function error(message: string) {
  const node = element("image-error");
  node.textContent = message;
  node.hidden = !message;
}
async function load(file: File) {
  if (
    !["image/png", "image/jpeg", "image/webp", "image/svg+xml"].includes(
      file.type,
    )
  ) {
    error("请选择 PNG、JPEG、WebP 或 SVG 图片。");
    return;
  }
  if (file.size > 32 * 1024 * 1024) {
    error("图片过大，请选择 32 MB 以内的文件。");
    return;
  }
  const generation = ++loadGeneration;
  try {
    let image: HTMLImageElement | ImageBitmap;
    if (file.type === "image/svg+xml") {
      const url = URL.createObjectURL(file);
      try {
        const svg = new Image();
        svg.src = url;
        await svg.decode();
        image = svg;
      } finally {
        URL.revokeObjectURL(url);
      }
    } else image = await createImageBitmap(file);
    const imageSize =
      image instanceof ImageBitmap
        ? { width: image.width, height: image.height }
        : { width: image.naturalWidth, height: image.naturalHeight };
    const close = () => {
      if (image instanceof ImageBitmap) image.close();
    };
    if (generation !== loadGeneration) {
      close();
      return;
    }
    if (imageSize.width * imageSize.height > 40_000_000) {
      close();
      throw new Error("图片分辨率过大，请先缩小到 4000 万像素以内。");
    }
    if (source instanceof ImageBitmap) source.close();
    source = image;
    size = imageSize;
    basename = file.name.replace(/\.[^.]+$/, "") || "panel";
    element("file-name").textContent = file.name;
    element("image-size").textContent =
      `${size.width} × ${size.height} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    element("sample-tag").hidden = true;
    error("");
    pointers.clear();
    reset();
  } catch (cause) {
    if (generation === loadGeneration) {
      error(
        cause instanceof DOMException
          ? "无法读取这张图片，请尝试其他文件。"
          : cause instanceof Error
            ? cause.message
            : "无法读取这张图片，请尝试其他文件。",
      );
      if (!source && sample.complete && sample.naturalWidth) {
        source = sample;
        render();
      }
    }
  }
}
input.addEventListener("change", () => {
  const file = input.files?.[0];
  if (file) void load(file);
  input.value = "";
});
let dragDepth = 0;
dropZone.addEventListener("dragenter", (event) => {
  event.preventDefault();
  ++dragDepth;
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
});
dropZone.addEventListener("dragleave", () => {
  if (--dragDepth <= 0) {
    dragDepth = 0;
    dropZone.classList.remove("dragging");
  }
});
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dragDepth = 0;
  dropZone.classList.remove("dragging");
  const file = event.dataTransfer?.files[0];
  if (file) void load(file);
});

const pointers = new Map<number, Point>();
function point(event: PointerEvent | WheelEvent): Point {
  const bounds = canvas.getBoundingClientRect();
  return {
    x:
      ((event.clientX - bounds.left) / bounds.width) * STAGE.width -
      STAGE.width / 2,
    y:
      ((event.clientY - bounds.top) / bounds.height) * STAGE.height -
      STAGE.height / 2,
  };
}
function pair() {
  const [a, b] = Array.from(pointers.values());
  return {
    center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
    distance: Math.hypot(a.x - b.x, a.y - b.y),
  };
}
canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  event.preventDefault();
  canvas.focus({ preventScroll: true });
  canvas.setPointerCapture(event.pointerId);
  pointers.set(event.pointerId, point(event));
  canvas.classList.add("active");
});
canvas.addEventListener("pointermove", (event) => {
  const before = pointers.get(event.pointerId);
  if (!before) return;
  const next = point(event);
  if (pointers.size === 2) {
    const old = pair();
    pointers.set(event.pointerId, next);
    const current = pair();
    if (old.distance > 0)
      crop = zoomAt(
        crop,
        (crop.zoom * current.distance) / old.distance,
        old.center,
        size,
      );
    pan(current.center.x - old.center.x, current.center.y - old.center.y);
  } else if (pointers.size === 1) {
    pointers.set(event.pointerId, next);
    pan(next.x - before.x, next.y - before.y);
  } else pointers.set(event.pointerId, next);
});
for (const type of ["pointerup", "pointercancel", "lostpointercapture"])
  canvas.addEventListener(type, (event) => {
    pointers.delete((event as PointerEvent).pointerId);
    if (!pointers.size) canvas.classList.remove("active");
  });
canvas.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault();
    const delta =
      event.deltaY *
      (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 320 : 1);
    changeZoom(crop.zoom * Math.exp(-delta * 0.0015), point(event));
  },
  { passive: false },
);
canvas.addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 24 : 8;
  const moves: Record<string, Point> = {
    ArrowLeft: { x: -step, y: 0 },
    ArrowRight: { x: step, y: 0 },
    ArrowUp: { x: 0, y: -step },
    ArrowDown: { x: 0, y: step },
  };
  if (moves[event.key]) {
    event.preventDefault();
    pan(moves[event.key].x, moves[event.key].y);
  } else if (["+", "=", "-"].includes(event.key)) {
    event.preventDefault();
    changeZoom(crop.zoom + (event.key === "-" ? -0.1 : 0.1));
  } else if (event.key === "0") {
    event.preventDefault();
    reset();
  }
});

function pixels() {
  return rgbaToRgb565(ctx.getImageData(0, 0, FRAME.width, FRAME.height).data);
}
function download(blob: Blob, extension: string, name = basename) {
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = `${name}-480x320.${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
element("download-png").addEventListener("click", () => {
  const name = basename;
  imageCanvas.toBlob((blob) => {
    if (blob) download(blob, "png", name);
  }, "image/png");
});
element("download-payload").addEventListener("click", () =>
  download(
    new Blob([imageBody(pixels())], { type: "application/octet-stream" }),
    "vimg",
  ),
);

function status(
  message = "",
  kind: "idle" | "working" | "success" | "error" = "idle",
) {
  const states = {
    idle: { label: "发送画面", icon: "upload" },
    working: { label: "正在发送…", icon: "loading" },
    success: { label: "画面已接收", icon: "check" },
    error: { label: "重新发送画面", icon: "error" },
  } as const;
  const button = element<HTMLButtonElement>("send");
  button.dataset.state = kind;
  button.setAttribute("aria-busy", String(kind === "working"));
  element("send-label").textContent = states[kind].label;
  element("send-icon").innerHTML = icon(states[kind].icon);
  const feedback = element("send-feedback");
  feedback.textContent = message;
  feedback.hidden = !(message && (kind === "error" || kind === "success"));
  feedback.dataset.state = kind;
}
element<HTMLFormElement>("send-form").addEventListener(
  "submit",
  async (event) => {
    event.preventDefault();
    if (sending || !source) return;
    let endpoint: string;
    try {
      endpoint = normalizeDeviceEndpoint(endpointInput.value);
    } catch (cause) {
      status((cause as Error).message, "error");
      endpointInput.focus();
      return;
    }
    endpointInput.value = endpoint.slice(7);
    sending = true;
    element<HTMLButtonElement>("send").disabled = true;
    status("正在发送画面，请稍候…", "working");
    try {
      const sentRevision = revision;
      await sendImage(endpoint, imageBody(pixels()));
      let addressChanged = true;
      try {
        addressChanged =
          normalizeDeviceEndpoint(endpointInput.value) !== endpoint;
      } catch {
        /* Current input may be an unfinished edit. */
      }
      const edited = sentRevision !== revision || addressChanged;
      status(
        edited ? "本次画面已接收；当前编辑或地址已改变，可再次发送。" : "",
        "success",
      );
    } catch (cause) {
      status(
        cause instanceof Error
          ? cause.message
          : "发送未获确认，请检查网络后手动重试。",
        "error",
      );
    } finally {
      sending = false;
      element<HTMLButtonElement>("send").disabled = false;
    }
  },
);
endpointInput.addEventListener("input", () => {
  if (!sending) status("等待发送");
});
const fromQuery = queryEndpoint(location.search);
if (fromQuery) endpointInput.value = fromQuery.slice(7);
function updateApiUrl() {
  let endpoint = "http://PANEL_IPV4:18086";
  try {
    endpoint = normalizeDeviceEndpoint(endpointInput.value);
  } catch {
    /* Keep the generic URL until an address is complete. */
  }
  const url = `${endpoint}/api/image`;
  element("api-url").textContent = url;
  element("api-curl").textContent =
    `curl -X POST "${url}" --data-binary "@xiaomi-panel-github-480x320.vimg"`;
}
endpointInput.addEventListener("input", updateApiUrl);
updateApiUrl();

const secondsInput = element<HTMLInputElement>("return-seconds");
const settingsRequests = new SettingsRequests();
let settingsController: AbortController | undefined;
type SettingsOperation = "read" | "save";
type SettingsState = "idle" | "working" | "success" | "error";

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

secondsInput.addEventListener("input", () => {
  settingsRequests.edit();
  secondsInput.removeAttribute("aria-invalid");
  if (!settingsController) {
    settingsButton("read", "idle");
    settingsButton("save", "idle");
    settingsFeedback("设置已编辑，尚未保存。");
  }
});
endpointInput.addEventListener("input", () => {
  settingsRequests.invalidate();
  settingsController?.abort();
  settingsController = undefined;
  settingsBusy(false);
  settingsButton("read", "idle");
  settingsButton("save", "idle");
  settingsFeedback("面板地址已更改，尚未读取此面板设置。");
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

const sample = new Image();
sample.onload = () => {
  if (!source) {
    source = sample;
    render();
  }
};
sample.onerror = () => {
  if (!source) error("默认画面未加载，请选择自己的图片。");
};
sample.src = `${import.meta.env.BASE_URL}github-card.png`;
