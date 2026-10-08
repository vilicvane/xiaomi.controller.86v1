import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  Check,
  CircleAlert,
  Download,
  Image as ImageIcon,
  LoaderCircle,
  Upload,
} from "lucide-react";
import { constrain, zoomAt, type Crop, type Point, type Size } from "./crop.ts";
import { PanelUploadError, sendCanvasImage } from "./panel-api.ts";
import { usePanel } from "./panel-context.tsx";
import {
  frameSnapshot,
  pngBlob,
  PREVIEW_SIZE,
  renderPreview,
  vimgBody,
  type EditorImage,
} from "./editor-render.ts";

type UploadKind = "idle" | "working" | "success" | "error";
type Metadata = { name: string; basename: string; description: string; sample: boolean };
type EditorState = {
  source: EditorImage | null;
  size: Size;
  crop: Crop;
  metadata: Metadata;
  revision: number;
  imageError: string;
  upload: { kind: UploadKind; message: string; uncertain?: boolean };
};
type EditorContextValue = {
  state: EditorState;
  load(file: File): Promise<void>;
  changeCrop(update: (crop: Crop, size: Size) => Crop): void;
  send(): Promise<void>;
  downloadPng(): Promise<void>;
};

const INITIAL: EditorState = {
  source: null,
  size: { width: 480, height: 320 },
  crop: { zoom: 1, x: 0, y: 0 },
  metadata: {
    name: "GitHub 自定义界面", basename: "xiaomi-panel-github",
    description: "480 × 320 · 默认画面", sample: true,
  },
  revision: 0,
  imageError: "",
  upload: { kind: "idle", message: "" },
};
const EditorContext = createContext<EditorContextValue | null>(null);
const UNCERTAIN_POST = "旧面板可能已接收图片，请确认后手动发送。";

function closeImage(image: EditorImage | null) {
  if (image instanceof ImageBitmap) image.close();
}

function download(blob: Blob, basename: string, extension: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${basename}-480x320.${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Mount above the routes so decoded images, crops and in-flight sends survive navigation. */
export function EditorProvider({ children }: { children: ReactNode }) {
  const panel = usePanel();
  const panelRef = useRef(panel);
  panelRef.current = panel;
  const [state, setState] = useState(INITIAL);
  const current = useRef(state);
  const loadGeneration = useRef(0);
  const sendGeneration = useRef(0);
  const lifetime = useRef(0);
  const fileLoad = useRef<number | null>(null);
  const activeSend = useRef<{ revision: number; controller: AbortController; posted: boolean } | null>(null);
  const sample = useRef<HTMLImageElement | null>(null);

  const change = useCallback((update: (state: EditorState) => EditorState) => {
    current.current = update(current.current);
    setState(current.current);
  }, []);
  const showImage = useCallback((source: EditorImage, size: Size, metadata: Metadata) => {
    closeImage(current.current.source);
    change((state) => ({
      ...state, source, size, metadata, crop: { zoom: 1, x: 0, y: 0 },
      revision: state.revision + 1, imageError: "",
      upload: state.upload.kind === "working" || state.upload.uncertain ? state.upload : INITIAL.upload,
    }));
  }, [change]);

  useEffect(() => {
    const mountedLifetime = ++lifetime.current;
    const image = new Image();
    sample.current = image;
    let mounted = true;
    image.src = `${import.meta.env.BASE_URL}github-card.png`;
    void image.decode().then(() => {
      if (mounted && fileLoad.current === null && !current.current.source)
        showImage(image, INITIAL.size, INITIAL.metadata);
    }, () => {
      if (mounted && fileLoad.current === null && !current.current.source)
        change((state) => ({ ...state, imageError: "默认画面未加载，请选择自己的图片。" }));
    });
    return () => {
      mounted = false;
      if (sample.current === image) sample.current = null;
      // StrictMode and Fast Refresh recreate effects while retaining state and owned images.
      // Dispose only if no setup reclaimed that ownership in the same effect flush.
      queueMicrotask(() => {
        if (lifetime.current !== mountedLifetime) return;
        ++loadGeneration.current;
        ++sendGeneration.current;
        fileLoad.current = null;
        activeSend.current?.controller.abort();
        closeImage(current.current.source);
      });
    };
  }, [change, showImage]);

  const load = useCallback(async (file: File) => {
    const imageError = !["image/png", "image/jpeg", "image/webp", "image/svg+xml"].includes(file.type)
      ? "请选择 PNG、JPEG、WebP 或 SVG 图片。"
      : file.size > 32 * 1024 * 1024 ? "图片过大，请选择 32 MB 以内的文件。" : "";
    if (imageError) {
      change((state) => ({ ...state, imageError }));
      return;
    }
    const generation = ++loadGeneration.current;
    fileLoad.current = generation;
    try {
      let image: EditorImage;
      if (file.type === "image/svg+xml") {
        const url = URL.createObjectURL(file);
        try {
          image = new Image();
          image.src = url;
          await image.decode();
        } finally {
          URL.revokeObjectURL(url);
        }
      } else image = await createImageBitmap(file);
      const size = image instanceof ImageBitmap
        ? { width: image.width, height: image.height }
        : { width: image.naturalWidth, height: image.naturalHeight };
      if (generation !== loadGeneration.current) {
        closeImage(image);
        return;
      }
      if (!size.width || !size.height || size.width * size.height > 40_000_000) {
        closeImage(image);
        throw new Error("图片分辨率无效或过大，请缩小到 4000 万像素以内。");
      }
      showImage(image, size, {
        name: file.name,
        basename: file.name.replace(/\.[^.]+$/, "") || "panel",
        description: `${size.width} × ${size.height} · ${(file.size / 1024 / 1024).toFixed(2)} MB`,
        sample: false,
      });
    } catch (cause) {
      if (generation !== loadGeneration.current) return;
      if (!current.current.source && sample.current?.complete && sample.current.naturalWidth)
        showImage(sample.current, INITIAL.size, INITIAL.metadata);
      change((state) => ({
        ...state, imageError: cause instanceof DOMException
          ? "无法读取这张图片，请尝试其他文件。"
          : cause instanceof Error ? cause.message : "无法读取这张图片，请尝试其他文件。",
      }));
    } finally {
      if (fileLoad.current === generation) fileLoad.current = null;
    }
  }, [change, showImage]);

  const changeCrop = useCallback((update: (crop: Crop, size: Size) => Crop) => {
    change((state) => ({
      ...state, crop: constrain(update(state.crop, state.size), state.size),
      revision: state.revision + 1,
      upload: state.upload.kind === "working" || state.upload.uncertain ? state.upload : INITIAL.upload,
    }));
  }, [change]);

  useEffect(() => {
    if (activeSend.current && activeSend.current.revision !== panel.getRevision())
      activeSend.current.controller.abort();
    if (current.current.upload.kind !== "working" && !current.current.upload.uncertain)
      change((state) => ({ ...state, upload: INITIAL.upload }));
  }, [panel.revision, panel.getRevision, change]);

  const send = useCallback(async () => {
    const snapshot = current.current;
    if (snapshot.upload.kind === "working" || !snapshot.source) return;
    const { endpoint, getRevision, focusAddress } = panelRef.current;
    if (!endpoint) {
      change((state) => ({
        ...state, upload: {
          kind: "error", uncertain: snapshot.upload.uncertain,
          message: "请先填写有效的面板地址。" + (snapshot.upload.uncertain ? UNCERTAIN_POST : ""),
        },
      }));
      focusAddress();
      return;
    }
    const generation = ++sendGeneration.current;
    const request = { revision: getRevision(), controller: new AbortController(), posted: false };
    activeSend.current = request;
    const addressChanged = () => request.revision !== getRevision();
    const requireAddress = () => {
      if (addressChanged()) {
        request.controller.abort();
        throw new Error("面板地址已改变。");
      }
    };
    const guardedFetch: typeof fetch = (input, options) => {
      requireAddress();
      if (options?.method === "POST") request.posted = true;
      return fetch(input, { ...options, signal: AbortSignal.any([
        request.controller.signal, ...(options?.signal ? [options.signal] : []),
      ]) });
    };
    change((state) => ({ ...state, upload: { kind: "working", message: "正在发送画面，请稍候…" } }));
    try {
      const frame = frameSnapshot(snapshot.source, snapshot.size, snapshot.crop);
      const vimg = vimgBody(frame);
      const png = new Uint8Array(await (await pngBlob(frame)).arrayBuffer());
      requireAddress();
      await sendCanvasImage(endpoint, png, vimg, guardedFetch);
      if (generation !== sendGeneration.current) return;
      const edited = snapshot.revision !== current.current.revision || addressChanged();
      change((state) => ({ ...state, upload: {
        kind: "success",
        message: edited ? "本次画面已接收；当前编辑或地址已改变，可再次发送。" : "",
      } }));
    } catch (cause) {
      if (generation !== sendGeneration.current) return;
      change((state) => ({ ...state, upload: {
        uncertain: request.posted && (addressChanged() ||
          cause instanceof PanelUploadError && cause.kind === "transport"),
        kind: "error", message: addressChanged()
          ? request.posted
            ? "面板地址已改变，本次发送已取消；" + UNCERTAIN_POST
            : "面板地址已改变，本次发送已取消，尚未上传。"
          : cause instanceof Error ? cause.message : "发送未获确认，请检查网络后手动重试。",
      } }));
    } finally {
      if (activeSend.current === request) activeSend.current = null;
    }
  }, [change]);

  const downloadPng = useCallback(async () => {
    const { source, size, crop, metadata } = current.current;
    if (!source) return;
    try {
      download(await pngBlob(frameSnapshot(source, size, crop)), metadata.basename, "png");
    } catch (cause) {
      change((state) => ({ ...state, imageError: (cause as Error).message }));
    }
  }, [change]);
  return <EditorContext.Provider value={{ state, load, changeCrop, send, downloadPng }}>
    {children}
  </EditorContext.Provider>;
}

const UPLOAD_LABELS: Record<UploadKind, string> = {
  idle: "发送画面", working: "正在发送…", success: "画面已接收", error: "重新发送画面",
};
const UPLOAD_ICONS = { idle: Upload, working: LoaderCircle, success: Check, error: CircleAlert };

export function ImageEditor() {
  const { state, load, changeCrop } = useContext(EditorContext)!;
  const { source, size, crop, metadata, imageError } = state;
  const canvas = useRef<HTMLCanvasElement>(null);
  const frame = useRef<HTMLCanvasElement | null>(null);
  const pointers = useRef(new Map<number, Point>());
  const dragDepth = useRef(0);
  const [active, setActive] = useState(false);
  const [dragging, setDragging] = useState(false);

  useLayoutEffect(() => {
    if (source) {
      frame.current ??= document.createElement("canvas");
      renderPreview(canvas.current!, frame.current, source, size, crop);
    }
  }, [source, size, crop]);
  useEffect(() => {
    pointers.current.clear();
    setActive(false);
  }, [source]);

  const point = useCallback((event: { clientX: number; clientY: number }): Point => {
    const bounds = canvas.current!.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * PREVIEW_SIZE.width - PREVIEW_SIZE.width / 2,
      y: ((event.clientY - bounds.top) / bounds.height) * PREVIEW_SIZE.height - PREVIEW_SIZE.height / 2,
    };
  }, []);
  useEffect(() => {
    const target = canvas.current!;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 320 : 1);
      const anchor = point(event);
      changeCrop((crop, size) => zoomAt(crop, crop.zoom * Math.exp(-delta * 0.0015), anchor, size));
    };
    target.addEventListener("wheel", wheel, { passive: false });
    return () => target.removeEventListener("wheel", wheel);
  }, [changeCrop, point]);

  function pair() {
    const [a, b] = [...pointers.current.values()];
    return { center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
      distance: Math.hypot(a.x - b.x, a.y - b.y) };
  }
  function pointerMove(event: PointerEvent<HTMLCanvasElement>) {
    const before = pointers.current.get(event.pointerId);
    if (!before) return;
    const next = point(event);
    if (pointers.current.size === 2) {
      const old = pair();
      pointers.current.set(event.pointerId, next);
      const current = pair();
      changeCrop((crop, size) => {
        const zoomed = old.distance > 0
          ? zoomAt(crop, crop.zoom * current.distance / old.distance, old.center, size) : crop;
        return { ...zoomed, x: zoomed.x + current.center.x - old.center.x,
          y: zoomed.y + current.center.y - old.center.y };
      });
    } else {
      pointers.current.set(event.pointerId, next);
      if (pointers.current.size === 1)
        changeCrop((crop) => ({ ...crop, x: crop.x + next.x - before.x, y: crop.y + next.y - before.y }));
    }
  }
  function releasePointer(event: PointerEvent<HTMLCanvasElement>) {
    pointers.current.delete(event.pointerId);
    if (!pointers.current.size) setActive(false);
  }
  function keyboard(event: KeyboardEvent<HTMLCanvasElement>) {
    const step = event.shiftKey ? 24 : 8;
    const moves: Record<string, Point> = {
      ArrowLeft: { x: -step, y: 0 }, ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step }, ArrowDown: { x: 0, y: step },
    };
    if (moves[event.key]) {
      event.preventDefault();
      const move = moves[event.key];
      changeCrop((crop) => ({ ...crop, x: crop.x + move.x, y: crop.y + move.y }));
    } else if (["+", "=", "-"].includes(event.key)) {
      event.preventDefault();
      const delta = event.key === "-" ? -0.1 : 0.1;
      changeCrop((crop, size) => zoomAt(crop, crop.zoom + delta, { x: 0, y: 0 }, size));
    } else if (event.key === "0") {
      event.preventDefault();
      changeCrop(() => ({ zoom: 1, x: 0, y: 0 }));
    }
  }

  return <section className="editor" aria-labelledby="preview-title">
      <div className="card-heading"><div><h2 id="preview-title">调整画面</h2></div>
        <span className="dimension">480 × 320 <span>·</span> 3:2</span></div>
      <div id="drop-zone" className={`preview-well${dragging ? " dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); ++dragDepth.current; setDragging(true); }}
        onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
        onDragLeave={() => { if (--dragDepth.current <= 0) { dragDepth.current = 0; setDragging(false); } }}
        onDrop={(event) => {
          event.preventDefault(); dragDepth.current = 0; setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void load(file);
        }}>
        <div className="canvas-wrap"><canvas id="preview" ref={canvas}
          width={PREVIEW_SIZE.width} height={PREVIEW_SIZE.height} tabIndex={0}
          className={active ? "active" : ""}
          aria-label="图片裁切预览。拖动调整位置，滚轮或双指缩放。键盘方向键移动，加减号缩放，0 重置。"
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.preventDefault(); event.currentTarget.focus({ preventScroll: true });
            event.currentTarget.setPointerCapture(event.pointerId);
            pointers.current.set(event.pointerId, point(event)); setActive(true);
          }}
          onPointerMove={pointerMove} onPointerUp={releasePointer}
          onPointerCancel={releasePointer} onLostPointerCapture={releasePointer} onKeyDown={keyboard} />
          <div className="crop-frame"><div className="crop-guides" aria-hidden="true" />
            <span id="sample-tag" className="sample-tag" hidden={!metadata.sample}>默认画面</span></div></div>
        <div className="drop-overlay">松开以更换图片</div>
      </div>
      <div className="image-row"><span className="image-info"><ImageIcon aria-hidden="true" />
        <span><strong id="file-name">{metadata.name}</strong><small id="image-size">{metadata.description}</small></span></span>
      </div>
      <p id="image-error" className="inline-error" role="alert" hidden={!imageError}>{imageError}</p>
    </section>;
}

/** Image actions sit directly below the crop preview. */
export function ImageActions() {
  const { state: { source, upload }, load, send, downloadPng } = useContext(EditorContext)!;
  const input = useRef<HTMLInputElement>(null);
  const sending = upload.kind === "working";
  const SendIcon = UPLOAD_ICONS[upload.kind];
  return <>
    <button id="choose-image" className="button secondary" type="button" onClick={() => input.current!.click()}>
      <ImageIcon aria-hidden="true" />选择图片
    </button>
    <input id="file-input" ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden
      onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void load(file); event.currentTarget.value = ""; }} />
    <button id="download-png" className="button secondary" type="button" disabled={!source}
      onClick={() => { void downloadPng(); }}><Download aria-hidden="true" />下载 PNG</button>
    <form id="send-form" onSubmit={(event) => { event.preventDefault(); void send(); }}>
      <button id="send" className="button primary" type="submit" disabled={!source || sending}
        data-state={upload.kind} aria-live="polite" aria-busy={sending}>
        <span id="send-icon"><SendIcon aria-hidden="true" /></span>
        <span id="send-label">{UPLOAD_LABELS[upload.kind]}</span><ArrowRight aria-hidden="true" />
      </button>
      <p id="send-feedback" className="send-feedback" role="status" aria-live="polite"
        hidden={!upload.message || upload.kind === "working"} data-state={upload.kind}>{upload.message}</p>
    </form>
  </>;
}
