# 86V1 自定义固件：HTTP 图片 API

本页描述已安装的 `maintained-images-five-page-20261008-a` 的 PNG / JPEG / VIMG 接口，
实机直接上传、完整像素读回和拒绝损坏 PNG 的结果见
[发布结果](../firmware/releases/maintained-images-20261008-a.json)。
此前 `maintained-idle-return-four-page-20261007-a` 只接受 VIMG；其历史结果不改写。
历史 raw TCP/VACK 协议另见 [原型协议](image-upload-protocol.md)，维护版不接受旧 raw TCP 上传。

监听局域网 TCP18086。双击自定义画面可显示地址；默认前端为
`https://wan.sh/xiaomi-86v1/`。网页在用户点击发送时查询图片能力，再选择格式，
不会在打开页面时自动访问面板，也不会在失败的 POST 后换格式重试。
同一端口提供 `GET` / `POST /api/settings`，见 [设置 API](auto-return.md#设置-api)。

## 上传图片

将图片裁切缩放为 **480 × 320**，直接把完整 PNG 或 JPEG 文件作为请求 body：

```sh
curl --data-binary "@wallpaper-480x320.png" "http://PANEL_IPV4:18086/api/image"
curl --data-binary "@photo-480x320.jpg" "http://PANEL_IPV4:18086/api/image"
```

`@` 表示读取本地文件，替换它后面的文件名或路径，保留 `@`。
cURL 自动发送 Content-Length。无需 VIMG 头、multipart 包装或 Content-Type。
接收器按文件内容签名选择解码器，文件名及声明的 Content-Type 不参与判断；
因此 cURL 默认的 `application/x-www-form-urlencoded` 也不妨碍上传图片。

Content-Length 必须唯一、准确，范围为 **1–1048576B（1MiB）**。
支持的图片范围如下；设备不自动裁切缩放：

| 格式 | 要求 |
| --- | --- |
| PNG | 480×320、8-bit、非交错静态图片 |
| JPEG | 480×320、8-bit baseline、单个完整扫描；灰度，或 RGB / YCbCr 三分量的 4:4:4、4:2:2、4:2:0 采样；不支持 progressive、CMYK / YCCK |
| VIMG | 完整 307216B body，含 RGB565LE 像素及 FNV 校验 |

透明 PNG 铺黑底后转换为 RGB565；JPEG 是有损格式，文字及界面画面优先使用 PNG。
设备不按 EXIF 方向重新旋转图片，上传前应把方向及裁切写进实际像素。
PNG 的完整 chunk、CRC、IEND 和压缩流收尾，以及 JPEG 的真实结束和损坏警告，
均属于接收校验；仅产生足够像素不能视为完整成功。
PNG 可包含调色板和透明信息；额外元数据限于 IDAT 前的 pHYs、sRGB、gAMA、cHRM。
其他元数据（包括文本、ICC profile、EXIF）以及 APNG 返回 415。
网页把原图重新绘制到 8-bit sRGB 画布后生成 PNG，不直接转发原文件元数据；
浏览器导出的 PNG 本身仍需满足上述格式范围。

第一方命令行工具保持图片文件原字节：

```powershell
node firmware/tools/upload.ts PANEL_IPV4 wallpaper-480x320.png
node firmware/tools/upload.ts PANEL_IPV4 photo-480x320.jpg
```

PNG / JPEG 上传前会查询能力；旧固件明确返回 404 时，工具会提示升级而停止，
不会把普通图片偷偷改成另一种格式，也不会发送必然不兼容的 POST。

`202` 表示图像已完成接收及校验，并在 RAM 中排队供 GUI 消费；
不表示 LCD 扫描完成，也不表示图片已保存到 Flash。重启后图片清除。
未完整接收、解码失败或失败发布不会替换当前图像。
地址页接收新图片后仍保持地址页，双击返回图片时展示最新一张。

## 请求与能力查询

| 请求 | 成功行为 |
| --- | --- |
| `GET /` | 配置前端 URL 时 `303` + Location，否则 `200` 本机说明页 |
| `GET /api/image` | `200`、`application/json`，列出可上传的格式 |
| `OPTIONS /api/image` | `204`，提供 CORS header |
| `POST /api/image` | 完整接收、校验并排队供 GUI 消费后 `202` |

能力响应为：

```json
{"formats":["png","jpeg","vimg"]}
```

已部署的旧维护版对 `GET /api/image` 返回 404，网页仅在这个明确响应后选择 VIMG。
能力查询发生网络错误、返回无效 JSON 或其他 HTTP 状态时，客户端停止，不把错误当作旧固件。
能力 GET 只读，不上传、清除或持久化任何图片。

响应使用 HTTP/1.1、Content-Length 和 Connection:close，一条连接只处理一个请求。
`303` 的 Location 示例为
`https://wan.sh/xiaomi-86v1/?device=http%3A%2F%2F203.0.113.20%3A18086`。
前端从 `device` 查询参数读取地址；已有查询参数时用 `&device=` 追加。
该参数名由设备提供，构建配置不能预置 `device`。Cloudflare 托管静态页面，
浏览器直接向局域网设备上传图片。

## 已部署客户端的 VIMG

VIMG 保留用于旧固件及既有客户端；网页检测到旧版接口时会在内部生成完整 VIMG Payload，下载按钮仅导出 PNG：

```sh
curl --data-binary "@wallpaper-480x320.vimg" "http://PANEL_IPV4:18086/api/image"
```

它的 Content-Length 必须为 **307216**；body 为 16B header 加 307200B RGB565LE：

| 偏移 | 类型 | 值 |
| --- | --- | --- |
| 0 | ASCII 4B | `VIMG` |
| 4 | u16 LE | 480 |
| 6 | u16 LE | 320 |
| 8 | u32 LE | 307200 |
| 12 | u32 LE | pixel payload 的 FNV-1a 32 位 |

像素按逻辑行排列，RGB565 的 bit15..11=R、bit10..5=G、bit4..0=B，每个像素低字节先发。
FNV 从 `0x811c9dc5` 开始，每 byte xor 后乘 `0x01000193`，截断为 32 位。
普通 PNG / JPEG 不添加 FNV 或专用文件头。

命令行工具也接受 `.vimg`，或把明确命名为 `.rgb565` 的 raw 像素包装为 VIMG：

```powershell
node firmware/tools/upload.ts PANEL_IPV4 wallpaper-480x320.vimg
node firmware/tools/upload.ts PANEL_IPV4 picture.rgb565
node firmware/tools/upload.ts PANEL_IPV4 --pattern
```

## 拒绝与连接条件

常见状态为 400 无效/截断请求、404 路径不存在、405 方法不支持、408 请求头超时、
411 缺 Content-Length、413 body 过大、415 不支持格式/编码、417 不支持 Expect、
422 图片尺寸或内容校验失败、431 请求头超过2048B、503 clock/资源/解码或发布不可用。
不支持 Transfer-Encoding、chunked、100-continue 或连接复用。
PNG / JPEG 自身的格式压缩受到支持；HTTP Content-Encoding 只能省略或为 identity，
gzip、deflate 等其他值返回 415，不能在图片外再包一层 HTTP 压缩。

接收/发送各自检查 5 秒无进展及 30 秒总期限。网络 worker 串行处理请求，等待及解码
期间不持 GUI/publisher 锁；这些应用检查不约束底层 native RPC 的最长延迟。
解码器使用每请求的独立状态及预算，不借用共享 GUI 图片缓存或正在显示的缓冲区。
连接失效或超时后不保证错误 response 送达；客户端未收到成功时应报告结果不确定，
检查设备后手动重试，不能自动重发。

API 提供 Access-Control-Allow-Origin、GET/POST 及 Content-Type 的预检响应。
浏览器前端须和设备在可互访的局域网；浏览器本地网络权限仍需用户允许。
当前正式 HTTPS 页面在 agent Chrome 中已完成能力查询和单次 PNG 上传，返回 202，
完整 RGB565 读回一致。该测试临时用 CDP 授予站点本地网络权限，随后恢复 prompt；
不代表用户点击了权限提示或所有浏览器均可用。
g 的正式 HTTPS 页面 VIMG 上传曾由用户确认，并观察到 GUI 消费新图，
这不是新 PNG / JPEG 接口或所有浏览器的实机验证。CORS 成功也不代表整个浏览器链路已验证。
当前 API 没有 sender 认证；FNV 与图片格式校验均不提供身份认证。
