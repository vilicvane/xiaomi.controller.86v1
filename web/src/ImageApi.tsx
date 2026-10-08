import { ArrowRight, CodeXml } from "lucide-react";
import { usePanel } from "./panel-context.tsx";

export function ImageApi() {
  const { endpoint } = usePanel();
  const url = `${endpoint ?? "http://PANEL_IPV4:18086"}/api/image`;
  return <section className="api card" id="api" aria-labelledby="api-title">
    <div className="api-heading"><span className="api-icon"><CodeXml aria-hidden="true" /></span>
      <h2 id="api-title">图片上传 API</h2><span className="api-badge">HTTP</span></div>
    <div className="api-body">
      <dl className="request-fields">
        <div><dt>Method</dt><dd><code className="method">POST</code></dd></div>
        <div><dt>URL</dt><dd><code id="api-url">{url}</code></dd></div>
        <div><dt>Content-Length</dt><dd>文件实际字节数，最大 <code>1 MiB</code></dd></div>
        <div><dt>Payload</dt><dd>完整的 480 × 320 PNG 或 JPEG 文件</dd></div>
      </dl>
      <div>
        <p>将图片裁切缩放为 <strong>480 × 320</strong> 后，直接发送图片文件即可，不需要专用头部或 Content-Type。
          网页下载的 PNG 可直接用于 API；网页发送时会检查固件能力，旧版设备仍使用 VIMG。</p>
        <h3>cURL 示例</h3>
        <pre className="api-example"><code id="api-curl">{`curl -X POST "${url}" --data-binary "@xiaomi-panel-github-480x320.png"`}</code></pre>
        <p>保留文件名前的 <code>@</code>，它表示让 cURL 读取本地文件内容。只将 <code>@</code> 后面的文件名或路径
          替换为下载的 <code>.png</code> 文件，或其他符合格式要求的 JPEG。cURL 会自动发送 Content-Length。
          旧版固件的 VIMG 用法见完整协议。</p>
        <p><code>202</code> 表示面板已接收并排队显示。图片保存在 RAM，重启后清除。</p>
        <a className="text-link" href="https://github.com/vilicvane/xiaomi.controller.86v1/blob/main/docs/http-image-api.md"
          target="_blank" rel="noopener noreferrer">完整协议 <ArrowRight aria-hidden="true" /></a>
      </div>
    </div>
  </section>;
}
