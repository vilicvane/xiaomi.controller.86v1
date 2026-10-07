# 86V1 自定义固件：HTTP 图片 API

适用于 `firmware/` 的 86V1 自定义固件。历史 raw TCP/VACK 协议单独保留在
[原型协议](image-upload-protocol.md)，维护版不接受旧 raw TCP 上传。

维护版不要求 Content-Type。默认前端为
`https://wan.sh/xiaomi-86v1/`，`GET /` 通过 303 跳转并携带设备地址查询参数。
安装及实际验证范围见 [当前发布结果](../firmware/releases/maintained-http-20261007-g.json)。

监听局域网 TCP18086。双击自定义画面可显示地址；地址按名义 1 秒查询 IPv4，查询失败
显示 0 地址，更新时仅改变地址展示状态。原生 RPC 没有证明严格墙钟上限。

| 请求 | 成功行为 |
| --- | --- |
| `GET /` | 配置前端 URL 时 `303` + Location，否则 `200` 本机说明页 |
| `OPTIONS /api/image` | `204`，提供 CORS header |
| `POST /api/image` | 完整接收、校验并排队供 GUI 消费后 `202` |

响应使用 HTTP/1.1、Content-Length 和 Connection:close，一条连接只处理一个请求。
`303` 的 Location 示例为
`https://wan.sh/xiaomi-86v1/?device=http%3A%2F%2F203.0.113.20%3A18086`。
前端从 `device` 查询参数读取设备地址；已有查询参数时用 `&device=` 追加。
该参数名由设备提供，构建配置不能预置 `device`。Cloudflare 托管静态页面，
浏览器直接向局域网设备上传图片。

## 图片 body

Content-Type 可以省略；声明的类型不参与图片判断，因此也接受 cURL 默认的
`application/x-www-form-urlencoded`。通用 HTTP header 语法仍需有效。
Content-Length 必须为 **307216**。
body 为 16B VIMG header 加 307200B RGB565LE；header 和校验算法与原型相同：

| 偏移 | 类型 | 值 |
| --- | --- | --- |
| 0 | ASCII 4B | `VIMG` |
| 4 | u16 LE | 480 |
| 6 | u16 LE | 320 |
| 8 | u32 LE | 307200 |
| 12 | u32 LE | pixel payload 的 FNV-1a 32 位 |

像素按逻辑行排列，RGB565 的 bit15..11=R、bit10..5=G、bit4..0=B，每个像素低字节先发。
FNV 从 `0x811c9dc5` 开始，每 byte xor 后乘 `0x01000193`，截断为32位。
未完整接收、错误校验和或失败发布不会替换现有图像。

电脑可用第一方上传工具发送 raw RGB565，或生成测试图：

```powershell
node firmware/tools/upload.ts PANEL_IPV4 picture.rgb565
node firmware/tools/upload.ts PANEL_IPV4 --pattern
```

`202` 表示图像已被接受供 GUI 消费；不表示 LCD 扫描完成，也不表示图片已保存到 Flash。
地址页接收图像后仍保持地址页，双击返回图片时展示最新一张。

## 拒绝与连接条件

常见状态为 400 无效/截断请求、404 路径不存在、405 方法不支持、408 请求头超时、
411 缺 Content-Length、413 body 过大、417 不支持 Expect、
422 图像校验和错误、431 请求头超过2048B、503 clock/owned buffer/发布不可用。
不支持 Transfer-Encoding、chunked、100-continue、连接复用或图片压缩。

接收/发送各自检查 5 秒无进展及 30 秒总期限。网络 worker 串行处理请求，等待期间不持
GUI/publisher 锁；这些应用检查不约束底层 native RPC 的最长延迟。连接失效或超时后
不保证错误 response 送达；客户端未收到成功时应报告结果不确定。

API 提供 Access-Control-Allow-Origin、POST 及 Content-Type 的预检响应。浏览器前端须和
设备在可互访的局域网；g 的正式 HTTPS 页面上传已由用户确认，并观察到 GUI 消费新图。
自动化只验证了跳转与地址填入，浏览器本地网络权限仍需用户允许；不代表所有浏览器均兼容。
CORS 成功不代表整个浏览器链路已验证。当前 API 没有 sender 认证，FNV 只检查
传输内容错误；部署前端时应明确局域网访问语义。
