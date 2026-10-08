import { FRAME, sourceRect, type Crop, type Size } from "./crop.ts";
import { imageBody, rgbaToRgb565 } from "./panel-api.ts";

export type EditorImage = ImageBitmap | HTMLImageElement;
export const PREVIEW_MARGIN = 32;
export const PREVIEW_SIZE = {
  width: FRAME.width + 2 * PREVIEW_MARGIN,
  height: FRAME.height + 2 * PREVIEW_MARGIN,
};

export function renderFrame(
  canvas: HTMLCanvasElement,
  source: EditorImage,
  size: Size,
  crop: Crop,
) {
  if (canvas.width !== FRAME.width) canvas.width = FRAME.width;
  if (canvas.height !== FRAME.height) canvas.height = FRAME.height;
  const context = canvas.getContext("2d", { willReadFrequently: true })!;
  const rect = sourceRect(crop, size);
  context.fillStyle = "#000";
  context.fillRect(0, 0, FRAME.width, FRAME.height);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(source, rect.x, rect.y, rect.width, rect.height,
    0, 0, FRAME.width, FRAME.height);
}

export function frameSnapshot(source: EditorImage, size: Size, crop: Crop) {
  const canvas = document.createElement("canvas");
  renderFrame(canvas, source, size, crop);
  return canvas;
}

export function renderPreview(
  canvas: HTMLCanvasElement,
  frame: HTMLCanvasElement,
  source: EditorImage,
  size: Size,
  crop: Crop,
) {
  renderFrame(frame, source, size, crop);
  const context = canvas.getContext("2d")!;
  const scale = FRAME.width / sourceRect(crop, size).width;
  context.fillStyle = "#101010";
  context.fillRect(0, 0, PREVIEW_SIZE.width, PREVIEW_SIZE.height);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(source,
    PREVIEW_MARGIN + (FRAME.width - size.width * scale) / 2 + crop.x,
    PREVIEW_MARGIN + (FRAME.height - size.height * scale) / 2 + crop.y,
    size.width * scale, size.height * scale);
  // Keep the actual panel pixels intact; CSS enlarges them with pixelated sampling.
  context.imageSmoothingEnabled = false;
  context.drawImage(frame, PREVIEW_MARGIN, PREVIEW_MARGIN);
  context.fillStyle = "rgba(0, 0, 0, 0.55)";
  context.fillRect(0, 0, PREVIEW_SIZE.width, PREVIEW_MARGIN);
  context.fillRect(0, PREVIEW_MARGIN + FRAME.height, PREVIEW_SIZE.width, PREVIEW_MARGIN);
  context.fillRect(0, PREVIEW_MARGIN, PREVIEW_MARGIN, FRAME.height);
  context.fillRect(PREVIEW_MARGIN + FRAME.width, PREVIEW_MARGIN, PREVIEW_MARGIN, FRAME.height);
}

export function pngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("无法生成 PNG 图片，尚未上传。"));
    }, "image/png");
  });
}

export function vimgBody(canvas: HTMLCanvasElement): Uint8Array<ArrayBuffer> {
  const context = canvas.getContext("2d", { willReadFrequently: true })!;
  return imageBody(rgbaToRgb565(context.getImageData(0, 0, FRAME.width, FRAME.height).data));
}
