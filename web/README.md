# 小米智能家庭面板

纯静态 Vite + TypeScript 页面，为维护版 HTTP 图片 API 准备 480×320 画面。
图片在浏览器内裁切、缩放、转换并发送到同一局域网的面板；不需要后端或图片中转服务。
支持 PNG、JPEG、WebP、SVG，单文件最大 32MiB；动图采用解码后的静态首帧。
拖动调整位置，用滚轮、双指或键盘 `+`/`-` 调整 1～5 倍覆盖比例，键盘 `0` 重置构图。
页面不显示缩放或重置栏，可下载 PNG 和完整的 `.vimg` Payload。

页面直接进入编辑工作区，默认画面沿用此前设备端 GitHub 卡片：GitHub 标志、用户名、
项目名称与金色星标提示。页面主题为克制的深灰色 `#303b4b`，默认图片保持原有金色。
可直接发送默认画面，也可替换
自己的图片。API 指南常显，按 METHOD、URL、PAYLOAD 展示接口与二进制 body 说明。
下载的 Payload 为 307216B，包含 VIMG 头、RGB565LE 像素和 FNV 校验，可直接用于
页面的 cURL 示例；不再提供仅像素的 raw RGB565 下载。
网页和 cURL 示例不指定 Content-Type；接收端直接校验 VIMG、固定长度及 FNV 校验和。

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

使用 Node.js 24。开发服务器地址以 Vite 控制台为准。生产产物位于 `web/dist`，不提交依赖和生成产物。
设备地址可手动输入，或由页面 URL 的 `#device=` fragment 传入。
双击面板自定义画面即可查看设备当前地址和 18086 端口。

裁切缩放、导出、上传语义及 Cloudflare Pages 配置见
[前端开发与使用说明](../docs/frontend.md)，完整协议见
[HTTP 图片 API](../docs/http-image-api.md)。

HTTP 202 表示设备已接收并排队供 GUI 消费；图片保存在 RAM，重启不会保留。
当前已安装 d 配置了临时 `http://PC_LAN_IPV4:5173/` 前端；访问面板 `IP:18086` 会用
303 跳转并自动填入设备地址。电脑须保持构建时的局域网地址并运行开发服务器。
上面的命令监听 LAN 并固定端口；未来更换目标 hostname 需要新的冻结固件 release。
Cloudflare 部署及 HTTPS 页面到面板 HTTP 的实际浏览器链路分别验证；浏览器请求本地网络
权限时，授权后才能上传。未连接设备时仍可编辑和下载。

本地 HTTP 页面到面板的 Windows Chrome 上传、裁切/缩放和导出已验证，见
[浏览器验证](browser-verification-20261007.json)；云端 HTTPS 到 LAN 尚未测试。
该记录的初次检查使用旧布局；新版深灰主题、默认卡片、像素放大、常显 API、
移动端布局和普通浏览器下载文件名已单列检查通过。
这些检查保留此前布局和 raw RGB565 下载的原范围；新版框外预览、完整 Payload、
发送按钮状态及 Lucide 图标也已单列检查通过。最新检查使用模拟 HTTP 和拦截导出
Blob/下载属性，没有新做真实设备上传或 `.vimg` 的普通浏览器落盘验证。

当前 d 已另行验证真实 303、Chrome 跟随/自动填地址、无 Content-Type 网页 POST/202 和
未指定 `-H` 的 cURL 完整 VIMG POST/202；用户确认默认卡片显示、手机 LAN 跳转打开网页。
结果见 [d 发布结果](../firmware/releases/maintained-http-20261007-d.json)，不扩展为手机上传、
其他 d 交互或云 HTTPS 验收。
