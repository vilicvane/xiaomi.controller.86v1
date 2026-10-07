export type Size = { width: number; height: number };
export type Point = { x: number; y: number };
export type Crop = { zoom: number; x: number; y: number };
export const FRAME: Size = { width: 480, height: 320 };
export const MAX_ZOOM = 5;

export function coverScale(size: Size): number {
  return Math.max(FRAME.width / size.width, FRAME.height / size.height);
}

export function constrain(crop: Crop, size: Size): Crop {
  const zoom = Math.max(1, Math.min(MAX_ZOOM, crop.zoom));
  const scale = coverScale(size) * zoom;
  const maxX = Math.max(0, (size.width * scale - FRAME.width) / 2);
  const maxY = Math.max(0, (size.height * scale - FRAME.height) / 2);
  return {
    zoom,
    x: maxX ? Math.max(-maxX, Math.min(maxX, crop.x)) : 0,
    y: maxY ? Math.max(-maxY, Math.min(maxY, crop.y)) : 0,
  };
}

/** Keep the image point under the cursor fixed, until it reaches the frame edge. */
export function zoomAt(
  crop: Crop,
  zoom: number,
  anchor: Point,
  size: Size,
): Crop {
  const nextZoom = Math.max(1, Math.min(MAX_ZOOM, zoom));
  const ratio = nextZoom / crop.zoom;
  return constrain(
    {
      zoom: nextZoom,
      x: anchor.x - (anchor.x - crop.x) * ratio,
      y: anchor.y - (anchor.y - crop.y) * ratio,
    },
    size,
  );
}

export function sourceRect(crop: Crop, size: Size) {
  const scale = coverScale(size) * crop.zoom;
  return {
    x: (size.width - FRAME.width / scale) / 2 - crop.x / scale,
    y: (size.height - FRAME.height / scale) / 2 - crop.y / scale,
    width: FRAME.width / scale,
    height: FRAME.height / scale,
  };
}
