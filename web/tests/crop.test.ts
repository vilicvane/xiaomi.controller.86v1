import assert from "node:assert/strict";
import { test } from "node:test";
import { constrain, sourceRect, zoomAt } from "../src/crop.ts";

test("portrait and landscape fill the frame without blank margins at each edge", () => {
  for (const size of [
    { width: 600, height: 1200 },
    { width: 1200, height: 400 },
    { width: 480, height: 320 },
  ]) {
    for (const zoom of [1, 2, 5])
      for (const direction of [-1, 1]) {
        const crop = constrain(
          { zoom, x: direction * 9999, y: direction * 9999 },
          size,
        );
        const rect = sourceRect(crop, size);
        assert(rect.x >= -1e-10 && rect.y >= -1e-10);
        assert(rect.x + rect.width <= size.width + 1e-10);
        assert(rect.y + rect.height <= size.height + 1e-10);
        assert(Math.abs(rect.width / rect.height - 1.5) < 1e-10);
      }
  }
});
test("zoom at a cursor preserves its source pixel before edge constraints", () => {
  const size = { width: 960, height: 640 },
    crop = { zoom: 2, x: 0, y: 0 },
    point = { x: 70, y: -40 };
  const next = zoomAt(crop, 3, point, size);
  const before = sourceRect(crop, size),
    after = sourceRect(next, size);
  const sx = (rect: typeof before) =>
    rect.x + ((point.x + 240) / 480) * rect.width;
  const sy = (rect: typeof before) =>
    rect.y + ((point.y + 160) / 320) * rect.height;
  assert(Math.abs(sx(before) - sx(after)) < 1e-10);
  assert(Math.abs(sy(before) - sy(after)) < 1e-10);
});
test("zooming out clamps pan and restores the center at the cover limit", () => {
  const size = { width: 960, height: 640 };
  assert.deepEqual(
    zoomAt({ zoom: 3, x: 350, y: -200 }, 0, { x: 0, y: 0 }, size),
    { zoom: 1, x: 0, y: 0 },
  );
  assert.equal(constrain({ zoom: 100, x: 0, y: 0 }, size).zoom, 5);
});
