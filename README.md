# Xiaomi Smart Panel Image Drawer

为小米智能家庭面板 `xiaomi.controller.86v1` 开发可远程更新内容的自定义下拉屏幕。
设备端接收局域网上传的图片，与原界面在运行中交接显示和触摸；原米家应用继续运行。

目前交付是针对**本机官方 1.50.10 映像**的持久化原生程序补丁，复用 NuttX、板级驱动、
网络和 MCU 服务。它还不是能适用于任意同型号设备的完整替代固件。仓库不分发原厂映像、
设备身份或包含它们的刷机包。

## 维护版与验证状态

维护源码在 [firmware](firmware/README.md)。四页 release
`maintained-http-four-page-20261007-d` 已完成独立离线审查及冻结，主/辅助/网络 BIN 分别为
2946/236/2948B。四页安装读回、状态闭包、暖启动及真实浏览器跳转、图片上传和校验拒绝
通过；用户已确认手机访问面板地址能打开前端、默认 GitHub 卡片正常显示。
d 的双击、上下滑、三击取消、息屏唤醒及米家验收仍待记录。各项状态见
[当前发布结果](firmware/releases/maintained-http-20261007-d.json)，不继承此前版本的用户验收。

维护版实现的行为：

- 原界面顶边下拉打开自定义画面，上滑返回原界面，移除自有第三键三击入口。
- 双击自定义画面在图片与 `IP:18086` 地址页之间切换，不丢弃已上传图片。
- HTTP `POST /api/image` 接收 480×320 RGB565；图片接收、合成及触摸在设备上执行。
- 浏览器 `GET /` 用 `303` 跳转到临时局域网前端 `http://PC_LAN_IPV4:5173/`，自动带入面板地址。
- 上传不要求 Content-Type，仍校验完整 VIMG、固定长度和 FNV。
- 观察到原系统息屏时安全交接到自定义画面，保持原背光状态；d 的用户唤醒验收待记录。
- 程序持久化，图片仅在 RAM，重启恢复地址画面。

```powershell
node firmware/tools/upload.ts PANEL_IPV4 --pattern
node firmware/tools/upload.ts PANEL_IPV4 picture.rgb565
```

将 `PANEL_IPV4` 换成面板显示的非零地址；上传器接受 raw RGB565，PNG/JPEG 转换由
前端或电脑完成。维护版只接受 HTTP，协议见 [HTTP 图片 API](docs/http-image-api.md)。
`202` 表示完整图像已接受供 GUI 消费，不等于屏幕扫描完成或写入 Flash。
HTTPS 前端到局域网 HTTP 的浏览器权限/CORS 链路仍须单独验证。

## 图片编辑前端

[小米智能家庭面板](web/README.md)默认展示此前 GitHub 卡片，网页采用深灰主题，
默认图片保留金色星标。直接进入编辑工作区并常显 API 指南。支持选择或拖入 PNG/JPEG/WebP/SVG，拖动裁切、滚轮/双指/键盘
调整构图，框外显示变暗的整图区域，并下载 480×320 PNG 或完整 `.vimg` Payload、
直接发送到面板。API 提供直接发送 Payload 的 cURL 示例。图片在浏览器本地处理，
使用面板显示的地址；当前不需要重新刷写设备。

```powershell
npm --prefix web install
npm --prefix web run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

使用 Node.js 24。当前 d 跳转依赖电脑的局域网地址和 5173 开发服务器；电脑须保持在
该局域网并运行服务器。Cloudflare Pages 的静态部署设置及局域网上传说明见
[前端说明](docs/frontend.md)，当前尚未部署线上站点。

Windows Chrome 已验证裁切像素、缩放、PNG/RGB565 导出和本地网页到面板的真实
HTTP 上传；请求像素与导出内容一致，返回 202。结果见
[浏览器验证](web/browser-verification-20261007.json)，云端 HTTPS 到 LAN 尚未测试。
初次上传、此前 raw RGB565 导出与布局检查保留原范围；框外预览、完整 Payload 校验及
发送按钮状态的最新检查通过，使用模拟 HTTP 和拦截导出，与真实设备上传和落盘区分。

当前 d 已由 Windows Chrome 跟随真实 303 跳转并自动填写地址，无 Content-Type 的
网页上传和未指定 `-H` 的 cURL 上传均返回 202；两次图像被 GUI 消费。用户已确认默认
卡片可见及手机 LAN 跳转打开网页；手机上传与云 HTTPS 未测试。

历史 image drawer 的 TCP `VIMG/VACK`、三击交接及实机结果完整保留在
[原型协议](docs/image-upload-protocol.md)和
[历史硬件结果](analysis/persistence/native-image-drawer-hardware-result.json)。完整断电测试
按用户要求跳过，不借用旧版结果。当前验证边界见 [架构](docs/architecture.md)。

## 开发与研究入口

| 文档 | 内容 |
| --- | --- |
| [维护源码与工具](firmware/README.md) | 编译、模型、冻结发布及设备执行器 |
| [当前发布结果](firmware/releases/maintained-http-20261007-d.json) | 四页读回、真实跳转/上传及单列用户验收状态 |
| [当前架构](docs/architecture.md) | GUI/网络职责、四页和 RAM 布局、验证状态 |
| [HTTP 图片 API](docs/http-image-api.md) | 浏览器入口、图片格式、确认及连接限制 |
| [图片编辑前端](docs/frontend.md) | 本地裁切缩放、图片导出、局域网上传及静态部署 |
| [历史图片上传协议](docs/image-upload-protocol.md) | 三页原型 TCP/VACK，保留旧客户端入口 |
| [工程约束](docs/engineering-notes.md) | 供电、调试、版本专用 ABI、Flash 和失败处理 |
| [开发与维护流程](docs/development.md) | 本地材料、冻结校验、新版本开发和精确回退 |
| [研究与历史版本索引](docs/research-index.md) | 配网恢复、显示接管、版本演进和原始归档 |
| [维护需求与验收](docs/maintenance-plan.md) | 四项需求的实现和待验证边界 |

历史研究代码在 `analysis/`，历史 PowerShell 入口在 `scripts/`，OpenOCD 配置在 `diagnostics/`。
维护版由 `firmware/tools/` 管理，每次发布生成独立私有 release 快照。
已经冻结的历史集合保留原路径和字节，不能为了整理目录而移动或重新生成。

## 仓库与安装材料

仓库保存第一方源码、文档和经过审查的结构化证据。完整 NOR/RAM 备份、扇区镜像、
凭据、网络日志、工具链、第三方参考源码及生成的 BIN/ELF/Tcl 数组只在本地保存。
全新 clone 不能直接安装或回退设备；必须准备与该设备、版本及安装基线匹配的材料。

维护版回退必须使用其冻结的 `hardware.ts restore`，先恢复 exact image drawer 三页和
stock 网络页，再进入历史回退链；不能直接对四页维护版运行旧三页 writer。操作步骤见
[开发与维护流程](docs/development.md)。

本轮先用 c 的冻结执行器恢复精确基线，再安装 d；c 的恢复已通过，d 的硬件恢复尚未
执行。[旧 c 结果](firmware/releases/maintained-http-20261007.json)及其双击/息屏用户观察原样保留。
