# 86V1 自定义固件：图片编辑前端

86V1 自定义固件的图片下拉屏幕编辑页面，网页显示名称为“小米智能家庭面板”。
当前源码使用 React `19.3.0`、TypeScript `7.0.2` 和 Vite `8.3.3` 构建静态文件，
React Router `8.4.0` 管理画面、设置、连接配置和 API 的独立页面，图标使用 `lucide-react`。
图片编辑为 HTTP 图片 API 准备 480×320 画面。
图片在浏览器内裁切、缩放、转换并发送到同一局域网的面板；不需要后端或图片中转服务。
当前已安装 `maintained-persistent-images-six-page-20261008-a`，支持 PNG/JPEG/VIMG 的 MMC 持久保存。
六页固件安装时的非 React 网页版本 `6d2572cb-61e0-40b1-b28f-837e32d53157` 曾部署，HTML/favicon/JS/CSS 与构建
一致，Chrome 无错误、初始无自动局域网请求。正式 HTTPS 按钮发送 PNG 返回 202，显示
“画面已保存”；完整像素读回和暖重启后的自动恢复通过。这是已有实机检查点，不是当前
React 窄版的新实机验收。当前 React 窄版已发布为 `4d60d470-f236-4390-a545-7ca592fcdc70`，
验证见末尾；历史五页及更早结果单独保留。
设备使用入口为 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)；刷写、调试器购买与
SWD 接线见 [刷写与配置指南](../docs/flashing.md)。安装指南明确依赖本机私有基线，
本目录的网页构建和发布命令不会刷写面板。
支持 PNG、JPEG、WebP、SVG，单文件最大 32MiB；动图采用解码后的静态首帧。
拖动调整位置，用滚轮、双指或键盘 `+`/`-` 调整 1～5 倍覆盖比例，键盘 `0` 重置构图。
页面不显示缩放或重置栏，下载只提供 PNG 图片。

配置地址后进入编辑工作区，默认画面沿用此前设备端 GitHub 卡片：GitHub 标志、用户名、
项目名称与金色星标提示。页面主题为克制的深灰色 `#303b4b`，默认图片保持原有金色。
可直接发送默认画面，也可替换
自己的图片。独立 API 页按 METHOD、URL、PAYLOAD 展示图片上传与自动返回读写接口。
下载的 PNG 可直接发给当前接口，
无需转换或添加专用头部。普通图片最大 1MiB，必须为 480×320；编码范围见
[HTTP 图片 API](../docs/http-image-api.md)。图片网页请求和 cURL 示例不指定 Content-Type；
接收端按文件签名识别 PNG/JPEG/VIMG，并验证完整图像。

发送时先查询 `GET /api/image`。设备支持 PNG 时，网页把裁切结果的 sRGB 画布导出为完整 PNG
再上传；JPEG 通过 cURL/CLI 保持文件原字节。只有旧固件能力查询明确返回 404，网页才使用
RGB565LE、VIMG 头和 FNV。查询错误会停止，失败 POST 不会换格式重发；打开网页不会自动
访问面板。旧 VIMG 仍用于上述内部发送兼容，不再提供 VIMG 下载按钮。

从导航进入“设置”（`/xiaomi-86v1/settings`），读取或保存原界面未触摸后的等待时间。
图片编辑保留在 `/xiaomi-86v1/`。页面采用最大 680px 的窄版单列布局，裁切预览没有外层白色卡片，
选择图片、下载 PNG、发送三个独立按钮位于画面下方。
连接配置位于 `/xiaomi-86v1/connection`，不再有全局连接侧栏。有效的 `?device=` 优先并
保存在当前浏览器；没有有效参数时读取有效的本地地址。两者都没有时，画面与设置页会先
进入连接配置，提交后回到原页面。输入草稿在提交前不改变活动地址，不自动探测面板。
`/xiaomi-86v1/api` 可在未配置地址时直接阅读；使用活动地址或文档示例 `192.0.2.1:18086`，
提供图片 POST、自动返回 GET/POST、JSON 与 cURL 示例。浏览器保存地址与设备设置是独立事项。
自动返回默认 60 秒、0 关闭、范围 0–3600。
设置页直接以“自动返回”为标题，卡片填满单列；秒数输入与读取、保存按钮在桌面同排，
移动端按空间换行。输入占位值为 60，未读取时不代表设备当前值。
设置按重启保留实现，当前图片也单独保存到 MMC；只计触屏，物理按键不影响计时。设置请求只由
明确点击发出，初始为“尚未读取”；GET/POST JSON 各有 10 秒超时，不自动重试，地址改变
取消旧请求，迟到响应不覆盖新编辑。客户端位于 `src/settings.ts`，协议与当前验收范围见
[自动返回说明](../docs/auto-return.md)。idle-return a 安装、真实设置接口和暖复位加载已验证，旧 g 无此接口；
网页读写及定时返回的用户观察仍单列。
离开设置页会取消尚未完成的请求，保留输入草稿；已发出的保存请求未获确认时，不能
据取消操作断言设备没有保存。

`EditorProvider` 和 `SettingsProvider` 位于路由上层，切页保留已解码图片、裁切、设置草稿
及结果状态。图片发送在内部切页时继续；地址变化或应用卸载会取消未完成请求。设置请求
在离开设置页时取消。已发出的 POST 未获确认时保留不确定状态，不自动重试。
入口为 [main.tsx](src/main.tsx) 和 [App.tsx](src/App.tsx)，连接配置与活动地址位于
[PanelConnection.tsx](src/PanelConnection.tsx) / [panel-context.tsx](src/panel-context.tsx)。
编辑、Canvas 绘制、设置和 API 说明分别位于 [ImageEditor.tsx](src/ImageEditor.tsx)、
[editor-render.ts](src/editor-render.ts)、[SettingsPage.tsx](src/SettingsPage.tsx) 与
[ImageApi.tsx](src/ImageApi.tsx)。

预览在裁切框外继续显示整图，框外以 55% 黑色遮罩变暗；中央 480×320 区域与导出和
发送使用同一画布。源图缩放和移动使用高质量重采样生成 480×320 成品，预览仍以
`pixelated` 放大成品像素，模拟实际面板分辨率。
操作图标使用按需导入的 `lucide-react` 组件，GitHub 品牌 SVG 保留。favicon 按实物描绘黑色玻璃、
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

能力 `persistent: true` 加本次 POST 202 表示已保存并排队供 GUI 消费，按钮显示“画面已保存”。
旧版没有该能力时只显示“画面已接收”，图片在 RAM。保存后发布或响应仍可能失败，不能自动重发。
详情见 [图片持久保存](../docs/persistent-images.md)。
当前版本和历史 idle-return a 沿用 `https://wan.sh/xiaomi-86v1/`；访问面板 `IP:18086` 会用 303 跳转，
通过 `?device=` 自动填入设备地址，使用设备不需要电脑开发服务器。未来更换目标
hostname 需要新的冻结固件 release；网页发布不会自动修改设备中的目标 URL。
浏览器请求本地网络权限时，授权后才能上传。
配置有效地址后，即使暂时无法连接设备也可编辑和下载；API 页不要求配置地址。

页面配置为 `PANEL_FRONTEND_URL=https://wan.sh/xiaomi-86v1/`、CORS `*`，
由设备端 release 在编译时确定，使用 `?device=` 自动填写面板地址。修改网页本身不能
替代独立冻结和硬件安装。此前 g 的四页读回/native/GLOBAL/暖启动通过；真实 GET/303 和
Chrome 跟随/填入地址通过，用户另行确认正式页面跳转及 HTTPS 网页上传正常；随后
只读状态显示 generation/displayed_generation=1、pending=0、server=1/error=0。
自动化 Chrome 没有发送 POST，GUI 消费也不等于 LCD 扫描验证。

## 发布

当前 Worker `xiaomi-86v1` 的发布版本为 `4d60d470-f236-4390-a545-7ca592fcdc70`，
源码检查点为 `codex/react-frontend` 的 `5c8e2cf`，包含合入的 `df96bed` 持久保存实现。
正式入口为 [wan.sh/xiaomi-86v1/](https://wan.sh/xiaomi-86v1/)。线上 9 项 HTTP、4 项资源字节
比对和 12 项 Chrome 检查通过；没有设备请求、上传或下载，本轮不新增实机验收。
仍只绑定 `wan.sh/xiaomi-86v1` 与 `wan.sh/xiaomi-86v1/*`，根路径规则未改。

React 基础版已发布为 `e6196398-f485-4f11-ab1b-20d18f6fa664`：29 项单元测试、32 项本地
浏览器检查、7 项线上 HTTP 检查、4 项资源比对和 10 项线上浏览器检查通过。
这些是后续布局调整前的历史检查点，不代替当前发布版本的验证。

此前直接 PNG 上传的非 React 网页已部署为 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5`。
当轮 HTML、JS、CSS、SVG favicon 和默认 PNG 五项文件均返回 200，字节及 SHA-256 与构建一致；
Chrome 页面/设置路径检查通过，页面与控制台错误为 0，初始自动 LAN 请求为 0。
真实发送按钮的 PNG 上传另列于末尾当前验证范围；以下此前线上证据保留原范围。

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
Cloudflare 从资源根的 `index.html` 返回 SPA 页面，直接访问或刷新设置页由 React Router
选择内容；未知应用路径由前端显示未找到页面。资源文件继续保留子路径，主站 route 不变。
根页面由 [prepare-spa.ts](scripts/prepare-spa.ts) 在构建后字节复制，避免手动维护两份 HTML。
assets-only SPA 对缺失 GET 也返回 HTML 200，不承诺缺失资源的 HTTP 404。

用户确认发布后，从仓库根目录执行：

```powershell
npm --prefix web ci
npm --prefix web run test
npm --prefix web run deploy
```

`deploy` 执行构建后调用锁定的 `wrangler@4.148.0` 发布；配置见
[wrangler.jsonc](wrangler.jsonc)。静态页面打开和 LAN 上传分别验证；上述自动化页面
检查没有发送 POST，历史 g 的正式 HTTPS 网页 VIMG 上传由用户另行确认通过。

本地 HTTP 页面到面板的 Windows Chrome 上传、裁切/缩放和导出已验证，见
[浏览器验证](browser-verification-20261007.json)；该历史记录没有测试云端 HTTPS 到 LAN。
该记录的初次检查使用旧布局；新版深灰主题、默认卡片、像素放大、常显 API、
移动端布局和普通浏览器下载文件名已单列检查通过。
这些检查保留此前布局和 raw RGB565 下载的原范围；新版框外预览、完整 Payload、
发送按钮状态及 Lucide 图标也已单列检查通过。当时的检查使用模拟 HTTP 和拦截导出
Blob/下载属性，没有新做真实设备上传或 `.vimg` 的普通浏览器落盘验证。

历史 d 已另行验证真实 LAN 303、Chrome 跟随/自动填地址、无 Content-Type 网页 POST/202 和
未指定 `-H` 的 cURL 完整 VIMG POST/202；用户确认默认卡片显示、手机 LAN 跳转打开网页。
结果见 [d 发布结果](../firmware/releases/maintained-http-20261007-d.json)，不扩展为手机上传、
其他 d 交互或云 HTTPS 到 LAN 上传验收。

历史 [g 发布结果](../firmware/releases/maintained-http-20261007-g.json)单独记录正式 query
跳转及用户 HTTPS 网页上传确认。其他 g 交互、实屏内容和米家状态仍待验收，未进行
完整断电测试；该记录不包含后续 g→a 迁移中的 g restore。

idle-return a 当轮的 19 项网页单元测试、生产构建及 Windows Chrome 模拟设置服务检查通过：
初始零设置请求、读取/保存/0关闭、处理中与失败状态、旧地址与新编辑保护、390/360px
无横向溢出、图片预览不变、无页面错误。没有在该检查中访问真实面板。
固件与设置实机结果见 [a 发布结果](../firmware/releases/maintained-idle-return-20261007-a.json)。
真实设置 GET/POST 0 和 5 秒、越界 422 且保留运行值，以及保存 5 秒后暖复位重新加载均
通过，随后保存回 60 秒。直接 Node 图片 POST/202 与用户网页操作、LCD 和完整断电分开记录。

历史 Navigo 版的生产构建曾用本地 Wrangler 检查：根/嵌套 HTML 精确一致，设置页、设备 query、
尾斜线及未知路径均返回同一 SPA，HEAD 无 body、根路径 307、四项资源与构建字节一致。
这些是本地 HTTP 托管检查，没有部署或请求面板，也不替代浏览器导航验证。

历史 Navigo 版通过本地 Chrome 的 21 项路由与状态回归：设置页直接访问/query/刷新、前进后退
及草稿、共享地址与图片裁切保留、明确读写与迟到编辑保护、离页取消和保存未确认状态、
API 锚点、修饰点击、未知/尾斜线/无效参数、360px 无溢出与零页面错误。6 次设置请求
全部使用浏览器模拟接口，没有请求真实面板，不扩展 a 版固件验收，也不证明 React 改版通过。

## 已有持久保存版实机验证

六页固件安装时的 30 项网页测试通过；`6d2572cb-61e0-40b1-b28f-837e32d53157` 正式页面
能力 GET200 和单次 6050B PNG POST202/“画面已保存”通过，
没有 Content-Type 或自动重发。临时 CDP 本地网络权限测试后恢复 prompt，非用户点击许可。
完整 RGB565 读回一致，随后暖重启自动加载该 PNG，计数1、pending0/server1/error0。
用户对默认画面、手势、双击及米家的组合问题回复“确认正常”；完整断电仍按用户要求跳过。
这是一次组合反馈，不扩展为各项独立测量。安装与实际请求范围见
[六页发布结果](../firmware/releases/maintained-persistent-images-20261008-a.json)。本轮 React 改版不新增设备请求。

## 历史五页 PNG/JPEG 验证

历史 images 版本通过 420 个实际 ARM 解码案例、36 组 UI、34 组 HTTP、17 组设置模型，
`0aa9d5c` 当轮网页通过 29 项单元测试。本机 Chrome 的真实 sRGB Canvas PNG 已进入离线 native HTTP
模型，接收、解码和 GUI 像素均与参考一致；解码本身执行原厂 ARM 指令。
该 Chrome 检查没有请求真实面板。独立实机验证已完成五页安装闭包、GLOBAL、暖启动和
新鲜 patched 检查；Node PNG/JPEG 请求均返回 202，RGB565 读回与参考一致。
坏 CRC PNG 返回 422，generation 和原图片保持不变。最后恢复默认 PNG，generation 3
已由 GUI 消费，运行状态正常。这些 Node 结果不证明 LCD、浏览器上传、米家或用户交互通过。
独立 Chrome 验证随后使用官方 HTTPS 页面的发送按钮：能力 GET 200、单次 6050B PNG
POST 202、无 Content-Type，按钮显示“画面已接收”，无请求错误。
本地网络权限最初提示时 GET 等待且无 POST；通过临时 origin 范围的 CDP 权限覆盖后完成发送，
不是用户点击授权，也不证明全部浏览器可用。请求接受与 GUI 像素读回、LCD 观察分开记录。
随后只读 RGB565 完整读回与默认画面一致，稳定 slot 和 generation/displayed_generation 4、
pending 0、server 1/error 0、GUI 运行正常；不是 LCD scanout。临时 origin 权限已恢复为 prompt 并确认。
本轮 GET 设置读到已有的 60 秒，未保存设置；自身恢复未实机测试，完整断电由用户跳过。
该原检查点见 [images 发布结果](../firmware/releases/maintained-images-20261008-a.json)。五页版自身恢复
后来在六页迁移中通过，只记录在六页结果中，原五页结果不变。
历史 a/g 的暖启动、设置或上传结果不继承到此版本，解码研究详见
[直接 PNG/JPEG 研究](../docs/research/direct-image-upload.md)。

React 基础版的网页验证与发布范围见上节；它沿用同一图片和设置 API，没有扩展设备验收。
此前本地右侧布局、PNG 下载与 HMR 调整的验收见下节，不沿用基础版或历史 Navigo 的检查结论。
当前单列布局、连接配置和独立 API 页已发布，本地及线上验证见末尾。

## 此前右侧布局的本地验证

2026-10-08 的右侧布局通过类型检查、生产构建和 29 项单元测试；Chrome 的 32 项通用回归、
24 项设置确认回归、6 项实际 Fast Refresh 检查和 5 项布局检查通过。设置和图片请求使用模拟接口，
没有请求真实面板；PNG 导出使用拦截的 Blob，没有实际下载文件。默认图片像素保持一致，预览继续按像素拉伸。

本地 Wrangler 的 7 项 HTTP 检查与 4 项资源字节比对通过；生产产物的 10 项 Chrome 检查覆盖
子路径、刷新、历史、共享地址、API 锚点、未知路径和手机布局，无页面错误或自动设备请求。
该阶段未发布。本地预览服务器地址以 Vite 输出为准。

## 合入持久保存前的单列布局验证

2026-10-08 的类型检查、生产构建和 36 项单元测试通过，其中新增 7 项地址测试。
Windows Chrome 在开发服务器和生产产物各完成 27 项回归，每轮 13 次模拟设备 API 请求，
真实 LAN 请求和实际下载均为 0，页面及 React 错误为 0；主动模拟旧能力 404 时的控制台
资源报错符合预期。

检查覆盖无地址时先配置再返回、无地址直接阅读三张 API 卡片、地址规范化与本地保存、
草稿失焦不提交、无效参数回退、URL 优先和历史恢复、存储受限提示及旧目标请求隔离。
单次 PNG 发送、明确 404 后的 VIMG 兼容、拦截 PNG 的名称和内容、默认图像素保持一致。
四页在 320/360/390/600/1280px 下无横向溢出或自动 LAN 请求，680px 单列、下置按钮和
设置输入的响应式布局通过。

本地 Wrangler 的 9 项 HTTP 路由、HEAD 和斜线跳转检查、4 项资源字节比对通过，
API 与连接配置页可直接访问和刷新。这些检查没有操作设备，不扩展固件、LCD 或米家验收；
该验证发生在合入六页持久保存语义前，不代替下面已发布版本的验证。

## 当前 React 窄版的发布验证

合入持久保存语义后的 37 项单元测试、类型检查和生产构建通过。开发与本地生产产物的
Chrome 回归各通过 32 项，每轮 26 次模拟设备请求；真实 LAN 请求、实际下载和 React
错误为 0。主动模拟 404、503、409 的资源报错符合预期。模拟验证包括已保存/已接收
反馈、无效能力响应不上传、503 未确认状态跨裁切与切页保留，以及 409 拒绝和发送快照反馈。

本地 Wrangler 和线上各通过 9 项 HTTP 检查与 4 项资源完整字节比对。正式 HTTPS 页面的
12 项 Chrome 检查覆盖四页导航与刷新、连接配置和本地地址回退、草稿/历史状态、三张
API 卡片、680px 画面与下置按钮；默认图像素不变，320/360px 下均无横向溢出。
线上页面及控制台错误、设备请求、上传和下载均为 0。本轮未操作面板，不增加 LCD、
米家或暖重启验证；此前 `6d2572cb` 的真实上传与恢复证据保留原范围。
