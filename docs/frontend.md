# 小米智能家庭面板自定义锁屏

页面源码在 [web](../web/README.md)，使用 Vite 和 TypeScript 构建为静态文件。
目标画面固定为 480×320、横向 3:2；裁切、缩放和 RGB565 转换都在用户的浏览器执行。
面板接收的是处理完成的像素，不负责 PNG/JPEG 解码。

页面从编辑工作区开始，默认显示此前设备端的 GitHub 卡片，保留 GitHub 标志、
`vilicvane`、完整项目名称和金色星标提示。页面主题采用克制的深灰色 `#303b4b`，
默认 GitHub 图片保留原来的金色；直接进入工作区，不先展示大段介绍标题。
默认画面可直接发送，也可由本地图片替换。

默认 [github-card.png](../web/public/github-card.png)由第一方离线绘图生成，不是设备 dump。
其 SHA-256 为 `ec1af029dc4492a8a09d8e4d985b3266434b05458d407167b3bddb710154c59e`。

API 指南保持展开可见，按 METHOD、URL、PAYLOAD 呈现请求方法、设备目标 URL 和
body 格式，并提供可复制的 cURL 示例，直接发送下载的 `.vimg` 文件。完整二进制定义
仍由 [HTTP 图片 API](http-image-api.md)维护。

操作图标使用按需导入的 `lucide@1.52.0`，favicon 也由库内图标生成；GitHub 品牌 SVG
保留。网页 GitHub 链接不再带星号，默认 GitHub 图片内的金色星标提示保持不变。

## 使用路径

1. 使用默认 GitHub 画面，或选择/拖入本地 PNG、JPEG、WebP、SVG；单文件最大 32MiB，动图使用静态首帧。
2. 拖动调整构图，用滚轮、双指或键盘 `+`/`-` 调整 1～5 倍覆盖比例；裁切框固定为 3:2，始终填满。
3. 双击面板自定义画面，查看 IP 与端口；在页面填写该地址。
4. 将处理后的画面发送到面板，或下载 480×320 PNG 和完整 `.vimg` Payload 到本地。

编辑区支持键盘方向键移动、`+`/`-` 缩放和 `0` 重置。导出的画面与当前裁切构图一致。
页面的 canvas 采用 `pixelated` 展示；当源像素被放大时关闭绘制插值，避免把像素边缘
抹平。较大的照片缩小时保留高质量过滤。页面没有缩放或重置栏，直接使用手势和键盘。

预览画布为 544×384，中央裁切区域为 480×320，四边各留 32 像素。整图延伸到框外，
框外覆盖 55% 黑色遮罩，便于调整构图。中央区域从导出/发送使用的 480×320 画布以
1:1 复制，框外预览不进入最终图像；响应式显示不改变目标分辨率。

发送按钮有待发送、发送中、已接收和失败四种状态。额外解释只在失败或发送期间继续
编辑/修改地址时显示，没有独立的“等待发送”行。页面保留同一局域网和浏览器授权说明。

设备地址也可通过 URL fragment 提供：`#device=` 后接编码过的 `http://PANEL_IPV4:18086`。
它与固件 `303 Location` 的 fragment 格式一致，不使用 query 参数向静态站点服务端传递
设备地址。页面和面板须能在同一局域网直接通信；Cloudflare 仅托管页面静态文件。

没有云端图片存储、服务端代理、账户或设备 token。图片只有用户点击发送后才离开浏览器，
目标为用户填写的面板；本地处理和下载可以在没有连接面板时使用。

## 像素与上传语义

浏览器把裁切结果转换为 RGB565LE，按 [HTTP 图片 API](http-image-api.md) 生成 VIMG header
和 FNV-1a 校验和，发送 `POST /api/image`。固定请求 body 为 307216B。
地址页收到新图片时仍保持地址页，双击返回图片可查看新画面。

当前下载的 `.vimg` 就是完整请求 body：16B VIMG header 加 307200B RGB565LE 像素，
校验和已填写，总长 307216B。PNG 用于查看或继续编辑，不能直接作为上传 body；
页面不再提供仅像素的 raw RGB565 下载。文件名保留原图名称并追加 `-480x320` 和格式后缀。

将面板地址和文件名替换后可直接调用：

```sh
curl -X POST "http://PANEL_IPV4:18086/api/image" -H "Content-Type: application/octet-stream" --data-binary "@picture-480x320.vimg"
```

保留 `@` 前缀，它表示读取本地文件内容；只替换后面的文件名或路径。
Content-Type header 用于当前已安装的严格版本；维护源码已取消类型限制，下一独立
发布安装后可省略它。

`202` 仅确认完整图像已接受并排队供 GUI 消费，不证明 LCD 扫描已经完成；图片仅存于
RAM，不是保存到 Flash。连接中断或浏览器没有收到响应时，结果可能不确定，不能报告成功。
页面不会自动重复发送来掩盖失败。

已安装 `maintained-http-four-page-20261007-c` 可直接接受该 HTTP API，无需新刷写。
它的前端 URL 仍为空，访问设备根地址目前返回说明页。未来实际域名确定后，可以用
`PANEL_FRONTEND_URL` 和 `PANEL_FRONTEND_ORIGIN` 构建新的、独立冻结的维护 release，
使设备根地址跳转到该页面；不能修改已冻结 release 的输入。

## 本地开发

使用 Node.js 24，从仓库根目录运行：

```powershell
npm --prefix web install
npm --prefix web run dev
npm --prefix web run test
npm --prefix web run build
```

发布构建使用 lockfile：`npm --prefix web ci` 后执行测试和构建。
`build` 先做 TypeScript 检查，再生成 Vite 静态产物；`test` 使用 Node 的 TypeScript 测试。
`web/dist` 为静态输出；`web/node_modules` 与构建产物不入库。
API 文档无需连接设备即可阅读，上传需要使用当前非零设备地址。

## Cloudflare Pages

后续连接仓库时使用以下设置，当前未创建线上站点或指定实际域名：

| 设置 | 值 |
| --- | --- |
| Root directory | `web` |
| Build command | `npm ci && npm run build` |
| Build output directory | `dist` |

目录和静态输出设置遵循 [Cloudflare Pages 构建配置](https://developers.cloudflare.com/pages/configuration/build-configuration/)。
不需要 Pages Functions、Worker 图片代理或服务端凭据。

浏览器上传要求页面和面板处于可互访的局域网，并允许页面访问本地网络。
Chrome 142 引入该权限；对 private IP literal 的请求在授权后可获得 mixed-content 豁免，见
[Chrome 本地网络访问说明](https://developer.chrome.com/blog/local-network-access?hl=en)。
当前已实现的 CORS 不能代替此权限。线上 HTTPS 域名还没有部署或验证；实际浏览器版本
和网络条件需要单独验收。上传失败时检查面板地址、同一局域网及浏览器授权，或下载
完整 Payload 后使用上述 cURL 命令。编辑和下载不依赖设备连接。

## 验证范围

2026-10-07 已用 Windows Chrome 验证本地 HTTP 页面到面板的真实上传，收到 202，
并逐字节确认请求像素与导出的 RGB565 相同、FNV 正确。纵向 SVG 的居中裁切和拖动
位置通过独立像素检查；按钮/键盘缩放、重置、双指 2 倍缩放、480×320 PNG 和
307200B RGB565 导出通过。初版 390px 手机布局没有横向溢出，旧版 API 折叠区域可
展开，无页面错误。这些检查保留为初次验证，与新版布局的检查分列。

另用浏览器里的延迟 202 模拟验证上传期间继续编辑或修改地址：成功反馈仍指向
实际发送的画面快照及原目标。它不增加真实设备上传的验证范围。
结果见 [前端浏览器验证](../web/browser-verification-20261007.json)。线上 HTTPS 到 LAN 和
Cloudflare 部署尚未验证；HTTP 202 也不能代替实屏观察或证明 LCD 扫描完成。

新版默认 GitHub 画面与 PNG 逐像素一致；深灰主题、准确应用名称、17px 小标题、
直接进入工作区及常显 METHOD/URL/PAYLOAD 均已在 Chrome 检查。110% 放大时绘制插值
关闭，默认卡片仍只含原有四种颜色；滚轮、双指、键盘缩放与 `0` 重置通过，390px 和
360px 布局没有横向溢出。fragment 首次加载能同步填写设备地址和 API URL，无页面错误。
本轮布局检查没有再上传设备或修改固件，保留初次真实 HTTP 上传的原范围。
最新调整已移除整个缩放和重置栏；滚轮、双指及键盘功能通过画面变化与重置后恢复
基准图的检查，结果另列在验证记录中。

此前 raw RGB565 下载版本的普通浏览器测试已确认落盘文件名：默认画面为
`xiaomi-panel-github-lockscreen-480x320.png`，测试图片导出为 `旅行照片-480x320.rgb565`
且大小为 307200B。命名沿用原图名称并附尺寸及格式后缀。

最新框外遮罩预览和完整 `.vimg` Payload 已在 Chrome 单独验证：544×384 预览的中央
绿像素保持 255，框外红/蓝像素变为 115，与 55% 黑色遮罩一致；PNG 与内框逐像素
相同，27 组尺寸/缩放/角落组合检查通过。拦截导出的 `.vimg` Blob 为 307216B，文件名
属性为 `旅行照片-480x320.vimg`，尺寸、长度、FNV 和纯绿像素均独立检查通过；模拟
HTTP 请求与该完整 Payload 逐字节相同。

四种发送状态、发送中禁用、正常成功无额外反馈、422 错误解释、发送期间编辑的准确
反馈及后续编辑返回待发送状态通过。无独立等待行、云端提示和网页 GitHub 星号，
常显 API/cURL、Lucide 操作图标、滚轮/双指/键盘、移动布局和 fragment 再次检查通过，
无页面错误。记录见 `payload_margin_revision`。本轮使用模拟 HTTP 和拦截 Blob/下载
属性，没有真实设备上传或 `.vimg` 的普通浏览器落盘验证，不借用此前 raw 下载结论。

设备双击地址和原系统息屏唤醒已由用户在 2026-10-07 确认正常；其他交互仍按当前
发布结果独立记录，没有进行或要求完整断电测试。
