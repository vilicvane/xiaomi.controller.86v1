import { readFileSync } from 'node:fs';
import { isIP } from 'node:net';
import { extname } from 'node:path';
import { pathToFileURL } from 'node:url';

export function imageBody(pixels: Uint8Array): Buffer {
  if (pixels.length !== 480 * 320 * 2) throw new Error('Expected exactly 307200 bytes of RGB565LE pixels');
  const body = Buffer.alloc(16 + pixels.length);
  body.write('VIMG');
  body.writeUInt16LE(480, 4);
  body.writeUInt16LE(320, 6);
  body.writeUInt32LE(pixels.length, 8);
  let checksum = 0x811c9dc5;
  for (const byte of pixels) checksum = Math.imul(checksum ^ byte, 0x01000193) >>> 0;
  body.writeUInt32LE(checksum, 12);
  body.set(pixels, 16);
  return body;
}

function testPattern(): Buffer {
  const pixels = Buffer.alloc(480 * 320 * 2);
  const colors = [0xf800, 0x07e0, 0x001f, 0xffe0];
  for (let y = 0; y < 320; y++) {
    for (let x = 0; x < 480; x++) {
      const color = Math.abs(y - x * 320 / 480) < 3 ? 0xffff : colors[Math.floor(x / 120)];
      pixels.writeUInt16LE(color, 2 * (y * 480 + x));
    }
  }
  return pixels;
}

type ImageFormat = 'png' | 'jpeg' | 'vimg';
const MAX_IMAGE_BYTES = 1024 * 1024;

function imageFormat(body: Uint8Array): ImageFormat {
  if (body.length < 1 || body.length > MAX_IMAGE_BYTES)
    throw new Error('Image body must contain 1..1048576 bytes');
  if ([137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => body[index] === byte))
    return 'png';
  if (body[0] === 255 && body[1] === 216) return 'jpeg';
  if (body[0] === 86 && body[1] === 73 && body[2] === 77 && body[3] === 71) {
    if (body.length !== 307216) throw new Error('VIMG must contain exactly 307216 bytes');
    return 'vimg';
  }
  throw new Error('Expected a PNG, JPEG or complete VIMG file');
}

/** Standard files keep their exact bytes; the .rgb565 suffix explicitly selects legacy raw pixels. */
export function uploadFileBody(bytes: Uint8Array, filename: string): Buffer {
  if (extname(filename).toLowerCase() === '.rgb565') return imageBody(bytes);
  imageFormat(bytes);
  return Buffer.from(bytes);
}

/** One POST, with a preceding read-only capability probe for standard image files. */
export async function uploadImage(
  address: string,
  body: Uint8Array,
  fetcher: typeof fetch = fetch,
): Promise<void> {
  if (isIP(address) !== 4) throw new Error('Expected a dotted-decimal panel IPv4 address');
  const format = imageFormat(body);
  const url = `http://${address}:18086/api/image`;
  if (format !== 'vimg') {
    let capability: Response;
    try {
      capability = await fetcher(url, {
        method: 'GET', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new Error('Cannot read image capabilities; no image was uploaded. Check the network before manually retrying.');
    }
    if (capability.status === 404)
      throw new Error('This installed firmware accepts VIMG only. Update the firmware for direct PNG/JPEG upload; no image was uploaded.');
    if (capability.status !== 200)
      throw new Error(`Image capability request failed: HTTP ${capability.status}; no image was uploaded.`);
    let formats: unknown;
    try {
      const value: unknown = await capability.json();
      formats = (value as { formats?: unknown } | null)?.formats;
    } catch {
      throw new Error('Invalid image capability response; no image was uploaded.');
    }
    if (!Array.isArray(formats) || formats.some((value) => typeof value !== 'string'))
      throw new Error('Invalid image capability response; no image was uploaded.');
    if (!formats.includes(format))
      throw new Error(`The panel does not advertise ${format.toUpperCase()} support; no image was uploaded.`);
  }
  let response: Response;
  try {
    response = await fetcher(url, {
      method: 'POST', body: Buffer.from(body), redirect: 'error', signal: AbortSignal.timeout(60000),
    });
  } catch {
    throw new Error('No upload confirmation received; the image may have been accepted. Check the panel before manually retrying.');
  }
  if (response.status !== 202) throw new Error(`Panel rejected upload: HTTP ${response.status}`);
}

async function main() {
  const [address, input] = process.argv.slice(2);
  if (!address || isIP(address) !== 4 || !input || process.argv.length !== 4)
    throw new Error('Usage: node firmware/tools/upload.ts PANEL_IPV4 picture.png|picture.jpg|picture.vimg|picture.rgb565|--pattern');
  const body = input === '--pattern' ? imageBody(testPattern()) : uploadFileBody(readFileSync(input), input);
  await uploadImage(address, body);
  console.log('HTTP 202: image accepted; this is not a display-completion acknowledgement.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await main();
