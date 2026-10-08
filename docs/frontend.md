# 86V1 自定义固件：图片编辑前端

本页面用于 86V1 自定义固件的图片下拉屏幕功能。页面源码在 [web](../web/README.md)，
使用 Vite 和 TypeScript 构建为静态文件，Navigo 管理页面路由；网页显示名称为“小米智能家庭面板”。
目标画面固定为 480×320、横向 3:2；裁切、缩放和 RGB565 转换都在用户的浏览器执行。
当前固件的图片接收程序处理已完成的像素，不解码 PNG/JPEG。
a 的自动返回设置接口、真实读写与暖复位加载通过；设置页导航是后续网页维护，
固件和用户观察范围保持原记录，不用网页改版推定实机验收。

页面从编辑工作区开始，默认显示此前设备端的 GitHub 卡片，保留 GitHub 标志、
`vilicvane`、完整项目名称和金色星标提示。页面主题采用克制的深灰色 `#303b4b`，
默认 GitHub 图片保留原来的金色；直接进入工作区，不先展示大段介绍标题。
默认画面可直接发送，也可由本地图片替换。

面向设备使用者的入口是 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)。
首次准备调试器、接线、备份、配置和维护升级见
[刷写与配置指南](flashing.md)。当前安装器依赖本机的精确基线和私有
冻结材料，不能把网页发布或源码 clone 当作通用原厂首刷入口。

默认 [github-card.png](../web/public/github-card.png)由第一方离线绘图生成，不是设备 dump。
其 SHA-256 为 `ec1af029dc4492a8a09d8e4d985b3266434b05458d407167b3bddb710154c59e`。

API 指南保持展开可见，按 METHOD、URL、PAYLOAD 呈现请求方法、设备目标 URL 和
body 格式，并提供可复制的 cURL 示例，直接发送下载的 `.vimg` 文件。完整二进制定义
仍由 [HTTP 图片 API](http-image-api.md)维护。

操作图标使用按需导入的 `lucide@1.52.0`，GitHub 品牌 SVG 保留。favicon 按实物描绘
黑色玻璃、横向屏幕及底部白色三连键，浏览器直接使用第一方 SVG，并检查 16/32 像素下的渲染。
网页 GitHub 链接不带星号，默认 GitHub 图片内的金色星标提示保持不变。

## 使用路径

1. 使用默认 GitHub 画面，或选择/拖入本地 PNG、JPEG、WebP、SVG；单文件最大 32MiB，动图使用静态首帧。
2. 拖动调整构图，用滚轮、双指或键盘 `+`/`-` 调整 1～5 倍覆盖比例；裁切框固定为 3:2，始终填满。
3. 双击面板自定义画面，查看 IP 与端口；在页面填写该地址。
4. 将处理后的画面发送到面板，或下载 480×320 PNG 和完整 `.vimg` Payload 到本地。

编辑区支持键盘方向键移动、`+`/`-` 缩放和 `0` 重置。导出的画面与当前裁切构图一致。
源图按当前构图经过高质量重采样生成 480×320 成品，放大、缩小及非整数移动都使用
插值。预览 canvas 继续采用 `pixelated` 展示这些成品像素，模拟面板的像素数量。
页面没有缩放或重置栏，直接使用手势和键盘。

预览画布为 544×384，中央裁切区域为 480×320，四边各留 32 像素。整图延伸到框外，
框外覆盖 55% 黑色遮罩，便于调整构图。中央区域从导出/发送使用的 480×320 画布以
1:1 复制，框外预览不进入最终图像；响应式显示不改变目标分辨率。

发送按钮有待发送、发送中、已接收和失败四种状态。额外解释只在失败或发送期间继续
编辑/修改地址时显示，没有独立的“等待发送”行。页面保留同一局域网和浏览器授权说明。

设备地址也可通过 URL 查询参数提供：`?device=` 后接编码过的 `http://PANEL_IPV4:18086`，例如
`https://wan.sh/xiaomi-86v1/?device=http%3A%2F%2FPANEL_IPV4%3A18086`。
此前 g 的 `303 Location` 使用同一格式，真实跳转与 Chrome 地址填入已验证。
a 沿用相同配置，实际跳转结果由新发布独立记录。
页面和面板须能在同一局域网直接通信；Cloudflare 仅托管页面静态文件。

没有云端图片存储、服务端代理、账户或设备 token。图片只有用户点击发送后才离开浏览器，
目标为用户填写的面板；本地处理和下载可以在没有连接面板时使用。

## 自动返回设置

页面导航提供“画面”和“设置”。图片编辑位于 `/xiaomi-86v1/`，自动返回位于独立的
`/xiaomi-86v1/settings` 页面，支持直接访问和刷新；两页均读取 `?device=`。
设置页可读取或保存原界面未触摸后的等待时间，默认 60 秒，0 关闭，最大 3600 整数秒。
只计触摸屏，物理键不重置；原系统息屏返回独立生效。设置保存到 MMC 并按重启保留实现，
与 RAM 图片分开。接口和用户操作见 [自动返回说明](auto-return.md)。

`settings.ts` 复用图片客户端的地址规范化，但不改图片协议。读取和保存分别请求
GET/POST `/api/settings`，POST 声明 `application/json`；只在明确点击按钮时联网，页面
初始不伪装已读取。10 秒超时、一次请求、手动重试；保存缺少确认时提示重新读取，不能
声称一定未保存。地址变化取消并隔离旧响应，请求期间的新编辑不被读回值覆盖。
离开设置页取消未完成请求并保留输入草稿；已发出的 POST 即使被取消，也可能已由
设备保存，因此未收到确认时保留不确定状态。

19 项网页测试与 Chrome 模拟接口检查通过，涵盖范围/JSON、读写、0关闭、取消/超时、
状态按钮、旧响应和新编辑、390/360px 布局且图片预览不变。该检查没有访问面板，不能
替代 a 的实际 API 或重启保留验证，见 [a 发布结果](../firmware/releases/maintained-idle-return-20261007-a.json)。
本轮真实 GET 默认 60 秒，POST/GET 0 和 5 一致；3601 返回 422 且保留运行值 0。
保存 5 后独立 AON GLOBAL 暖复位，224B context 和 GET 重新加载为 5，随后保存回 60。
这些真实接口与暖加载结果不代替用户的网页读写、触摸延期或完整断电验收。

## 像素与上传语义

浏览器把裁切结果转换为 RGB565LE，按 [HTTP 图片 API](http-image-api.md) 生成 VIMG header
和 FNV-1a 校验和，发送 `POST /api/image`。固定请求 body 为 307216B。
地址页收到新图片时仍保持地址页，双击返回图片可查看新画面。

当前下载的 `.vimg` 就是完整请求 body：16B VIMG header 加 307200B RGB565LE 像素，
校验和已填写，总长 307216B。PNG 用于查看或继续编辑，不能直接作为上传 body；
页面不再提供仅像素的 raw RGB565 下载。文件名保留原图名称并追加 `-480x320` 和格式后缀。

将面板地址和文件名替换后可直接调用：

```sh
curl -X POST "http://PANEL_IPV4:18086/api/image" --data-binary "@picture-480x320.vimg"
```

保留 `@` 前缀，它表示读取本地文件内容；只替换后面的文件名或路径。
不需要 Content-Type；cURL 会自动计算并发送 Content-Length。

`202` 仅确认完整图像已接受并排队供 GUI 消费，不证明 LCD 扫描已经完成；图片仅存于
RAM，不是保存到 Flash。连接中断或浏览器没有收到响应时，结果可能不确定，不能报告成功。
页面不会自动重复发送来掩盖失败。

此前已安装 `maintained-http-four-page-20261007-g` 接受不指定 Content-Type 的该 HTTP API；
a 沿用图片协议和正式 URL，以下 g 的检查保留为历史证据。
访问设备根地址会 303 到 `https://wan.sh/xiaomi-86v1/`，通过 `?device=` 自动填入设备地址；
无需电脑开发服务器。真实 GET/303 与 Windows Chrome 跟随、输入框/API URL 同步通过。
用户另行确认正式页面跳转和 HTTPS 网页上传正常；随后只读状态观察到
generation/displayed_generation=1、pending=0、server=1/error=0，说明图像已由 GUI 消费。
自动化 Chrome 没有发送 POST，也没有 LCD 扫描验证。
g 的四页安装/native/GLOBAL/暖读回通过；实屏、其他交互和米家状态仍待单列验收。
配置在编译时确定，默认 URL 如上、CORS 为 `*`。更改跳转目标要创建新的独立 release；
不能修改已冻结 c/d/g release 的输入。

为正式页面构建时，URL 与浏览器 origin 分别填写：

```sh
PANEL_FRONTEND_URL=https://wan.sh/xiaomi-86v1/ \
PANEL_FRONTEND_ORIGIN='*' sh firmware/build.sh
```

URL 含子路径并保留末尾斜线。g 使用 CORS `*`，继续支持正式页面、本地开发和
workers.dev 来源；如需限定为 `https://wan.sh`，origin 不带路径，并构建新的独立 release。
该命令只生成构建材料，不能代替独立审查、冻结和实机安装。

## 本地开发

使用 Node.js 24，从仓库根目录运行：

```powershell
npm --prefix web install
npm --prefix web run dev -- --host 0.0.0.0 --port 5173 --strictPort
npm --prefix web run test
npm --prefix web run build
```

发布构建使用 lockfile：`npm --prefix web ci` 后执行测试和构建。
`build` 先做 TypeScript 检查，再生成 Vite 静态产物；`test` 使用 Node 的 TypeScript 测试。
静态输出为 `web/dist-cloudflare/xiaomi-86v1/`，资源 URL 前缀为 `/xiaomi-86v1/`；
`web/node_modules` 与构建产物不入库。构建后可用 `npm --prefix web run preview` 查看该子路径。
API 文档无需连接设备即可阅读，上传需要使用当前非零设备地址。
`0.0.0.0` 使开发服务器能从局域网访问；固定 5173 并用 `--strictPort` 避免占用时自动
更换端口。真实电脑/面板地址不提交到 Git。这个服务器仅用于开发，a 的正式网页入口
不依赖它；历史 d 的临时 LAN 跳转记录保留原范围。

## Cloudflare Workers 静态部署

网页已于 2026-10-07 发布为 Worker `xiaomi-86v1`，独立入口为
[Workers 页面](https://xiaomi-86v1.vilicvane.workers.dev/xiaomi-86v1/)，已返回 HTTP 200。
此前同页设置卡片的发布版本为 `ecf90b3d-d93f-4a09-aab7-7d5b513a9d49`。正式页面 200、四项
线上资源与当时构建字节一致，Chrome 显示设置卡片、初始零自动 LAN 请求，页面错误为 0。
这次页面检查没有请求面板；此前版本 `d92ceb00-ba7c-4832-ae9c-e00879c5ca12` 的证据保持
原范围。
独立设置页与 SPA 回退于 2026-10-08 发布，验证记录见本页末尾。
独立入口的无尾斜线路径返回 307 到 `/xiaomi-86v1/`；SVG favicon、JS、CSS 和默认 PNG
四项线上资源的字节与 SHA-256 均匹配构建产物。Windows Chrome 已验证 HTTPS 页面
标题、默认图加载，以及测试用 `?device=` 查询参数到输入框/API URL 的同步，无页面错误或
请求失败。这一静态检查没有发送面板请求、下载文件或修改固件。
目标入口 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)已能正常访问，HTTP 200、无尾
斜线路径 307、静态资源及 Chrome 页面加载和测试用 `?device=` 参数均已验证；
上述检查不包含 HTTPS 到 LAN 的上传。

| 设置 | 值 |
| --- | --- |
| 项目目录 | `web` |
| 构建输出 | `dist-cloudflare/xiaomi-86v1` |
| Worker assets directory | `dist-cloudflare` |
| 缺页处理 | `single-page-application`，根 `index.html` 由构建后复制 |
| Worker 名称 | `xiaomi-86v1` |
| 精确路径 route | `wan.sh/xiaomi-86v1` |
| 子路径 route | `wan.sh/xiaomi-86v1/*` |
| 发布命令 | `npm run deploy` |

从仓库根目录发布：

```powershell
npm --prefix web ci
npm --prefix web run test
npm --prefix web run deploy
```

`deploy` 执行 `npm run build && wrangler deploy`，Wrangler `4.148.0` 是锁定的开发依赖，
使用操作者的 Cloudflare 登录。配置见 [wrangler.jsonc](../web/wrangler.jsonc)。
目录结构与子路径一致，没有 Worker 业务代码、后端服务或图片中转。构建末尾执行
[prepare-spa.ts](../web/scripts/prepare-spa.ts)，将嵌套页面字节复制到资源根 `index.html`；
官方 SPA fallback 固定读取这个根文件。它让设置页的直接访问、刷新与未知路径先取得
同一 SPA，再由 Navigo 选择页面或显示未找到。没有根页面时，仅开启 fallback 仍无法
使用嵌套的 HTML。assets-only 模式下，缺失 GET 包括资源请求也会返回 HTML 200；
客户端未找到页面不代表服务端 HTTP 404。
两条 route 只覆盖该页面及其资源，不替换主站。配置遵循
[Cloudflare 子目录静态资源](https://developers.cloudflare.com/workers/static-assets/routing/advanced/serving-a-subdirectory/)
、[SPA 配置](https://developers.cloudflare.com/workers/static-assets/routing/single-page-application/)
和 [Workers Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)。

在 `web` 目录中，可以本地运行实际 Wrangler 资源服务，检查设置页的直接访问和刷新：

```sh
npm run build
npx wrangler dev --local --ip 127.0.0.1 --port 8787
```

然后访问 `http://127.0.0.1:8787/xiaomi-86v1/settings`。这验证本地托管行为，不是
Cloudflare 发布或面板联网验收。

浏览器上传要求页面和面板处于可互访的局域网，并允许页面访问本地网络。
Chrome 142 引入该权限；对 private IP literal 的请求在授权后可获得 mixed-content 豁免，见
[Chrome 本地网络访问说明](https://developer.chrome.com/blog/local-network-access?hl=en)。
当前已实现的 CORS 不能代替此权限。用户已在 g 上确认正式 HTTPS 网页上传正常，
这项报告不证明所有浏览器支持。自动化 Chrome 只跟随跳转，未执行 POST。上传失败时检查
面板地址、同一局域网及浏览器授权，或下载
完整 Payload 后使用上述 cURL 命令。编辑和下载不依赖设备连接。

## 验证范围

2026-10-07 已用 Windows Chrome 验证本地 HTTP 页面到面板的真实上传，收到 202，
并逐字节确认请求像素与导出的 RGB565 相同、FNV 正确。纵向 SVG 的居中裁切和拖动
位置通过独立像素检查；按钮/键盘缩放、重置、双指 2 倍缩放、480×320 PNG 和
307200B RGB565 导出通过。初版 390px 手机布局没有横向溢出，旧版 API 折叠区域可
展开，无页面错误。这些检查保留为初次验证，与新版布局的检查分列。

另用浏览器里的延迟 202 模拟验证上传期间继续编辑或修改地址：成功反馈仍指向
实际发送的画面快照及原目标。它不增加真实设备上传的验证范围。
结果见 [前端浏览器验证](../web/browser-verification-20261007.json)。这些本地实验没有验证
线上 HTTPS 到 LAN；当前 Cloudflare 静态页面部署状态另见上节。HTTP 202 也不能代替
实屏观察或证明 LCD 扫描完成。

此前像素精确预览版默认 GitHub 画面与 PNG 逐像素一致；深灰主题、准确应用名称、17px 小标题、
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

历史 d 的真实 LAN 303 Location 与编译配置/设备 fragment 一致；Chrome 跟随后自动填入地址，
无 Content-Type 的完整网页 POST 和未指定 `-H` 的 Windows cURL 完整 VIMG POST 均返回
202，网页按钮显示成功且无页面错误。错误 FNV/422、任意 type 的错误 VIMG/400 后仍能
GET/303，两个有效上传被 GUI 消费；generation/displayed_generation=2、pending=0、server=1。
这次真实设备链路见 [d 发布结果](../firmware/releases/maintained-http-20261007-d.json)，与上述
模拟 HTTP、拦截导出和历史 raw 下载结果分开记录。该轮没有测试云 HTTPS 到 LAN 上传
或 `.vimg` 普通浏览器落盘。

用户已独立确认 d 的默认卡片显示和手机 LAN 跳转打开页面，仅这两项通过。此前 c 的
双击/息屏用户确认保留在 [旧 c 结果](../firmware/releases/maintained-http-20261007.json)，d 的
双击、手势、三击取消、息屏和米家仍待验收；没有进行或要求完整断电测试。

随后调整源图采样：480×320 硬边图放大到 110% 后，边缘出现正常的过渡色；默认
GitHub 图在 1:1 下仍与源像素一致。Windows Chrome 的 16 组缩放/移动检查确认中央
裁切与内存 PNG 逐像素一致，模拟 POST 的 307216B body 通过独立 RGB565/FNV 核对。
框外遮罩和 360/390px 布局通过，CSS `pixelated` 继续模拟成品像素。这些是本地画布、
内存 PNG 和模拟请求检查，没有新增设备上传或浏览器下载结论。

正式网页版本 `d92ceb00-ba7c-4832-ae9c-e00879c5ca12` 的线上页面、资源及测试用 query
检查通过。随后 g 的实际设备 GET/303 确认 Location 为正式 URL 加编码后的 `?device=`；
Windows Chrome 跟随后自动填写 endpoint/API，页面错误为 0，没有执行浏览器 POST。
用户报告“可以，上传正常”，确认正式网页跳转和 HTTPS 网页上传通过；随后新鲜只读
状态为 generation/displayed_generation=1、pending=0、server=1/error=0，GUI 持续运行。
没有记录自动化 POST 的状态/body 或 LCD 扫描。g 的实屏内容、
双击、上下滑、第三键三击取消、息屏和米家仍待单列验收；完整断电按用户要求跳过。
历史范围见 [g 发布结果](../firmware/releases/maintained-http-20261007-g.json)，
本轮安装与设置结果另见 [a 发布结果](../firmware/releases/maintained-idle-return-20261007-a.json)。

后续独立设置页改版已通过本地 Wrangler 生产产物检查：根 shell 副本与嵌套 HTML 字节一致；
设置路径、query、尾斜线、未知路径、HEAD 和标准 SPA 缺资源行为符合配置，根路径 307，
四项资源响应与新构建一致。这些是本地 HTTP 检查，未部署、未请求面板；浏览器中的
导航、历史和刷新行为另行验证，不扩展旧 a 实机结果。

### 独立设置页正式发布

2026-10-08 部署版本为 `e4aae372-469f-4df1-8cd7-b6acc3163d6d`，入口为
[设置](https://wan.sh/xiaomi-86v1/settings)。采用 Navigo `8.11.1` 的 History API 路由，
页面切换保留图片、裁切和设置草稿；面板地址同步到两页和普通 `device` query。
畸形 query 先规范化，不能让路由解析失败。未知应用路径显示未找到页面。

19 项前端单元测试与生产构建通过。正式站点的 7 项 HTTP 检查通过，包括设置页直接访问、
query、尾斜线、未知路径、HEAD 和根路径跳转；4 项静态资源逐字节匹配构建。
Windows Chrome 的 8 项线上检查覆盖设置页刷新、默认图片、导航和历史状态保留、
移动布局、未知路径和畸形 query，页面错误与自动设备请求均为 0。
这些检查没有向面板发送设置或图片，不改变 a 版的实机验收范围。

新版随后通过本地 Chrome 的 21 项路由与状态回归：画面页不再显示设置、设置页 query
和刷新、图片裁切保留、前进后退草稿、两处地址同步、显式读写、迟到编辑保护、离页
取消和 POST 未确认、地址切换、API hash、修饰点击、未知路径/尾斜线/无效或畸形 query，
以及 360px 无横向溢出和零页面错误。6 次设置请求均为浏览器模拟接口，没有访问面板；
不扩展原 a 结果，也不据本地回归推定新版线上部署已完成。
