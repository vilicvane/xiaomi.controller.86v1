import { ArrowRight, Image as ImageIcon, RefreshCw, Save } from "lucide-react";
import { usePanel } from "./panel-context.tsx";

export function ImageApi() {
  const { endpoint } = usePanel();
  const address = endpoint ?? "http://192.0.2.1:18086";
  const imageUrl = `${address}/api/image`;
  const settingsUrl = `${address}/api/settings`;
  const settingsJson = '{"return_after_seconds":60}';

  return <section className="api-page" id="api-page" aria-labelledby="api-image-title">
    <p className="api-intro">{endpoint
      ? "以下示例使用已配置的面板地址。"
      : "以下示例使用文档地址 192.0.2.1:18086，请替换为面板显示的地址。"}
      </p>

    <section className="api card" id="api-image" aria-labelledby="api-image-title">
      <div className="api-heading"><span className="api-icon"><ImageIcon aria-hidden="true" /></span>
        <h2 id="api-image-title">上传图片</h2><span className="api-badge">POST</span></div>
      <div className="api-body">
        <dl className="request-fields">
          <div><dt>Method</dt><dd><code className="method">POST</code></dd></div>
          <div><dt>URL</dt><dd><code id="api-url">{imageUrl}</code></dd></div>
          <div><dt>Content-Length</dt><dd>准确的文件字节数，<code>1–1048576</code>（1 MiB）</dd></div>
          <div><dt>Payload</dt><dd>完整的 480 × 320 PNG 或 JPEG 文件</dd></div>
        </dl>
        <div>
          <p>PNG 为 8-bit、非交错静态图片；JPEG 为 8-bit baseline 单扫描，支持灰度和
            三分量 4:4:4、4:2:2、4:2:0。不支持 progressive JPEG。面板不会自动裁切或缩放。</p>
          <p>直接发送文件内容，不使用 multipart 或专用头部，不需要 Content-Type。
            网页下载的 PNG 可直接使用；设备按文件签名识别格式并检查完整图像。</p>
          <h3>cURL 示例</h3>
          <pre className="api-example"><code id="api-curl">{`curl --data-binary "@xiaomi-panel-github-480x320.png" "${imageUrl}"`}</code></pre>
          <p>保留文件名前的 <code>@</code>，替换它后面的文件名或路径。cURL 自动提供
            Content-Length；Windows PowerShell 中使用 <code>curl.exe</code>。</p>
          <dl className="api-statuses">
            <div><dt><code>202</code></dt><dd>完整图像已校验并在 RAM 排队，重启后清除；不代表 LCD 已完成显示。</dd></div>
            <div><dt><code>411 / 413</code></dt><dd>缺少 Content-Length，或文件超过大小限制。</dd></div>
            <div><dt><code>415 / 422</code></dt><dd>格式或编码不支持，或尺寸、内容校验失败；不会替换当前图片。</dd></div>
            <div><dt><code>503</code></dt><dd>设备资源或发布暂不可用，请确认后手动重试。</dd></div>
          </dl>
          <p><code>GET /api/image</code> 成功时返回 <code>200</code> 和
            <code>{'{"formats":["png","jpeg","vimg"]}'}</code>。
            网页仅在发送时查询能力；旧固件明确返回 404 才使用 VIMG，不在失败 POST 后换格式重发。</p>
          <a className="text-link" href="https://github.com/vilicvane/xiaomi.controller.86v1/blob/main/docs/http-image-api.md"
            target="_blank" rel="noopener noreferrer">图片格式与完整协议 <ArrowRight aria-hidden="true" /></a>
        </div>
      </div>
    </section>

    <section className="api card" id="api-settings-read" aria-labelledby="api-settings-read-title">
      <div className="api-heading"><span className="api-icon"><RefreshCw aria-hidden="true" /></span>
        <h2 id="api-settings-read-title">读取自动返回</h2><span className="api-badge">GET</span></div>
      <div className="api-body">
        <dl className="request-fields">
          <div><dt>Method</dt><dd><code className="method">GET</code></dd></div>
          <div><dt>URL</dt><dd><code id="settings-get-url">{settingsUrl}</code></dd></div>
          <div><dt>Payload</dt><dd>无请求 body</dd></div>
        </dl>
        <div>
          <pre className="api-example"><code>{`curl "${settingsUrl}"`}</code></pre>
          <p><code>200</code> 返回当前等待时间，单位为整数秒。例如：</p>
          <pre className="api-example"><code>{settingsJson}</code></pre>
          <p><code>0</code> 关闭定时返回；<code>60</code> 表示原界面连续 60 秒未触摸后返回
            自定义图片。只计触屏，物理按键不会重置计时，原系统息屏规则独立生效。</p>
        </div>
      </div>
    </section>

    <section className="api card" id="api-settings-save" aria-labelledby="api-settings-save-title">
      <div className="api-heading"><span className="api-icon"><Save aria-hidden="true" /></span>
        <h2 id="api-settings-save-title">保存自动返回</h2><span className="api-badge">POST</span></div>
      <div className="api-body">
        <dl className="request-fields">
          <div><dt>Method</dt><dd><code className="method">POST</code></dd></div>
          <div><dt>URL</dt><dd><code id="settings-post-url">{settingsUrl}</code></dd></div>
          <div><dt>Content-Length</dt><dd>准确的 JSON 字节数，<code>1–64</code></dd></div>
          <div><dt>Payload</dt><dd>只有 <code>return_after_seconds</code> 一个成员的 JSON 对象，值为 0–3600 的整数</dd></div>
        </dl>
        <div>
          <p>将以下内容保存为无 BOM 的 UTF-8 文件 <code>settings.json</code>，然后发送文件：</p>
          <pre className="api-example"><code>{settingsJson}</code></pre>
          <pre className="api-example"><code>{`curl --data-binary "@settings.json" "${settingsUrl}"`}</code></pre>
          <p><code>200</code> 在设置写入、同步并读回确认后返回同一 JSON 结构，设置在重启后保留。</p>
          <dl className="api-statuses">
            <div><dt><code>400</code></dt><dd>请求或 JSON 无效，包括多余成员、负数或小数。</dd></div>
            <div><dt><code>422 / 413</code></dt><dd>整数超过 3600 秒，或 body 超过 64 字节。</dd></div>
            <div><dt><code>409</code></dt><dd>设置路径存在其他文件，不覆盖该文件。</dd></div>
            <div><dt><code>503</code></dt><dd>文件系统或保存确认失败。</dd></div>
          </dl>
          <p>未收到确认时，设置可能已保存；失败不承诺旧持久化值保持不变。
            先手动重新读取确认，不自动重复 POST。</p>
          <a className="text-link" href="https://github.com/vilicvane/xiaomi.controller.86v1/blob/main/docs/auto-return.md#设置-api"
            target="_blank" rel="noopener noreferrer">自动返回与完整设置协议 <ArrowRight aria-hidden="true" /></a>
        </div>
      </div>
    </section>
  </section>;
}
