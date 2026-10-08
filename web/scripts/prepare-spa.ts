import { copyFile } from "node:fs/promises";

await copyFile(
  new URL("../dist-cloudflare/xiaomi-86v1/index.html", import.meta.url),
  new URL("../dist-cloudflare/index.html", import.meta.url),
);
