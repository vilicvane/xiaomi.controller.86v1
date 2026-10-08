# 86V1 自定义固件：图片编辑前端

86V1 自定义固件的图片下拉屏幕编辑页面，网页显示名称为“小米智能家庭面板”。
使用 Vite + TypeScript 构建静态文件，Navigo 管理图片编辑与设置的独立页面。
图片编辑为 HTTP 图片 API 准备 480×320 画面。
图片在浏览器内裁切、缩放、转换并发送到同一局域网的面板；不需要后端或图片中转服务。
设备使用入口为 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)；刷写、调试器购买与
SWD 接线见 [刷写与配置指南](../docs/flashing.md)。安装指南明确依赖本机私有基线，
本目录的网页构建和发布命令不会刷写面板。
支持 PNG、JPEG、WebP、SVG，单文件最大 32MiB；动图采用解码后的静态首帧。
拖动调整位置，用滚轮、双指或键盘 `+`/`-` 调整 1～5 倍覆盖比例，键盘 `0` 重置构图。
页面不显示缩放或重置栏，可下载 PNG 和完整的 `.vimg` Payload。

页面直接进入编辑工作区，默认画面沿用此前设备端 GitHub 卡片：GitHub 标志、用户名、
项目名称与金色星标提示。页面主题为克制的深灰色 `#303b4b`，默认图片保持原有金色。
可直接发送默认画面，也可替换
自己的图片。API 指南常显，按 METHOD、URL、PAYLOAD 展示接口与二进制 body 说明。
下载的 Payload 为 307216B，包含 VIMG 头、RGB565LE 像素和 FNV 校验，可直接用于
页面的 cURL 示例；不再提供仅像素的 raw RGB565 下载。
图片网页请求和图片 cURL 示例不指定 Content-Type；接收端直接校验 VIMG、固定长度及 FNV。

从导航进入“设置”（`/xiaomi-86v1/settings`），读取或保存原界面未触摸后的等待时间。
图片编辑保留在 `/xiaomi-86v1/`；两页都支持 `?device=` 自动填写面板地址。
自动返回默认 60 秒、0 关闭、范围 0–3600。
设置按重启保留实现，图片仍为 RAM-only；只计触屏，物理按键不影响计时。设置请求只由
明确点击发出，初始为“尚未读取”；GET/POST JSON 各有 10 秒超时，不自动重试，地址改变
取消旧请求，迟到响应不覆盖新编辑。客户端位于 `src/settings.ts`，协议与当前验收范围见
[自动返回说明](../docs/auto-return.md)。a 安装、真实设置接口和暖复位加载已验证，旧 g 无此接口；
网页读写及定时返回的用户观察仍单列。
离开设置页会取消尚未完成的请求，保留输入草稿；已发出的保存请求未获确认时，不能
据取消操作断言设备没有保存。

预览在裁切框外继续显示整图，框外以 55% 黑色遮罩变暗；中央 480×320 区域与导出和
发送使用同一画布。源图缩放和移动使用高质量重采样生成 480×320 成品，预览仍以
`pixelated` 放大成品像素，模拟实际面板分辨率。
操作图标来自按需导入的 Lucide，GitHub 品牌 SVG 保留。favicon 按实物描绘黑色玻璃、
横向屏幕和底部白色三连键，浏览器直接使用第一方 SVG，并检查 16/32 像素下的渲染。
默认 [GitHub 卡片 PNG](public/github-card.png)来自第一方离线绘图，是静态资源而非设备 dump。
SHA-256：`ec1af029dc4492a8a09d8e4d985b3266434b05458d407167b3bddb710154c59e`。

从仓库根目录运行：

```powershell
npm --prefix web install
npm --prefix web run dev -- --host 0.0.0.0 --port 5173 --strictPort
npm --prefix web run test
npm --prefix web run build
```

使用 Node.js 24。开发服务器地址以 Vite 控制台为准。生产产物位于
`web/dist-cloudflare/xiaomi-86v1/`，资源前缀为 `/xiaomi-86v1/`；构建末尾复制同一页面到
`web/dist-cloudflare/index.html`，供 Cloudflare SPA 回退使用，不提交依赖和生成产物。
构建后可运行 `npm --prefix web run preview` 查看该子路径。
设备地址可手动输入，或由页面 URL 的 `?device=` 查询参数传入，例如
`https://wan.sh/xiaomi-86v1/?device=http%3A%2F%2FPANEL_IPV4%3A18086`。
双击面板自定义画面即可查看设备当前地址和 18086 端口。

裁切缩放、导出、上传语义及 Cloudflare 静态部署配置见
[前端开发与使用说明](../docs/frontend.md)，完整协议见
[HTTP 图片 API](../docs/http-image-api.md)。

HTTP 202 表示设备已接收并排队供 GUI 消费；图片保存在 RAM，重启不会保留。
本轮 a 沿用 `https://wan.sh/xiaomi-86v1/`；访问面板 `IP:18086` 会用 303 跳转，
通过 `?device=` 自动填入设备地址，使用设备不需要电脑开发服务器。未来更换目标
hostname 需要新的冻结固件 release；网页发布不会自动修改设备中的目标 URL。
浏览器请求本地网络权限时，授权后才能上传。
未连接设备时仍可编辑和下载。

a 的页面配置为 `PANEL_FRONTEND_URL=https://wan.sh/xiaomi-86v1/`、CORS `*`，
由设备端 release 在编译时确定，使用 `?device=` 自动填写面板地址。修改网页本身不能
替代独立冻结和硬件安装。此前 g 的四页读回/native/GLOBAL/暖启动通过；真实 GET/303 和
Chrome 跟随/填入地址通过，用户另行确认正式页面跳转及 HTTPS 网页上传正常；随后
只读状态显示 generation/displayed_generation=1、pending=0、server=1/error=0。
自动化 Chrome 没有发送 POST，GUI 消费也不等于 LCD 扫描验证。

## 发布

Worker `xiaomi-86v1` 已发布到
[独立 Workers 页面](https://xiaomi-86v1.vilicvane.workers.dev/xiaomi-86v1/)，HTTP 200 已确认。
无尾斜线路径的 307、四项静态资源与构建 SHA-256 一致、Chrome HTTPS 页面和默认图
加载、测试用 `?device=` 自动填入地址/API URL 均已验证；无页面错误或请求失败。
此次检查没有面板上传、下载或固件操作。
目标地址 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)已能正常访问，HTTP 200、无尾
斜线路径 307、静态资源和 Chrome 页面加载及测试用 `?device=` 参数均已验证。
此前同页设置卡片的发布版本为 `ecf90b3d-d93f-4a09-aab7-7d5b513a9d49`。正式页面 200、四项
线上资源与当时构建字节一致，Chrome 显示设置卡片、初始不自动请求 LAN、页面错误为 0；
这次页面检查没有请求面板。此前图片网页版本 `d92ceb00-ba7c-4832-ae9c-e00879c5ca12` 的
跳转和上传证据保持原范围。
独立设置页与 SPA 回退于 2026-10-08 发布，版本为
`e4aae372-469f-4df1-8cd7-b6acc3163d6d`，可直接访问
[设置页](https://wan.sh/xiaomi-86v1/settings)。正式站点 7 项 HTTP 检查、4 项资源字节比对
及 8 项 Chrome 导航/刷新/历史/移动布局检查通过；没有页面错误或自动设备请求。
19 项单元测试与生产构建通过；面板实机范围保持原记录。
部署仅绑定 `wan.sh/xiaomi-86v1` 和 `wan.sh/xiaomi-86v1/*` 两条狭窄 route，
采用 `dist-cloudflare` 内的静态资源，不包含 Worker 业务代码或后端服务。

[wrangler.jsonc](wrangler.jsonc) 启用 `assets.not_found_handling: single-page-application`。
Cloudflare 从资源根的 `index.html` 返回 SPA 页面，直接访问或刷新设置页仍由 Navigo
选择内容；未知应用路径由前端显示未找到页面。资源文件继续保留子路径，主站 route 不变。
根页面由 [prepare-spa.ts](scripts/prepare-spa.ts) 在构建后字节复制，避免手动维护两份 HTML。
assets-only SPA 对缺失 GET 也返回 HTML 200，不承诺缺失资源的 HTTP 404。

```powershell
npm --prefix web ci
npm --prefix web run test
npm --prefix web run deploy
```

`deploy` 执行构建后调用锁定的 `wrangler@4.148.0` 发布；配置见
[wrangler.jsonc](wrangler.jsonc)。静态页面打开和 LAN 上传分别验证；上述自动化页面
检查没有发送 POST，正式 HTTPS 网页上传由用户另行确认通过。

本地 HTTP 页面到面板的 Windows Chrome 上传、裁切/缩放和导出已验证，见
[浏览器验证](browser-verification-20261007.json)；该历史记录没有测试云端 HTTPS 到 LAN。
该记录的初次检查使用旧布局；新版深灰主题、默认卡片、像素放大、常显 API、
移动端布局和普通浏览器下载文件名已单列检查通过。
这些检查保留此前布局和 raw RGB565 下载的原范围；新版框外预览、完整 Payload、
发送按钮状态及 Lucide 图标也已单列检查通过。最新检查使用模拟 HTTP 和拦截导出
Blob/下载属性，没有新做真实设备上传或 `.vimg` 的普通浏览器落盘验证。

历史 d 已另行验证真实 LAN 303、Chrome 跟随/自动填地址、无 Content-Type 网页 POST/202 和
未指定 `-H` 的 cURL 完整 VIMG POST/202；用户确认默认卡片显示、手机 LAN 跳转打开网页。
结果见 [d 发布结果](../firmware/releases/maintained-http-20261007-d.json)，不扩展为手机上传、
其他 d 交互或云 HTTPS 到 LAN 上传验收。

历史 [g 发布结果](../firmware/releases/maintained-http-20261007-g.json)单独记录正式 query
跳转及用户 HTTPS 网页上传确认。其他 g 交互、实屏内容和米家状态仍待验收，未进行
完整断电测试；该记录不包含后续 g→a 迁移中的 g restore。

本轮 a 的 19 项网页单元测试、生产构建及 Windows Chrome 模拟设置服务检查通过：
初始零设置请求、读取/保存/0关闭、处理中与失败状态、旧地址与新编辑保护、390/360px
无横向溢出、图片预览不变、无页面错误。没有在该检查中访问真实面板。
固件与设置实机结果见 [a 发布结果](../firmware/releases/maintained-idle-return-20261007-a.json)。
真实设置 GET/POST 0 和 5 秒、越界 422 且保留运行值，以及保存 5 秒后暖复位重新加载均
通过，随后保存回 60 秒。直接 Node 图片 POST/202 与用户网页操作、LCD 和完整断电分开记录。

独立设置页的生产构建已用本地 Wrangler 检查：根/嵌套 HTML 精确一致，设置页、设备 query、
尾斜线及未知路径均返回同一 SPA，HEAD 无 body、根路径 307、四项资源与构建字节一致。
这些是本地 HTTP 托管检查，没有部署或请求面板，也不替代浏览器导航验证。

新版已通过本地 Chrome 的 21 项路由与状态回归：设置页直接访问/query/刷新、前进后退
及草稿、共享地址与图片裁切保留、明确读写与迟到编辑保护、离页取消和保存未确认状态、
API 锚点、修饰点击、未知/尾斜线/无效参数、360px 无溢出与零页面错误。6 次设置请求
全部使用浏览器模拟接口，没有请求真实面板，不扩展 a 版固件验收或证明新版已上线。
