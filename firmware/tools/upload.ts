import { readFileSync } from 'node:fs';
import { isIP } from 'node:net';
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

async function main() {
  const [address, input] = process.argv.slice(2);
  if (!address || isIP(address) !== 4 || !input || process.argv.length !== 4)
    throw new Error('Usage: node firmware/tools/upload.ts PANEL_IPV4 picture.rgb565|--pattern');
  const pixels = input === '--pattern' ? testPattern() : readFileSync(input);
  const response = await fetch(`http://${address}:18086/api/image`, {
    method: 'POST',
    body: imageBody(pixels), signal: AbortSignal.timeout(60000),
  });
  if (response.status !== 202) throw new Error(`Panel rejected upload: HTTP ${response.status}`);
  console.log('HTTP 202: image accepted; this is not a display-completion acknowledgement.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await main();
